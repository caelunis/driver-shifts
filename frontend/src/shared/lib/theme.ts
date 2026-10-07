// Light, dark, or following the OS ("system": no data-theme attribute).
// public/theme.js applies the saved choice before the first paint.

export type Theme = "light" | "dark" | "system";

export function savedTheme(): Theme {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  try {
    if (theme === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", theme);
  } catch {
    // Storage may be unavailable (private mode): the choice lasts until reload
  }
}

export const NEXT_THEME: Record<Theme, Theme> = { light: "dark", dark: "system", system: "light" };
