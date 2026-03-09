import { useEffect } from "react";
import type { ActionLogEntry } from "../../../shared/types";
import type { TradeVisualPoint } from "../types/viewModels";
import { ChartPanel } from "./ChartPanel";

type TradeChartModalProps = {
  isOpen: boolean;
  onClose: () => void;
  series: TradeVisualPoint[];
  actions?: ActionLogEntry[];
  inline?: boolean;
};

export function TradeChartModal({ isOpen, onClose, series, actions = [], inline }: TradeChartModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (inline) {
    return <ChartPanel series={series} actions={actions} />;
  }

  if (!isOpen) return null;

  return (
    <div className="trade-modal-backdrop" onClick={onClose}>
      <div className="trade-modal-content" onClick={(event) => event.stopPropagation()}>
        <div className="trade-modal-top">
          <h3>Trade-Chart</h3>
          <button type="button" className="button-secondary btn-sm" onClick={onClose}>
            ✕ Schließen
          </button>
        </div>
        <ChartPanel className="trade-modal-panel" series={series} actions={actions} />
      </div>
    </div>
  );
}
