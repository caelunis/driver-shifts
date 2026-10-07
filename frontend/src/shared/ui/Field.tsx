import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";

interface Props {
  label: string;
  error?: string;
  hint?: ReactNode;
  /** One input, select, textarea or output */
  children: ReactElement<Record<string, unknown>>;
}

/**
 * Label, input and the input's error right under it. The hint and the error are tied
 * to the input with aria-describedby rather than placed inside the label, so the
 * input's accessible name is just the label ("Пароль", not "Пароль Не меньше 8…").
 */
export function Field({ label, error, hint, children }: Props) {
  const id = useId();
  const noteId = `${id}-note`;
  const note = error ?? hint;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": note ? noteId : undefined,
      })
    : children;

  return (
    <div className={error ? "field invalid" : "field"}>
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {control}
      {error ? (
        <small id={noteId} className="field-error" role="alert">
          {error}
        </small>
      ) : (
        hint && (
          <small id={noteId} className="field-hint">
            {hint}
          </small>
        )
      )}
    </div>
  );
}
