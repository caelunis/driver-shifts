import { Navigate, Outlet, useLocation } from "react-router";

import { useMe } from "@/features/auth/api";

export const homeFor = (role: "driver" | "admin") => (role === "admin" ? "/admin/drivers" : "/day");

/** Routes for one role; others are sent to their own home, guests to the login page. */
export function RequireRole({ role }: { role: "driver" | "admin" }) {
  const { data: me, isPending } = useMe();
  const location = useLocation();
  if (isPending) return <p className="loading">Загрузка…</p>;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (me.role !== role) return <Navigate to={homeFor(me.role)} replace />;
  return <Outlet />;
}

export function Home() {
  const { data: me, isPending } = useMe();
  if (isPending) return <p className="loading">Загрузка…</p>;
  return <Navigate to={me ? homeFor(me.role) : "/login"} replace />;
}
