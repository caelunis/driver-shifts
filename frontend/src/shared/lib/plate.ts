// Kazakhstan plates, same rules as the server (backend app/schemas/common.py).

const LOOKALIKES: Record<string, string> = {
  А: "A", В: "B", Е: "E", К: "K", М: "M", Н: "H", О: "O", Р: "P", С: "C", Т: "T", У: "Y", Х: "X",
};
const PLATE = /^\d{3}[A-Z]{2,3}(0[1-9]|1\d|20)$/;

/** " 123 авс-02" -> "123ABC02", or null if it is not a valid plate. */
export function normalizePlate(input: string): string | null {
  const plate = input
    .replace(/[\s-]/g, "")
    .toUpperCase()
    .replace(/[А-Я]/g, (ch) => LOOKALIKES[ch] ?? ch);
  return PLATE.test(plate) ? plate : null;
}

/** "123ABC02" -> "123 ABC 02" */
export const formatPlate = (plate: string | null | undefined) =>
  plate ? plate.replace(/^(\d{3})([A-Z]+)(\d{2})$/, "$1 $2 $3") : "";

/** "Hyundai Accent, 777 AAA 02" */
export const carText = (d: { car_model?: string | null; car_plate?: string | null }) =>
  [d.car_model, formatPlate(d.car_plate)].filter(Boolean).join(", ");
