import { useMemo, useState } from "react";
import type { ErrorLogEntry } from "../../../shared/types";
import { SectionHeader } from "./SectionHeader";

type ErrorPanelProps = {
  className?: string;
  errors: ErrorLogEntry[];
};

export function ErrorPanel({ className = "", errors }: ErrorPanelProps) {
  const [hiddenIds, setHiddenIds] = useState<Set<number>>(new Set());

  const visibleErrors = useMemo(
    () => errors.filter((item) => !hiddenIds.has(item.id)),
    [errors, hiddenIds],
  );

  function hideItem(id: number) {
    setHiddenIds((current) => {
      const next = new Set(current);
      next.add(id);
      return next;
    });
  }

  function resetHidden() {
    setHiddenIds(new Set());
  }

  function prettyDetails(details: string): string {
    const raw = (details || "").trim();
    if (!raw) return "Keine weiteren Details.";
    try {
      const parsed = JSON.parse(raw);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return raw;
    }
  }

  function detailsIsJson(details: string): boolean {
    const raw = (details || "").trim();
    if (!raw) return false;
    try {
      JSON.parse(raw);
      return true;
    } catch {
      return false;
    }
  }

  return (
    <section className={`panel ${className}`.trim()}>
      <SectionHeader
        title="Fehler-Ansicht"
        subtitle="Du kannst jede Meldung ausblenden, damit die Ansicht sauber bleibt."
        action={
          hiddenIds.size > 0 ? (
            <button type="button" className="button-secondary" onClick={resetHidden}>
              Ausgeblendete zurückholen
            </button>
          ) : null
        }
      />
      <div className="error-stack">
        {visibleErrors.length === 0 ? (
          <p className="error-empty">Keine sichtbaren Fehler.</p>
        ) : (
          visibleErrors.slice(0, 20).map((item) => (
            <article key={item.id} className="error-item">
              <div className="error-item-top">
                <span className="error-code">{item.error_code}</span>
                <span className="error-time">{new Date(item.created_at).toLocaleString("de-DE")}</span>
              </div>
              <p className="error-message">{item.message}</p>
              {detailsIsJson(item.details || "") ? (
                <details className="json-viewer" open={item.error_code === "GUARD_BLOCKED"}>
                  <summary>JSON-Details</summary>
                  <pre className="error-details">{prettyDetails(item.details || "")}</pre>
                </details>
              ) : (
                <pre className="error-details">{prettyDetails(item.details || "")}</pre>
              )}
              <div className="error-actions">
                <button type="button" className="button-secondary" onClick={() => hideItem(item.id)}>
                  Ausblenden
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
