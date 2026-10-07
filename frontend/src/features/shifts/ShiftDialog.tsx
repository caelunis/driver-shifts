import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm } from "react-hook-form";

import { api } from "../../shared/api/client";
import type { Shift, ShiftPatch, ShiftStartIn } from "../../shared/api/types";
import { applyServerErrors } from "../../shared/lib/forms";
import { isoDay, isoToLocal, localToIso, localWithOffset, nowLocal, parseOffset } from "../../shared/lib/time";
import { Field } from "../../shared/ui/Field";
import { Modal } from "../../shared/ui/Modal";
import { useToast } from "../../shared/ui/Toast";
import { invalidateDiary, type DiaryScope } from "../diary/scope";
import { DAY_MS } from "./api";
import { shiftFormSchema, type ShiftDialogMode, type ShiftFormValues } from "./schema";

interface Props {
  scope: DiaryScope;
  mode: ShiftDialogMode;
  open: boolean;
  onClose: () => void;
  /** The shift to edit or close */
  shift?: Shift;
  /** Called with the local day of the saved shift */
  onSaved?: (day: string) => void;
}

const TITLES: Record<ShiftDialogMode, string> = {
  past: "Внести прошедшую смену",
  edit: "Изменить смену",
  close: "Закончить смену",
};
const FIELDS = ["start", "end", "note"] as const;

export function ShiftDialog(props: Props) {
  return (
    <Modal open={props.open} onClose={props.onClose} title={TITLES[props.mode]}>
      <ShiftForm {...props} />
    </Modal>
  );
}

function ShiftForm({ scope, mode, onClose, shift, onSaved }: Props) {
  const qc = useQueryClient();
  const toast = useToast();

  const initial: ShiftFormValues = useMemo(
    () => ({
      start: shift ? isoToLocal(shift.start) : "",
      // Closing: "now", unless the shift is a forgotten one that would exceed 24 hours
      end: shift?.end
        ? isoToLocal(shift.end)
        : mode === "close" && shift && Date.now() - Date.parse(shift.start) < DAY_MS
          ? nowLocal(scope.tz)
          : "",
      note: shift?.note ?? "",
    }),
    [shift, mode, scope.tz],
  );
  const { register, handleSubmit, setError, formState } = useForm<ShiftFormValues>({
    resolver: zodResolver(shiftFormSchema(mode)),
    defaultValues: initial,
  });
  const err = formState.errors;
  // Edited times keep the shift's own offset; new ones get the driver's zone
  const offset = shift ? (parseOffset(shift.start) ?? 0) : null;
  const toIso = (local: string) => (offset === null ? localToIso(local, scope.tz) : localWithOffset(local, offset));

  const save = useMutation({
    mutationFn: async (v: ShiftFormValues): Promise<Shift> => {
      if (mode === "past") {
        const body: ShiftStartIn = { start: toIso(v.start), end: toIso(v.end), note: v.note };
        return api<Shift>("POST", "/api/shifts", body);
      }
      if (mode === "close" && scope.role === "driver") {
        return api<Shift>("POST", `/api/shifts/${shift!.id}/close`, v.end ? { end: toIso(v.end) } : {});
      }
      // Edit, or the admin closing a shift (the admin has no close endpoint: an end is a change)
      const patch: ShiftPatch = {};
      if (v.start !== initial.start) patch.start = toIso(v.start);
      if (v.end !== initial.end) patch.end = v.end ? toIso(v.end) : null; // cleared: reopen
      if (v.note !== initial.note) patch.note = v.note;
      return api<Shift>("PATCH", `${scope.base}/shifts/${shift!.id}`, patch);
    },
    onSuccess: async (saved) => {
      toast.ok(mode === "past" ? "Смена добавлена" : mode === "close" ? "Смена закончена" : "Смена изменена");
      await invalidateDiary(qc, scope);
      onSaved?.(isoDay(saved.start));
      onClose();
    },
    onError: (e) => {
      const rest = applyServerErrors(e, setError, FIELDS);
      if (rest) toast.err(rest);
    },
  });

  return (
    <form className="form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
      {mode !== "close" && (
        <Field label="Начало" error={err.start?.message}>
          <input type="datetime-local" {...register("start")} />
        </Field>
      )}
      <Field
        label="Окончание"
        error={err.end?.message}
        hint={
          mode === "edit"
            ? shift?.end
              ? "Очистите поле, чтобы снова открыть смену"
              : "Пусто — смена продолжается"
            : mode === "close"
              ? "Не позже чем через 24 часа после начала"
              : undefined
        }
      >
        <input type="datetime-local" {...register("end")} />
      </Field>
      {mode !== "close" && (
        <Field label="Заметка" error={err.note?.message}>
          <textarea rows={2} maxLength={500} placeholder="Например: аэропорт, вечерняя смена" {...register("note")} />
        </Field>
      )}
      <div className="modal-actions">
        <button type="button" onClick={onClose}>
          Отмена
        </button>
        <button type="submit" className="primary" disabled={save.isPending}>
          {mode === "close" ? "Закончить" : mode === "past" ? "Добавить" : "Сохранить"}
        </button>
      </div>
    </form>
  );
}
