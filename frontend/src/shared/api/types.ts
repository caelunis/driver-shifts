// Shorthands for the generated OpenAPI types (schema.d.ts; regenerate with `npm run gen:api`).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Profile = Schemas["Profile"];
export type Trip = Schemas["Trip"];
export type TripIn = Schemas["TripIn"];
export type TripPatch = Schemas["TripPatch"];
export type Shift = Schemas["Shift"];
export type ShiftDetail = Schemas["ShiftDetail"];
export type ShiftStartIn = Schemas["ShiftStartIn"];
export type ShiftPatch = Schemas["ShiftPatch"];
export type DaySummary = Schemas["DaySummary"];
export type DayInfo = Schemas["DayInfo"];
export type DriverInfo = Schemas["DriverInfo"];
export type DriverCreate = Schemas["DriverCreate"];
export type DriverUpdate = Schemas["DriverUpdate"];
export type Payment = Trip["payment"];

// The error body is the same for every endpoint (backend app/core/errors.py); FastAPI's
// generated schema still describes its default 422 shape, so this one is written by hand.
export interface FieldError {
  field: string | null;
  code: string;
  message: string;
  ctx: Record<string, unknown>;
}

export interface ErrorBody {
  error: {
    code: string;
    message: string;
    fields: FieldError[];
    ctx: Record<string, unknown>;
  };
}
