import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/shared/api/client";
import { errorMessage, fieldErrorMessage } from "@/shared/api/errors";

/**
 * Puts a failed request's field errors under the form's own inputs.
 * Returns text for whatever has no input in this form (to show in a toast), or null.
 * `rename` maps server field names to form field names where they differ.
 */
export function applyServerErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  formFields: readonly Path<T>[],
  rename: Partial<Record<string, Path<T>>> = {},
): string | null {
  if (!(err instanceof ApiError) || err.fields.length === 0) return errorMessage(err);
  const rest: string[] = [];
  for (const f of err.fields) {
    const name = (f.field && (rename[f.field] ?? f.field)) as Path<T> | null;
    if (name && formFields.includes(name)) {
      setError(name, { type: "server", message: fieldErrorMessage(f) }, { shouldFocus: true });
    } else {
      rest.push(fieldErrorMessage(f));
    }
  }
  return rest.length ? rest.join("; ") : null;
}
