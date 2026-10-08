import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/shared/api/client";
import { errorMessage } from "@/shared/api/errors";
import type { Shift, Trip } from "@/shared/api/types";
import { formatMoney } from "@/shared/lib/money";
import { tripsText } from "@/shared/lib/plural";
import { formatDateTime, formatDuration, hhmm, isoDay, isoToLocalCeil } from "@/shared/lib/time";
import { ConfirmDialog } from "@/shared/ui/ConfirmDialog";
import { useToast } from "@/shared/ui/Toast";
import { invalidateDiary, type DiaryScope } from "@/features/diary/scope";
import { TripDialog } from "@/features/trips/TripDialog";
import { TripTable } from "@/features/trips/TripTable";
import { isLockedForDriver } from "@/features/shifts/api";
import { ShiftDialog } from "@/features/shifts/ShiftDialog";

interface Props {
  scope: DiaryScope;
  shift: Shift;
  trips: Trip[];
}

type Dialog =
  | { kind: "none" }
  | { kind: "add-trip" }
  | { kind: "edit-trip"; trip: Trip }
  | { kind: "delete-trip"; trip: Trip }
  | { kind: "edit-shift" }
  | { kind: "close-shift" }
  | { kind: "delete-shift" };

export function ShiftCard({ scope, shift, trips }: Props) {
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const close = () => setDialog({ kind: "none" });

  const open = shift.status === "open";
  const locked = scope.role === "driver" && isLockedForDriver(shift);
  // Only the driver adds trips; the admin corrects existing entries
  const canAdd = scope.role === "driver" && !locked;
  const canEdit = !locked;
  const s = shift.summary;

  const remove = useMutation({
    mutationFn: (path: string) => api<void>("DELETE", path),
    onSuccess: async () => {
      toast.ok(dialog.kind === "delete-shift" ? "Смена удалена" : "Поездка удалена");
      close();
      await invalidateDiary(qc, scope);
    },
    onError: (e) => toast.err(errorMessage(e)),
  });

  const lastEnd = trips.length ? trips[trips.length - 1]!.end : null;
  const end = shift.end
    ? isoDay(shift.end) === shift.local_day
      ? hhmm(shift.end)
      : formatDateTime(shift.end)
    : "сейчас";

  return (
    <article className={open ? "panel shift open" : "panel shift"} aria-label={`Смена ${hhmm(shift.start)}`}>
      <header className="shift-head">
        <div>
          <h3>
            {hhmm(shift.start)} – {end}
            {open && <span className="pill live">идёт</span>}
          </h3>
          <p className="muted small">
            {formatDuration(s.duration_min)} · {tripsText(s.count)}
            {s.net_per_hour != null && ` · ${formatMoney(s.net_per_hour)}/ч`}
            {shift.note && ` · ${shift.note}`}
          </p>
        </div>
        <div className="shift-net">
          <span className="muted small">На руки</span>
          <strong>{formatMoney(s.net)}</strong>
        </div>
      </header>

      {trips.length > 0 ? (
        <TripTable
          trips={trips}
          day={shift.local_day}
          onEdit={canEdit ? (trip) => setDialog({ kind: "edit-trip", trip }) : undefined}
          onDelete={canEdit ? (trip) => setDialog({ kind: "delete-trip", trip }) : undefined}
        />
      ) : (
        <p className="muted empty">Поездок пока нет</p>
      )}

      <footer className="shift-actions">
        {canAdd && (
          <button type="button" className="primary" onClick={() => setDialog({ kind: "add-trip" })}>
            + Поездка
          </button>
        )}
        {open && scope.role === "driver" && (
          <button type="button" onClick={() => setDialog({ kind: "close-shift" })}>
            Закончить смену
          </button>
        )}
        {canEdit && (
          <>
            <button type="button" onClick={() => setDialog({ kind: "edit-shift" })}>
              Изменить смену
            </button>
            <button type="button" className="danger" onClick={() => setDialog({ kind: "delete-shift" })}>
              Удалить смену
            </button>
          </>
        )}
        {locked && <span className="muted small">Прошло больше 7 дней — изменить смену может администратор</span>}
      </footer>

      <TripDialog
        scope={scope}
        open={dialog.kind === "add-trip" || dialog.kind === "edit-trip"}
        onClose={close}
        shift={shift}
        trip={dialog.kind === "edit-trip" ? dialog.trip : undefined}
        defaultStart={isoToLocalCeil(lastEnd ?? shift.start)}
      />
      <ShiftDialog
        scope={scope}
        mode={dialog.kind === "close-shift" ? "close" : "edit"}
        open={dialog.kind === "edit-shift" || dialog.kind === "close-shift"}
        onClose={close}
        shift={shift}
      />
      <ConfirmDialog
        open={dialog.kind === "delete-trip"}
        title="Удалить поездку?"
        confirmText="Удалить"
        busy={remove.isPending}
        onClose={close}
        onConfirm={() =>
          dialog.kind === "delete-trip" &&
          remove.mutate(`${scope.base}/trips/${encodeURIComponent(dialog.trip.id)}`)
        }
      >
        {dialog.kind === "delete-trip" &&
          `${hhmm(dialog.trip.start)}–${hhmm(dialog.trip.end)}, ${formatMoney(dialog.trip.amount)}. Отменить удаление нельзя.`}
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog.kind === "delete-shift"}
        title="Удалить смену?"
        confirmText={trips.length ? `Удалить смену и ${tripsText(trips.length)}` : "Удалить смену"}
        busy={remove.isPending}
        onClose={close}
        onConfirm={() => remove.mutate(`${scope.base}/shifts/${shift.id}`)}
      >
        {trips.length
          ? `Вместе со сменой удалятся все её поездки (${tripsText(trips.length)}). Отменить нельзя.`
          : "Отменить удаление нельзя."}
      </ConfirmDialog>
    </article>
  );
}
