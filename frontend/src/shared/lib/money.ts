const MONEY = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

/** 12345 -> "12 345 ₸" */
export const formatMoney = (n: number) => `${MONEY.format(n)} ₸`;

/** 15 -> "15%", 12.5 -> "12,5%" */
export const formatPct = (pct: number) =>
  `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(pct)}%`;

/**
 * amount * pct / 100 rounded half up, exactly as the server does it
 * (backend app/services/commission.py). Integer arithmetic: pct has at most
 * two decimals, so 15 -> 1500 hundredths and no float rounding creeps in.
 */
export function commissionFor(amount: number, pct: number): number {
  const hundredths = Math.round(pct * 100);
  return Math.floor((2 * amount * hundredths + 10000) / 20000);
}
