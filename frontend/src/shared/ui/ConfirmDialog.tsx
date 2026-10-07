import type { ReactNode } from "react";

import { Modal } from "./Modal";

interface Props {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmText: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** "Are you sure?" for destructive actions. */
export function ConfirmDialog({ open, title, children, confirmText, busy, onConfirm, onClose }: Props) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="confirm-text">{children}</div>
      <div className="modal-actions">
        <button type="button" onClick={onClose}>
          Отмена
        </button>
        <button type="button" className="danger solid" disabled={busy} onClick={onConfirm}>
          {confirmText}
        </button>
      </div>
    </Modal>
  );
}
