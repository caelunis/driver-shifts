import { z } from "zod";

export type ShiftDialogMode = "past" | "edit" | "close";

const MAX_SHIFT_MIN = 24 * 60;

/** Values of the shift dialog: datetime-local strings and the note. */
export function shiftFormSchema(mode: ShiftDialogMode) {
  return z
    .object({
      started_at: z.string(),
      ended_at: z.string(),
      note: z.string().max(500, "Не больше 500 символов"),
    })
    .superRefine((v, ctx) => {
      if (mode !== "close" && !v.started_at) {
        ctx.addIssue({ code: "custom", path: ["started_at"], message: "Укажите начало" });
      }
      if (mode === "past" && !v.ended_at) {
        ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Укажите окончание" });
      }
      if (v.started_at && v.ended_at) {
        const minutes = (Date.parse(v.ended_at) - Date.parse(v.started_at)) / 60000;
        if (minutes <= 0) {
          ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Окончание должно быть позже начала" });
        } else if (minutes > MAX_SHIFT_MIN) {
          ctx.addIssue({ code: "custom", path: ["ended_at"], message: "Смена длится не больше 24 часов" });
        }
      }
    });
}

export type ShiftFormValues = z.infer<ReturnType<typeof shiftFormSchema>>;
