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
      start: z.string().min(1, "Укажите начало"),
      end: z.string().min(1, "Укажите окончание"),
      amount: z.string().min(1, "Укажите сумму").regex(INT, "Введите сумму целым числом"),
      payment: z.enum(["card", "cash"]),
      commission: z.string(),
    })
    .superRefine((v, ctx) => {
      const amount = Number(v.amount);
      if (INT.test(v.amount)) {
        if (amount <= 0) ctx.addIssue({ code: "custom", path: ["amount"], message: "Сумма должна быть больше 0" });
        if (amount > MAX_AMOUNT) {
          ctx.addIssue({ code: "custom", path: ["amount"], message: "Не больше 500 000 ₸" });
        }
      }
      if (v.start && v.end) {
        const minutes = (Date.parse(v.end) - Date.parse(v.start)) / 60000;
        if (minutes <= 0) {
          ctx.addIssue({ code: "custom", path: ["end"], message: "Окончание должно быть позже начала" });
        } else if (minutes < MIN_TRIP_MIN) {
          ctx.addIssue({ code: "custom", path: ["end"], message: "Поездка длится не меньше минуты" });
        } else if (minutes > MAX_TRIP_MIN) {
          ctx.addIssue({ code: "custom", path: ["end"], message: "Поездка длится не больше 6 часов" });
        }
      }
      if (manualCommission) {
        if (!v.commission) {
          ctx.addIssue({ code: "custom", path: ["commission"], message: "Укажите комиссию" });
        } else if (!INT.test(v.commission)) {
          ctx.addIssue({ code: "custom", path: ["commission"], message: "Введите комиссию целым числом" });
        } else if (INT.test(v.amount) && Number(v.commission) >= amount) {
          ctx.addIssue({ code: "custom", path: ["commission"], message: "Комиссия должна быть меньше суммы" });
        }
      }
    });
}

export type TripFormValues = z.infer<ReturnType<typeof tripFormSchema>>;
