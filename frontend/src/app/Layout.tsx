import { Link, NavLink, Outlet, useNavigate } from "react-router";

import { useLogout, useMe } from "../features/auth/api";
import { carText } from "../shared/lib/plate";
import { ThemeToggle } from "../shared/ui/ThemeToggle";
import { useToast } from "../shared/ui/Toast";

export function Layout() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const toast = useToast();
  const admin = me?.role === "admin";

  return (
    <>
      <header className="topbar">
        <h1>
          <Link to="/">Дневник смен</Link>
        </h1>
        <nav className="topbar-actions">
          {me && !admin && (
            <>
              <NavLink to="/day" className="btn">
                Дневник
              </NavLink>
              <NavLink to="/profile" className="btn">
                Профиль
              </NavLink>
            </>
          )}
          {admin && (
            <>
              <span className="badge">Администратор</span>
              <NavLink to="/admin/drivers" className="btn">
                Водители
              </NavLink>
            </>
          )}
          {me && (
            <span className="who" title={me.email}>
              {admin ? me.email : [me.name, carText(me)].filter(Boolean).join(" · ")}
            </span>
          )}
          <ThemeToggle />
          {me && (
            <button
              type="button"
              disabled={logout.isPending}
              onClick={() =>
                logout.mutate(undefined, {
                  onSuccess: () => navigate("/login"),
                  onError: () => toast.err("Не удалось выйти, попробуйте ещё раз"),
                })
              }
            >
              Выйти
            </button>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
