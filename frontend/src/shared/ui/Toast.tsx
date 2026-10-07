import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Kind = "ok" | "err" | "info";
interface Item {
  id: number;
  kind: Kind;
  text: string;
}

interface Toasts {
  ok: (text: string) => void;
  err: (text: string) => void;
  info: (text: string) => void;
}

const ToastContext = createContext<Toasts | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const next = useRef(1);

  const push = useCallback((kind: Kind, text: string) => {
    const id = next.current++;
    setItems((list) => [...list.slice(-3), { id, kind, text }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), kind === "err" ? 6000 : 3500);
  }, []);

  const api = useMemo<Toasts>(
    () => ({ ok: (t) => push("ok", t), err: (t) => push("err", t), info: (t) => push("info", t) }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "err" ? "alert" : "status"}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Toasts {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return ctx;
}
