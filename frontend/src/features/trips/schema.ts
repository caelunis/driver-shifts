import { z } from "zod";

// The same limits as the server (backend app/schemas/trips.py). The server stays the
// authority; these checks only save a round trip for obvious mistakes.
export const MAX_AMOUNT = 500_000;
export const MIN_TRIP_MIN = 1;
export const MAX_TRIP_MIN = 6 * 60;

const INT = /^\d+$/;

/** Form values as typed: datetime-local strings and digits. */
export function tripFormSchema(manualCommission: boolean) {
  return z
    .object({
      started_at: z.string().min(1, "Укажите начало"),
      ended_at: z.string().min(1, "Укажите окончание"),
      fare: z.string().min(1, "Укажите сумму").regex(INT, "Введите сумму целым числом"),
      payment_method: z.enum(["card", "cash"]),
      commission_amount: z.string(),
    })
    .superRefine((v, ctx) => {
      const fare = Number(v.fare);
      if (INT.test(v.fare)) {
        if (fare <= 0) ctx.addIssue({ code: "custom", path: ["fare"], message: "Сумма должна быть больше 0" });
        if (fare > MAX_AMOUNT) {
          ctx.addIssue({ code: "custom", path: ["fare"], message: "Не больше 500 000 ₸" });
        }
      }
      if (v.started_at && v.ended_at) {
        const minutes = (Date.parse(v.ended_at) - Date.parse(v.started_at)) / 60000;
        if (minutes <= 0) {
          ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Окончание должно быть позже начала" });
        } else if (minutes < MIN_TRIP_MIN) {
          ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Поездка длится не меньше минуты" });
        } else if (minutes > MAX_TRIP_MIN) {
          ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Поездка длится не больше 6 часов" });
        }
      }
      if (manualCommission) {
        if (!v.commission_amount) {
          ctx.addIssue({ code: "custom", path: ["commission_amount"], message: "Укажите комиссию" });
        } else if (!INT.test(v.commission_amount)) {
          ctx.addIssue({ code: "custom", path: ["commission_amount"], message: "Введите комиссию целым числом" });
        } else if (INT.test(v.fare) && Number(v.commission_amount) >= fare) {
          ctx.addIssue({ code: "custom", path: ["commission_amount"], message: "Комиссия должна быть меньше суммы" });
        }
      }
    });
}

export type TripFormValues = z.infer<ReturnType<typeof tripFormSchema>>;
