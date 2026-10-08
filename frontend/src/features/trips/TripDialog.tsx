import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { useForm, useWatch } from "react-hook-form";

import { api, API_V1, ApiError, request } from "@/shared/api/client";
import type { Shift, Trip, TripIn, TripPatch } from "@/shared/api/types";
import { applyServerErrors } from "@/shared/lib/forms";
import { commissionFor, formatMoney, formatPct } from "@/shared/lib/money";
import { isoToLocal, localToIso, localWithOffset, parseOffset } from "@/shared/lib/time";
import { uuid } from "@/shared/lib/uuid";
import { Field } from "@/shared/ui/Field";
import { Modal } from "@/shared/ui/Modal";
import { useToast } from "@/shared/ui/Toast";
import { meKey } from "@/features/auth/api";
import { invalidateDiary, type DiaryScope } from "@/features/diary/scope";
import { tripFormSchema, type TripFormValues } from "@/features/trips/schema";

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

const FIELDS = ["started_at", "ended_at", "fare", "payment_method", "commission_amount"] as const;

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
  const pct = trip ? (trip.commission_percent ?? null) : scope.commissionPct;
  const manual = pct === null;
  // Generated once per dialog: a retried submit sends the same id, and the server
  // answers "already there" instead of storing the trip twice
  const tripId = useRef(trip?.id ?? uuid());

  const initial: TripFormValues = useMemo(
    () => ({
      started_at: trip ? isoToLocal(trip.started_at) : (defaultStart ?? ""),
      ended_at: trip ? isoToLocal(trip.ended_at) : "",
      fare: trip ? String(trip.fare) : "",
      payment_method: trip?.payment_method ?? "card",
      commission_amount: trip && manual ? String(trip.commission_amount) : "",
    }),
    [trip, defaultStart, manual],
  );

  const form = useForm<TripFormValues>({ resolver: zodResolver(tripFormSchema(manual)), defaultValues: initial });
  const { register, handleSubmit, setError, formState } = form;
  const fare = useWatch({ control: form.control, name: "fare" });
  const err = formState.errors;

  const save = useMutation({
    mutationFn: async (v: TripFormValues) => {
      if (!trip) {
        const body: TripIn = {
          id: tripId.current,
          shift_id: shift.id,
          started_at: localToIso(v.started_at, scope.tz),
          ended_at: localToIso(v.ended_at, scope.tz),
          fare: Number(v.fare),
          payment_method: v.payment_method,
          commission_amount: manual ? Number(v.commission_amount) : undefined,
        };
        return request<Trip>("POST", `${API_V1}/trips`, body);
      }
      // Only what changed; edited times keep the offset they were entered with
      const patch: TripPatch = {};
      if (v.started_at !== initial.started_at) patch.started_at = localWithOffset(v.started_at, parseOffset(trip.started_at) ?? 0);
      if (v.ended_at !== initial.ended_at) patch.ended_at = localWithOffset(v.ended_at, parseOffset(trip.ended_at) ?? 0);
      if (v.fare !== initial.fare) patch.fare = Number(v.fare);
      if (v.payment_method !== initial.payment_method) patch.payment_method = v.payment_method;
      if (manual && v.commission_amount !== initial.commission_amount) patch.commission_amount = Number(v.commission_amount);
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
    !manual && /^\d+$/.test(fare) && Number(fare) > 0
      ? `${formatPct(pct)} от суммы = ${formatMoney(commissionFor(Number(fare), pct))}`
      : !manual
        ? `${formatPct(pct)} от суммы, считается автоматически`
        : undefined;

  return (
    <form className="form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
      <div className="row">
        <Field label="Начало" error={err.started_at?.message}>
          <input type="datetime-local" {...register("started_at")} />
        </Field>
        <Field label="Окончание" error={err.ended_at?.message}>
          <input type="datetime-local" {...register("ended_at")} />
        </Field>
      </div>
      <div className="row">
        <Field label="Сумма, ₸" error={err.fare?.message}>
          <input type="text" inputMode="numeric" autoComplete="off" {...register("fare")} />
        </Field>
        <Field label="Оплата" error={err.payment_method?.message}>
          <select {...register("payment_method")}>
            <option value="card">Карта</option>
            <option value="cash">Наличные</option>
          </select>
        </Field>
      </div>
      {manual ? (
        <Field label="Комиссия, ₸" error={err.commission_amount?.message} hint="Процент не задан — введите сумму комиссии">
          <input type="text" inputMode="numeric" autoComplete="off" {...register("commission_amount")} />
        </Field>
      ) : (
        <Field label="Комиссия" error={err.commission_amount?.message}>
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
