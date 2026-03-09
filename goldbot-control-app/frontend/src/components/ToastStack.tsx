import type { ToastMessage } from "../types/viewModels";

type ToastStackProps = {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
};

const KIND_ICON: Record<ToastMessage["kind"], string> = {
  success: "✓",
  error: "✕",
  info: "ℹ",
};

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div className="toast-stack" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.kind}`}>
          <div className="toast-body">
            <span className="toast-icon">{KIND_ICON[toast.kind]}</span>
            <p>{toast.text}</p>
          </div>
          <button type="button" className="toast-dismiss" onClick={() => onDismiss(toast.id)}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
