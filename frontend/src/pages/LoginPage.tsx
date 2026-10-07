import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router";
import { z } from "zod";

import { homeFor } from "../app/guards";
import { useLogin, useMe } from "../features/auth/api";
import { ApiError } from "../shared/api/client";
import { errorMessage } from "../shared/api/errors";
import { applyServerErrors } from "../shared/lib/forms";
import { Field } from "../shared/ui/Field";

const schema = z.object({
  email: z.email("Введите e-mail"),
  password: z.string().min(1, "Введите пароль"),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { data: me } = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const { register, handleSubmit, setError, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  if (me) return <Navigate to={homeFor(me.role)} replace />;

  const onSubmit = handleSubmit((v) =>
    login.mutate(v, {
      onSuccess: (profile) => navigate(from && from !== "/login" ? from : homeFor(profile.role), { replace: true }),
      onError: (e) => {
        applyServerErrors(e, setError, ["email", "password"]);
      },
    }),
  );
  // Wrong password, rate limit, network: one message above the button
  const fieldErrors = login.error instanceof ApiError && login.error.fields.length > 0;
  const formError = login.error && !fieldErrors ? errorMessage(login.error) : null;

  return (
    <div className="narrow">
      <form className="panel form" noValidate onSubmit={onSubmit} aria-label="Вход">
        <h2>Вход</h2>
        <Field label="E-mail" error={formState.errors.email?.message}>
          <input type="email" autoComplete="username" autoFocus {...register("email")} />
        </Field>
        <Field label="Пароль" error={formState.errors.password?.message}>
          <input type="password" autoComplete="current-password" {...register("password")} />
        </Field>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <button type="submit" className="primary wide" disabled={login.isPending}>
          Войти
        </button>
        <p className="muted small">Аккаунт создаёт администратор.</p>
      </form>
    </div>
  );
}
