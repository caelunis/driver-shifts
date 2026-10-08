import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useDrivers } from "@/features/drivers/api";
import { DriverDialog } from "@/features/drivers/DriverDialog";
import { errorMessage } from "@/shared/api/errors";
import { formatMoney, formatPct } from "@/shared/lib/money";
import { carText } from "@/shared/lib/plate";
import { formatDay } from "@/shared/lib/time";

export function DriversPage() {
  const [q, setQ] = useState("");
  const query = useDeferredValue(q);
  const drivers = useDrivers(query);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="wide">
      <div className="panel">
        <div className="toolbar">
          <h2>Водители</h2>
          <input
            type="search"
            placeholder="Имя, e-mail, авто или номер"
            aria-label="Поиск водителей"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            + Водитель
          </button>
        </div>

        {drivers.error ? (
          <p className="error-box" role="alert">
            {errorMessage(drivers.error)}
          </p>
        ) : !drivers.data ? (
          <p className="loading">Загрузка…</p>
        ) : drivers.data.length === 0 ? (
          <p className="muted empty">{q.trim() ? "Никого не нашлось" : "Водителей пока нет"}</p>
        ) : (
          <table className="drivers">
            <thead>
              <tr>
                <th>Имя</th>
                <th className="hide-sm">Автомобиль</th>
                <th className="num hide-sm">Комиссия</th>
                <th className="num">Поездок</th>
                <th className="num">На руки</th>
                <th className="hide-sm">Последняя смена</th>
              </tr>
            </thead>
            <tbody>
              {drivers.data.map((d) => (
                <tr key={d.id} className="clickable" onClick={() => navigate(`/admin/drivers/${d.id}`)}>
                  <td>
                    <Link to={`/admin/drivers/${d.id}`} onClick={(e) => e.stopPropagation()}>
                      {d.full_name}
                    </Link>
                    <div className="muted small">{d.email}</div>
                  </td>
                  <td className="hide-sm">{carText(d) || <span className="muted">—</span>}</td>
                  <td className="num hide-sm">
                    {d.commission_percent == null ? <span className="muted">вручную</span> : formatPct(d.commission_percent)}
                  </td>
                  <td className="num">{d.trips_count}</td>
                  <td className="num">{formatMoney(d.net_income)}</td>
                  <td className="hide-sm">{d.last_work_date ? formatDay(d.last_work_date) : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <DriverDialog open={creating} onClose={() => setCreating(false)} onSaved={(d) => navigate(`/admin/drivers/${d.id}`)} />
    </div>
  );
}
