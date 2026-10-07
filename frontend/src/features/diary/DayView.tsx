import { errorMessage } from "../../shared/api/errors";
import { addDays, formatDay, todayIn } from "../../shared/lib/time";
import { CurrentShiftBar } from "../shifts/CurrentShiftBar";
import { ShiftCard } from "../shifts/ShiftCard";
import { useDay, useDays } from "./api";
import { Calendar } from "./Calendar";
import type { DiaryScope } from "./scope";
import { SummaryCards } from "./SummaryCards";

interface Props {
  scope: DiaryScope;
  day: string;
  onDay: (day: string) => void;
}

/** A diary day: calendar on the side; the day's totals and its shifts with trips. */
export function DayView({ scope, day, onDay }: Props) {
  const today = todayIn(scope.tz);
  const days = useDays(scope);
  const { summary, shifts, trips } = useDay(scope, day);
  const failed = summary.error ?? shifts.error ?? trips.error;

  return (
    <div className="diary">
      <aside className="side panel">
        <Calendar key={day.slice(0, 7)} selected={day} today={today} days={days.data ?? []} onSelect={onDay} />
      </aside>

      <section className="day">
        {scope.role === "driver" && <CurrentShiftBar scope={scope} onDay={onDay} />}

        <div className="day-head">
          <button type="button" aria-label="Предыдущий день" onClick={() => onDay(addDays(day, -1))}>
            ‹
          </button>
          <h2>
            {formatDay(day)}
            {day === today && <span className="pill">сегодня</span>}
          </h2>
          <button type="button" aria-label="Следующий день" onClick={() => onDay(addDays(day, 1))}>
            ›
          </button>
        </div>

        {failed ? (
          <p className="panel error-box" role="alert">
            {errorMessage(failed)}
          </p>
        ) : !summary.data || !shifts.data || !trips.data ? (
          <p className="loading">Загрузка…</p>
        ) : (
          <>
            {summary.data.shifts > 0 && <SummaryCards s={summary.data} />}
            {shifts.data.length === 0 && (
              <p className="panel muted empty">
                В этот день смен нет.
                {scope.role === "driver" && " Начните смену или внесите прошедшую."}
              </p>
            )}
            {shifts.data.map((shift) => (
              <ShiftCard
                key={shift.id}
                scope={scope}
                shift={shift}
                trips={trips.data.filter((t) => t.shift_id === shift.id)}
              />
            ))}
          </>
        )}
      </section>
    </div>
  );
}
