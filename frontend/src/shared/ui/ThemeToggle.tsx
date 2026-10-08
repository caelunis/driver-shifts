import { useState } from "react";

import { applyTheme, NEXT_THEME, savedTheme, type Theme } from "@/shared/lib/theme";

const LABELS: Record<Theme, { text: string; title: string }> = {
  light: { text: "☀️ Светлая", title: "Тема: светлая. Нажмите для тёмной" },
  dark: { text: "🌙 Тёмная", title: "Тема: тёмная. Нажмите, чтобы следовать системе" },
  system: { text: "🖥 Как в системе", title: "Тема: как в системе. Нажмите для светлой" },
};

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(savedTheme);
  const { text, title } = LABELS[theme];
  return (
    <button
      type="button"
      title={title}
      onClick={() => {
        const next = NEXT_THEME[theme];
        applyTheme(next);
        setTheme(next);
      }}
    >
      {text}
    </button>
  );
}
