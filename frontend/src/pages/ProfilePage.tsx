import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { meKey, useMe } from "@/features/auth/api";
import { api } from "@/shared/api/client";
import type { Profile } from "@/shared/api/types";
import { applyServerErrors } from "@/shared/lib/forms";
import { formatPct } from "@/shared/lib/money";
import { formatPlate } from "@/shared/lib/plate";
import { DEFAULT_TZ } from "@/shared/lib/timezones";
import { Field } from "@/shared/ui/Field";
import { TimezoneSelect } from "@/shared/ui/TimezoneSelect";
import { useToast } from "@/shared/ui/Toast";

/** The driver sees their profile; only the timezone is theirs to change. */
export function ProfilePage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const { register, handleSubmit, setError, formState } = useForm<{ default_tz: string }>({
    values: { default_tz: me?.default_tz ?? DEFAULT_TZ },
  });

  const save = useMutation({
    mutationFn: (v: { default_tz: string }) => api<Profile>("PATCH", "/api/me", v),
    onSuccess: (profile) => {
      qc.setQueryData(meKey, profile);
      toast.ok("Профиль сохранён");
    },
    onError: (e) => {
      const rest = applyServerErrors(e, setError, ["default_tz"]);
      if (rest) toast.err(rest);
    },
  });

  if (!me) return null;
  return (
    <div className="narrow">
      <form className="panel form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
        <h2>Профиль</h2>
        <Field label="E-mail">
          <input value={me.email} disabled />
        </Field>
        <Field label="Имя">
          <input value={me.name ?? ""} disabled />
        </Field>
        <div className="row">
          <Field label="Автомобиль">
            <input value={me.car_model ?? ""} placeholder="не указан" disabled />
          </Field>
          <Field label="Госномер">
            <input value={formatPlate(me.car_plate)} placeholder="не указан" disabled />
          </Field>
        </div>
        <Field label="Комиссия">
          <input
            value={me.default_commission_pct == null ? "" : formatPct(me.default_commission_pct)}
            placeholder="не задана — вводится в каждой поездке"
            disabled
          />
        </Field>
        <p className="muted small">Имя, автомобиль и комиссию задаёт администратор.</p>
        <Field
          label="Часовой пояс"
          error={formState.errors.default_tz?.message}
          hint="В нём вводится время смен и поездок"
        >
          <TimezoneSelect {...register("default_tz")} />
        </Field>
        <button type="submit" className="primary wide" disabled={save.isPending || !formState.isDirty}>
          Сохранить
        </button>
      </form>
    </div>
  );
}
