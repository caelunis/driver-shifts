import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api, ApiError } from "@/shared/api/client";
import { errorMessage } from "@/shared/api/errors";
import type { DriverCreate, DriverInfo, DriverUpdate } from "@/shared/api/types";
import { applyServerErrors } from "@/shared/lib/forms";
import { formatPlate, normalizePlate } from "@/shared/lib/plate";
import { DEFAULT_TZ } from "@/shared/lib/timezones";
import { Field } from "@/shared/ui/Field";
import { Modal } from "@/shared/ui/Modal";
import { TimezoneSelect } from "@/shared/ui/TimezoneSelect";
import { useToast } from "@/shared/ui/Toast";
import { driverFormSchema, parsePct, type DriverFormValues } from "@/features/drivers/schema";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Set when editing */
  driver?: DriverInfo;
  onSaved?: (driver: DriverInfo) => void;
}

const FIELDS = ["email", "password", "name", "car_model", "car_plate", "default_tz", "default_commission_pct"] as const;
const CONFLICT_FIELDS: Record<string, "email" | "car_plate"> = { email_taken: "email", plate_taken: "car_plate" };

export function DriverDialog(props: Props) {
  return (
    <Modal open={props.open} onClose={props.onClose} title={props.driver ? "Изменить водителя" : "Новый водитель"}>
      <DriverForm {...props} />
    </Modal>
  );
}

function DriverForm({ onClose, driver, onSaved }: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const creating = !driver;
  const { register, handleSubmit, setError, formState } = useForm<DriverFormValues>({
    resolver: zodResolver(driverFormSchema(creating)),
    defaultValues: {
      email: driver?.email ?? "",
      password: "",
      name: driver?.name ?? "",
      car_model: driver?.car_model ?? "",
      car_plate: formatPlate(driver?.car_plate),
      default_tz: driver?.default_tz ?? DEFAULT_TZ,
      default_commission_pct: driver?.default_commission_pct == null ? "" : String(driver.default_commission_pct),
    },
  });
  const err = formState.errors;

  const save = useMutation({
    mutationFn: (v: DriverFormValues) => {
      const profile = {
        name: v.name.trim(),
        car_model: v.car_model.trim(),
        car_plate: v.car_plate.trim() ? normalizePlate(v.car_plate) : null,
        default_tz: v.default_tz,
        default_commission_pct: parsePct(v.default_commission_pct),
      };
      if (creating) {
        const body: DriverCreate = { ...profile, email: v.email.trim(), password: v.password };
        return api<DriverInfo>("POST", "/api/admin/drivers", body);
      }
      const body: DriverUpdate = v.password ? { ...profile, password: v.password } : profile;
      return api<DriverInfo>("PATCH", `/api/admin/drivers/${driver.id}`, body);
    },
    onSuccess: async (saved, v) => {
      toast.ok(
        creating
          ? `Водитель ${saved.name} добавлен`
          : v.password
            ? "Сохранено, пароль изменён — водитель выйдет со всех устройств"
            : "Сохранено",
      );
      await qc.invalidateQueries({ queryKey: ["drivers"] });
      onSaved?.(saved);
      onClose();
    },
    onError: (e) => {
      // A taken email or plate is a 409 without field errors: put it under its input
      const conflictField = e instanceof ApiError ? CONFLICT_FIELDS[e.code] : undefined;
      if (conflictField) return setError(conflictField, { message: errorMessage(e) }, { shouldFocus: true });
      const rest = applyServerErrors(e, setError, FIELDS);
      if (rest) toast.err(rest);
    },
  });

  return (
    <form className="form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
      <Field label="E-mail" error={err.email?.message} hint={creating ? "Это логин водителя" : "Логин не меняется"}>
        <input type="email" autoComplete="off" disabled={!creating} {...register("email")} />
      </Field>
      <Field
        label={creating ? "Временный пароль" : "Новый пароль"}
        error={err.password?.message}
        hint={
          creating
            ? "Не меньше 8 символов, не e-mail и не «12345678». Передайте его водителю."
            : "Пусто — не менять. После смены водитель выйдет со всех устройств."
        }
      >
        <input type="text" autoComplete="new-password" spellCheck={false} {...register("password")} />
      </Field>
      <Field label="Имя" error={err.name?.message}>
        <input type="text" maxLength={100} {...register("name")} />
      </Field>
      <div className="row">
        <Field label="Автомобиль" error={err.car_model?.message}>
          <input type="text" maxLength={100} placeholder="Toyota Camry" {...register("car_model")} />
        </Field>
        <Field label="Госномер" error={err.car_plate?.message}>
          <input type="text" maxLength={12} placeholder="123 ABC 02" autoComplete="off" {...register("car_plate")} />
        </Field>
      </div>
      <div className="row">
        <Field label="Комиссия, %" error={err.default_commission_pct?.message} hint="Пусто — водитель вводит сам">
          <input type="text" inputMode="decimal" placeholder="не задана" {...register("default_commission_pct")} />
        </Field>
        <Field label="Часовой пояс" error={err.default_tz?.message}>
          <TimezoneSelect {...register("default_tz")} />
        </Field>
      </div>
      <div className="modal-actions">
        <button type="button" onClick={onClose}>
          Отмена
        </button>
        <button type="submit" className="primary" disabled={save.isPending}>
          {creating ? "Создать" : "Сохранить"}
        </button>
      </div>
    </form>
  );
}
