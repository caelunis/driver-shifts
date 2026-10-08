import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";

import { DayView } from "@/features/diary/DayView";
import { adminScope } from "@/features/diary/scope";
import { useDriver } from "@/features/drivers/api";
import { DriverDialog } from "@/features/drivers/DriverDialog";
import { api } from "@/shared/api/client";
import { errorMessage } from "@/shared/api/errors";
import { formatPct } from "@/shared/lib/money";
import { carText } from "@/shared/lib/plate";
import { tripsText } from "@/shared/lib/plural";
import { todayIn } from "@/shared/lib/time";
import { ConfirmDialog } from "@/shared/ui/ConfirmDialog";
import { useToast } from "@/shared/ui/Toast";

/** The admin's view of one driver: profile header and the driver's diary. */
export function DriverDiaryPage() {
  const params = useParams();
  const id = Number(params.id);
  const driver = useDriver(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<"none" | "edit" | "delete">("none");

  const remove = useMutation({
    mutationFn: () => api<void>("DELETE", `/api/admin/drivers/${id}`),
    onSuccess: async () => {
      toast.ok("Водитель удалён");
      await qc.invalidateQueries({ queryKey: ["drivers"] });
      navigate("/admin/drivers");
    },
    onError: (e) => toast.err(errorMessage(e)),
  });

  if (driver.error) {
    return (
      <div className="narrow">
        <p className="panel error-box" role="alert">
          {errorMessage(driver.error)} <Link to="/admin/drivers">К списку</Link>
        </p>
      </div>
    );
  }
  if (!driver.data) return <p className="loading">Загрузка…</p>;

  const d = driver.data;
  const scope = adminScope(d.id, d.default_tz, d.default_commission_pct ?? null);
  // Without a date: the last day with a shift, or today
  if (!params.date) return <Navigate to={scope.dayPath(d.last_trip_day ?? todayIn(d.default_tz))} replace />;

  return (
    <div className="wide">
      <div className="panel driver-head">
        <div>
          <Link to="/admin/drivers" className="muted small">
            ← Все водители
          </Link>
          <h2>{d.name}</h2>
          <p className="muted small">
            {[
              d.email,
              carText(d),
              d.default_commission_pct == null ? "комиссия вручную" : `комиссия ${formatPct(d.default_commission_pct)}`,
              tripsText(d.trips_count),
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="buttons">
          <button type="button" onClick={() => setDialog("edit")}>
            Изменить
          </button>
          <button type="button" className="danger" onClick={() => setDialog("delete")}>
            Удалить
          </button>
        </div>
      </div>

      <DayView scope={scope} day={params.date} onDay={(day) => navigate(scope.dayPath(day))} />

      <DriverDialog open={dialog === "edit"} onClose={() => setDialog("none")} driver={d} />
      <ConfirmDialog
        open={dialog === "delete"}
        title={`Удалить водителя ${d.name}?`}
        confirmText="Удалить"
        busy={remove.isPending}
        onClose={() => setDialog("none")}
        onConfirm={() => remove.mutate()}
      >
        Удалятся аккаунт, все смены и поездки ({tripsText(d.trips_count)}). Отменить нельзя.
      </ConfirmDialog>
    </div>
  );
}
