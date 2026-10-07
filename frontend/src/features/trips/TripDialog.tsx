import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { useForm, useWatch } from "react-hook-form";

import { api, ApiError, request } from "../../shared/api/client";
import type { Shift, Trip, TripIn, TripPatch } from "../../shared/api/types";
import { applyServerErrors } from "../../shared/lib/forms";
import { commissionFor, formatMoney, formatPct } from "../../shared/lib/money";
import { isoToLocal, localToIso, localWithOffset, parseOffset } from "../../shared/lib/time";
import { uuid } from "../../shared/lib/uuid";
import { Field } from "../../shared/ui/Field";
import { Modal } from "../../shared/ui/Modal";
import { useToast } from "../../shared/ui/Toast";
import { meKey } from "../auth/api";
import { invalidateDiary, type DiaryScope } from "../diary/scope";
import { tripFormSchema, type TripFormValues } from "./schema";

interface Props {
  scope: DiaryScope;
  open: boolean;
  onClose: () => void;
  /** The shift a new trip goes into */
  shift: Shift;
  /** Set when editing */
  trip?: Trip;
  /** Prefilled start of a new trip, datetime-local */
  defaultStart?: string;
}

const FIELDS = ["start", "end", "amount", "payment", "commission"] as const;

export function TripDialog(props: Props) {
  return (
    <Modal open={props.open} onClose={props.onClose} title={props.trip ? "Изменить поездку" : "Новая поездка"}>
      <TripForm {...props} />
    </Modal>
  );
}

function TripForm({ scope, onClose, shift, trip, defaultStart }: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  // The percent the commission follows: the trip's own one when editing, else the profile's
  const pct = trip ? (trip.commission_pct ?? null) : scope.commissionPct;
  const manual = pct === null;
  // Generated once per dialog: a retried submit sends the same id, and the server
  // answers "already there" instead of storing the trip twice
  const tripId = useRef(trip?.id ?? uuid());

  const initial: TripFormValues = useMemo(
    () => ({
      start: trip ? isoToLocal(trip.start) : (defaultStart ?? ""),
      end: trip ? isoToLocal(trip.end) : "",
      amount: trip ? String(trip.amount) : "",
      payment: trip?.payment ?? "card",
      commission: trip && manual ? String(trip.commission) : "",
    }),
    [trip, defaultStart, manual],
  );

  const form = useForm<TripFormValues>({ resolver: zodResolver(tripFormSchema(manual)), defaultValues: initial });
  const { register, handleSubmit, setError, formState } = form;
  const amount = useWatch({ control: form.control, name: "amount" });
  const err = formState.errors;

  const save = useMutation({
    mutationFn: async (v: TripFormValues) => {
      if (!trip) {
        const body: TripIn = {
          id: tripId.current,
          shift_id: shift.id,
          start: localToIso(v.start, scope.tz),
          end: localToIso(v.end, scope.tz),
          amount: Number(v.amount),
          payment: v.payment,
          commission: manual ? Number(v.commission) : undefined,
        };
        return request<Trip>("POST", "/api/trips", body);
      }
      // Only what changed; edited times keep the offset they were entered with
      const patch: TripPatch = {};
      if (v.start !== initial.start) patch.start = localWithOffset(v.start, parseOffset(trip.start) ?? 0);
      if (v.end !== initial.end) patch.end = localWithOffset(v.end, parseOffset(trip.end) ?? 0);
      if (v.amount !== initial.amount) patch.amount = Number(v.amount);
      if (v.payment !== initial.payment) patch.payment = v.payment;
      if (manual && v.commission !== initial.commission) patch.commission = Number(v.commission);
      const data = await api<Trip>("PATCH", `${scope.base}/trips/${encodeURIComponent(trip.id)}`, patch);
      return { status: 200, data };
    },
    onSuccess: async ({ status }) => {
      if (trip) toast.ok("Поездка изменена");
      else if (status === 201) toast.ok("Поездка добавлена");
      else toast.info("Такая поездка уже есть — дубль не создан");
      await invalidateDiary(qc, scope);
      onClose();
    },
    onError: (e) => {
      // The admin may have changed the percent while the form was open
      if (e instanceof ApiError && e.fields.some((f) => f.code === "commission_fixed")) {
        void qc.invalidateQueries({ queryKey: meKey });
      }
      const rest = applyServerErrors(e, setError, FIELDS);
      if (rest) toast.err(rest);
    },
  });

  const preview =
    !manual && /^\d+$/.test(amount) && Number(amount) > 0
      ? `${formatPct(pct)} от суммы = ${formatMoney(commissionFor(Number(amount), pct))}`
      : !manual
        ? `${formatPct(pct)} от суммы, считается автоматически`
        : undefined;

  return (
    <form className="form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
      <div className="row">
        <Field label="Начало" error={err.start?.message}>
          <input type="datetime-local" {...register("start")} />
        </Field>
        <Field label="Окончание" error={err.end?.message}>
          <input type="datetime-local" {...register("end")} />
        </Field>
      </div>
      <div className="row">
        <Field label="Сумма, ₸" error={err.amount?.message}>
          <input type="text" inputMode="numeric" autoComplete="off" {...register("amount")} />
        </Field>
        <Field label="Оплата" error={err.payment?.message}>
          <select {...register("payment")}>
            <option value="card">Карта</option>
            <option value="cash">Наличные</option>
          </select>
        </Field>
      </div>
      {manual ? (
        <Field label="Комиссия, ₸" error={err.commission?.message} hint="Процент не задан — введите сумму комиссии">
          <input type="text" inputMode="numeric" autoComplete="off" {...register("commission")} />
        </Field>
      ) : (
        <Field label="Комиссия" error={err.commission?.message}>
          <output className="computed">{preview}</output>
        </Field>
      )}
      <div className="modal-actions">
        <button type="button" onClick={onClose}>
          Отмена
        </button>
        <button type="submit" className="primary" disabled={save.isPending}>
          {trip ? "Сохранить" : "Добавить"}
        </button>
      </div>
    </form>
  );
}
