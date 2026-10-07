import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/**
 * A native <dialog>: focus trapping, Esc to close and the backdrop come from the browser.
 * The content is mounted only while open, so forms start fresh every time.
 */
export function Modal({ open, onClose, title, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="modal" onClose={onClose} aria-labelledby="modal-title">
      {open && (
        <>
          <header className="modal-head">
            <h2 id="modal-title">{title}</h2>
            <button type="button" className="icon" aria-label="Закрыть" onClick={onClose}>
              ✕
            </button>
          </header>
          {children}
        </>
      )}
    </dialog>
  );
}
