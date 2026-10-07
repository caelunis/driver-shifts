import { Navigate, useNavigate, useParams } from "react-router";

import { useMe } from "../features/auth/api";
import { DayView } from "../features/diary/DayView";
import { driverScope } from "../features/diary/scope";
import { DEFAULT_TZ } from "../shared/lib/timezones";
import { todayIn } from "../shared/lib/time";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The driver's own diary: /day/:date, /day = today. */
export function DiaryPage() {
  const { data: me } = useMe();
  const { date } = useParams();
  const navigate = useNavigate();
  if (!me) return null; // RequireRole has already waited for the profile
  const tz = me.default_tz ?? DEFAULT_TZ;
  if (!date || !DAY.test(date)) return <Navigate to={`/day/${todayIn(tz)}`} replace />;

  const scope = driverScope(tz, me.default_commission_pct ?? null);
  return <DayView scope={scope} day={date} onDay={(d) => navigate(scope.dayPath(d))} />;
}
