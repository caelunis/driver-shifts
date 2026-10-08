import type { DaySummary } from "@/shared/api/types";
import { formatMoney } from "@/shared/lib/money";
import { tripsText } from "@/shared/lib/plural";

export function SummaryCards({ s }: { s: DaySummary }) {
  const cards: [string, string, string?][] = [
    ["На руки", formatMoney(s.net_income), tripsText(s.trips_count)],
    ["Выручка", formatMoney(s.revenue)],
    ["Комиссия", formatMoney(s.commission_total)],
    ["Наличные", formatMoney(s.cash.amount), tripsText(s.cash.trips_count)],
    ["Карта", formatMoney(s.card.amount), tripsText(s.card.trips_count)],
  ];
  return (
    <div className="stats">
      {cards.map(([label, value, sub], i) => (
        <div key={label} className={i === 0 ? "stat main" : "stat"}>
          <span className="stat-label">{label}</span>
          <strong className="stat-value">{value}</strong>
          {sub && <span className="stat-sub">{sub}</span>}
        </div>
      ))}
    </div>
  );
}
