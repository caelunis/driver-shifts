import { useState } from "react";

import type { DayInfo } from "../../shared/api/types";
import { formatMoney } from "../../shared/lib/money";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTH = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" });

interface Props {
  selected: string;
  today: string;
  days: DayInfo[];
  onSelect: (day: string) => void;
}

/** Month grid starting on Monday; days with shifts are marked. */
export function Calendar({ selected, today, days, onSelect }: Props) {
  const [month, setMonth] = useState(selected.slice(0, 7)); // "YYYY-MM"
  const byDay = new Map(days.map((d) => [d.date, d]));

  const [y, m] = month.split("-").map(Number) as [number, number];
  const first = new Date(Date.UTC(y, m - 1, 1));
  const lead = (first.getUTCDay() + 6) % 7; // Monday = 0
  const count = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= count; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);

  const shift = (n: number) => {
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setMonth(d.toISOString().slice(0, 7));
  };
  const title = MONTH.format(first);

  return (
    <div className="calendar">
      <div className="cal-head">
        <button type="button" aria-label="Предыдущий месяц" onClick={() => shift(-1)}>
          ‹
        </button>
        <span className="cal-month">{title[0]!.toUpperCase() + title.slice(1)}</span>
        <button type="button" aria-label="Следующий месяц" onClick={() => shift(1)}>
          ›
        </button>
      </div>
      <div className="cal-grid">
        {WEEKDAYS.map((w) => (
          <span key={w} className="cal-wd">
            {w}
          </span>
        ))}
        {cells.map((day, i) => {
          if (!day) return <span key={`pad-${i}`} />;
          const info = byDay.get(day);
          const cls = ["cal-day", info && "has-data", day === selected && "selected", day === today && "today"]
            .filter(Boolean)
            .join(" ");
          return (
            <button
              key={day}
              type="button"
              className={cls}
              aria-current={day === selected ? "date" : undefined}
              title={info ? `${info.count} поездок · ${formatMoney(info.net)}` : undefined}
              onClick={() => onSelect(day)}
            >
              {Number(day.slice(8))}
            </button>
          );
        })}
      </div>
      <button type="button" className="link" onClick={() => { setMonth(today.slice(0, 7)); onSelect(today); }}>
        Сегодня
      </button>
    </div>
  );
}
