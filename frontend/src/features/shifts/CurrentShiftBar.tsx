import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, API_V1 } from "@/shared/api/client";
import { errorMessage } from "@/shared/api/errors";
import type { Shift } from "@/shared/api/types";
import { formatMoney } from "@/shared/lib/money";
import { tripsText } from "@/shared/lib/plural";
import { formatDateTime, formatDuration, isoDay } from "@/shared/lib/time";
import { useToast } from "@/shared/ui/Toast";
import { invalidateDiary, type DiaryScope } from "@/features/diary/scope";
import { DAY_MS, useCurrentShift } from "@/features/shifts/api";
import { ShiftDialog } from "@/features/shifts/ShiftDialog";

interface Props {
  scope: DiaryScope;
  /** Go to a day of the diary */
  onDay: (day: string) => void;
}

/** The driver's open shift with its running totals, or buttons to start one. */
export function CurrentShiftBar({ scope, onDay }: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: current, isPending } = useCurrentShift();
  const [dialog, setDialog] = useState<"none" | "past" | "close">("none");

  const started_at = useMutation({
    mutationFn: () => api<Shift>("POST", `${API_V1}/shifts`, {}),
    onSuccess: async (shift) => {
      toast.ok("Смена началась");
      await invalidateDiary(qc, scope);
      onDay(isoDay(shift.started_at));
    },
    onError: (e) => toast.err(errorMessage(e)),
  });

  if (isPending) return <div className="panel current-shift muted">Загрузка…</div>;

  const forgotten = current != null && Date.now() - Date.parse(current.started_at) > DAY_MS;

  return (
    <section className={current ? "panel current-shift live" : "panel current-shift"} aria-label="Текущая смена">
      {current ? (
        <div className="current-body">
          <div>
            <strong>Смена идёт</strong> с {formatDateTime(current.started_at)} ·{" "}
            {formatDuration(current.summary.duration_minutes)}
            <div className="muted small">
              {tripsText(current.summary.trips_count)} · на руки {formatMoney(current.summary.net_income)}
              {" · "}
              <Link to={scope.dayPath(current.work_date)}>к смене</Link>
            </div>
          </div>
          <button type="button" className="primary" onClick={() => setDialog("close")}>
            Закончить смену
          </button>
        </div>
      ) : (
        <div className="current-body">
          <span className="muted">Смена не начата</span>
          <div className="buttons">
            <button type="button" className="primary" disabled={started_at.isPending} onClick={() => started_at.mutate()}>
              Начать смену
            </button>
            <button type="button" onClick={() => setDialog("past")}>
              Внести прошедшую
            </button>
          </div>
        </div>
      )}
      {forgotten && (
        <p className="warning" role="alert">
          Смена открыта больше суток — похоже, её забыли закончить. Укажите, когда она закончилась.
        </p>
      )}
      {current && (
        <button type="button" className="link small" onClick={() => setDialog("past")}>
          Внести прошедшую смену
        </button>
      )}

      <ShiftDialog
        scope={scope}
        mode={dialog === "close" ? "close" : "past"}
        open={dialog !== "none"}
        onClose={() => setDialog("none")}
        shift={dialog === "close" ? (current ?? undefined) : undefined}
        onSaved={onDay}
      />
    </section>
  );
}
