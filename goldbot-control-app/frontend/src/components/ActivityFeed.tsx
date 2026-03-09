import { useMemo, useState } from "react";
import type { ActionLogEntry } from "../../../shared/types";
import { SectionHeader } from "./SectionHeader";

type ActivityFeedProps = {
  className?: string;
  actions: ActionLogEntry[];
};

type FilterValue = "all" | "success" | "blocked" | "failed";
type GroupedAction = {
  key: string;
  count: number;
  latest: ActionLogEntry;
};

const FILTERS: FilterValue[] = ["all", "success", "blocked", "failed"];

const FILTER_LABELS: Record<FilterValue, string> = {
  all: "ALLE",
  success: "ERFOLG",
  blocked: "BLOCKIERT",
  failed: "FEHLER",
};

export function ActivityFeed({ className = "", actions }: ActivityFeedProps) {
  const [filter, setFilter] = useState<FilterValue>("all");

  const visibleItems = useMemo<GroupedAction[]>(() => {
    const filtered =
      filter === "all"
        ? actions.slice(0, 60)
        : actions.filter((item) => item.status === filter).slice(0, 60);

    const grouped = new Map<string, GroupedAction>();
    for (const item of filtered) {
      const key = `${item.command_type}|${item.status}|${item.message}`;
      const existing = grouped.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        grouped.set(key, { key, count: 1, latest: item });
      }
    }
    return [...grouped.values()].slice(0, 20);
  }, [actions, filter]);

  return (
    <section className={`panel ${className}`.trim()}>
      <SectionHeader title="Aktivitäts-Feed" subtitle="Letzte Kommandos und deren Ergebnis" />
      <div className="feed-filter-row">
        {FILTERS.map((item) => (
          <button
            type="button"
            key={item}
            className={`chip ${item === filter ? "chip-active" : ""}`}
            onClick={() => setFilter(item)}
          >
            {FILTER_LABELS[item]}
          </button>
        ))}
      </div>
      <ul className="activity-list">
        {visibleItems.length === 0 ? (
          <li className="activity-empty">Keine Aktivität für diesen Filter.</li>
        ) : (
          visibleItems.map((item) => (
            <li key={item.key} className={`activity-row status-${item.latest.status}`}>
              <div>
                <p className="activity-command">
                  <span>{item.latest.command_type}</span>
                  {item.count > 1 ? <span className="activity-repeat">({item.count}x)</span> : null}
                </p>
                <p className="activity-time">
                  {new Date(item.latest.executed_at).toLocaleString("de-DE")} - {item.latest.requested_by}
                </p>
              </div>
              <div className="activity-status">
                <span className={`status-pill status-${item.latest.status}`}>{item.latest.status}</span>
                <span className="activity-message">{item.latest.message}</span>
              </div>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
