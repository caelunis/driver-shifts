import type { Trip } from "@/shared/api/types";
import { formatMoney } from "@/shared/lib/money";
import { formatDuration, hhmm, isoDay, minutesBetween } from "@/shared/lib/time";

interface Props {
  trips: Trip[];
  /** Local day of the shift: a trip after midnight shows its date */
  day: string;
  onEdit?: (trip: Trip) => void;
  onDelete?: (trip: Trip) => void;
}

export function TripTable({ trips, day, onEdit, onDelete }: Props) {
  const actions = Boolean(onEdit || onDelete);
  const time = (iso: string) => (isoDay(iso) === day ? hhmm(iso) : `${hhmm(iso)} (${isoDay(iso).slice(8)}.${isoDay(iso).slice(5, 7)})`);
  return (
    <table className="trips">
      <thead>
        <tr>
          <th>Время</th>
          <th className="num">Сумма</th>
          <th className="hide-sm">Оплата</th>
          <th className="num hide-sm">Комиссия</th>
          <th className="num">На руки</th>
          {actions && <th aria-label="Действия" />}
        </tr>
      </thead>
      <tbody>
        {trips.map((t) => (
          <tr key={t.id}>
            <td className="time">
              {time(t.started_at)}–{time(t.ended_at)}
              <span className="muted small hide-sm"> · {formatDuration(minutesBetween(t.started_at, t.ended_at))}</span>
              {/* The payment column is hidden on phones: shown under the time instead */}
              <span className={`pay ${t.payment_method} small show-sm`}>{t.payment_method === "cash" ? "Наличные" : "Карта"}</span>
            </td>
            <td className="num">{formatMoney(t.fare)}</td>
            <td className="hide-sm">
              <span className={`pay ${t.payment_method}`}>{t.payment_method === "cash" ? "Наличные" : "Карта"}</span>
            </td>
            <td className="num hide-sm">{formatMoney(t.commission_amount)}</td>
            <td className="num strong">{formatMoney(t.fare - t.commission_amount)}</td>
            {actions && (
              <td className="row-actions">
                {onEdit && (
                  <button
                    type="button"
                    className="small icon-btn"
                    aria-label="Изменить поездку"
                    title="Изменить"
                    onClick={() => onEdit(t)}
                  >
                    ✎
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    className="small danger icon-btn"
                    aria-label="Удалить поездку"
                    title="Удалить"
                    onClick={() => onDelete(t)}
                  >
                    ✕
                  </button>
                )}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
