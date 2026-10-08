import { z } from "zod";

import { normalizePlate } from "@/shared/lib/plate";

// Mirrors the server's rules (backend app/schemas/accounts.py); the server has the last word,
// e.g. on the list of common passwords.

/** `creating`: email and password are required; when editing, an empty password keeps the old one. */
export function driverFormSchema(creating: boolean) {
  return z
    .object({
      email: creating ? z.email("Некорректный e-mail") : z.string(),
      password: z.string().max(128, "Не больше 128 символов"),
      name: z
        .string()
        .trim()
        .min(1, "Укажите имя")
        .max(100, "Не больше 100 символов")
        .refine((v) => /\p{L}/u.test(v), "Имя должно содержать буквы"),
      car_model: z.string().trim().max(100, "Не больше 100 символов"),
      car_plate: z.string().refine((v) => !v.trim() || normalizePlate(v) !== null, "Номер в формате 123 ABC 02"),
      default_tz: z.string().min(1, "Выберите часовой пояс"),
      default_commission_pct: z
        .string()
        .refine((v) => {
          if (!v.trim()) return true;
          const n = Number(v.replace(",", "."));
          return Number.isFinite(n) && n >= 0 && n < 100;
        }, "От 0 до 99,99"),
    })
    .superRefine((v, ctx) => {
      if (creating && v.password.length < 8) {
        ctx.addIssue({ code: "custom", path: ["password"], message: "Не меньше 8 символов" });
      } else if (!creating && v.password && v.password.length < 8) {
        ctx.addIssue({ code: "custom", path: ["password"], message: "Не меньше 8 символов" });
      }
    });
}

export type DriverFormValues = z.input<ReturnType<typeof driverFormSchema>>;

/** "" -> null, "12,5" -> 12.5 */
export const parsePct = (v: string) => (v.trim() ? Number(v.replace(",", ".")) : null);
