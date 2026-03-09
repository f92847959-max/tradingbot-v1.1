import { useEffect, useMemo, useState } from "react";
import type { CommandType } from "../../../shared/types";
import { SectionHeader } from "./SectionHeader";

type QuickActionItem = {
  type: CommandType;
  icon: string;
  label: string;
  sublabel: string;
  critical: boolean;
  primary?: boolean;
};

type QuickActionsPanelProps = {
  className?: string;
  isRefreshing: boolean;
  onQuickAction: (
    commandType: CommandType,
    confirmToken?: string,
    sourceElement?: HTMLElement,
  ) => Promise<void>;
  onOpenChart: () => void;
};

const ACTIONS: QuickActionItem[] = [
  { type: "START_BOT", icon: "▶", label: "Start", sublabel: "Bot starten", critical: false, primary: true },
  { type: "STOP_BOT", icon: "■", label: "Stop", sublabel: "Bot stoppen", critical: true },
  { type: "PAUSE_TRADING", icon: "⏸", label: "Pause", sublabel: "Trading pausieren", critical: false },
  { type: "RESUME_TRADING", icon: "⏵", label: "Fortsetzen", sublabel: "Trading fortsetzen", critical: false },
  { type: "RELOAD_CONFIG", icon: "↻", label: "Neu laden", sublabel: "Config neu laden", critical: true },
  { type: "EMERGENCY_STOP", icon: "⛔", label: "Not-Aus", sublabel: "Sofortiger Stopp", critical: true },
];

const ARM_WINDOW_MS = 5000;
const COOLDOWN_MS = 2200;

export function QuickActionsPanel({
  className = "",
  isRefreshing,
  onQuickAction,
  onOpenChart,
}: QuickActionsPanelProps) {
  const [armedType, setArmedType] = useState<CommandType | null>(null);
  const [armedUntil, setArmedUntil] = useState<number>(0);
  const [isSending, setIsSending] = useState(false);
  const [clock, setClock] = useState<number>(Date.now());
  const [cooldownUntil, setCooldownUntil] = useState<Record<string, number>>({});

  const remainingSeconds = useMemo(() => {
    if (!armedType) return 0;
    return Math.max(0, Math.ceil((armedUntil - clock) / 1000));
  }, [armedType, armedUntil, clock]);

  useEffect(() => {
    const ticker = window.setInterval(() => setClock(Date.now()), 160);
    return () => window.clearInterval(ticker);
  }, []);

  useEffect(() => {
    if (!armedType) return;
    const timeout = window.setTimeout(() => {
      setArmedType(null);
      setArmedUntil(0);
    }, ARM_WINDOW_MS);
    return () => window.clearTimeout(timeout);
  }, [armedType]);

  async function runAction(action: QuickActionItem, sourceElement?: HTMLElement): Promise<void> {
    const itemCooldown = cooldownUntil[action.type] ?? 0;
    if (Date.now() < itemCooldown) {
      return;
    }

    if (action.critical) {
      if (armedType !== action.type || Date.now() > armedUntil) {
        setArmedType(action.type);
        setArmedUntil(Date.now() + ARM_WINDOW_MS);
        return;
      }
    }

    try {
      setIsSending(true);
      await onQuickAction(action.type, action.critical ? "CONFIRM" : undefined, sourceElement);
      setCooldownUntil((current) => ({ ...current, [action.type]: Date.now() + COOLDOWN_MS }));
      setArmedType(null);
      setArmedUntil(0);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className={`panel ${className}`.trim()}>
      <SectionHeader
        title="Schnellsteuerung"
        subtitle="Aktionen mit Cooldown und Sicherheitsbestätigung."
        action={
          <div className="quick-actions-header-tools">
            <span className="quick-actions-tip" title="Kritische Aktionen erfordern einen zweiten Klick.">
              ⓘ
            </span>
            <button type="button" className="button-secondary btn-sm" onClick={onOpenChart}>
              Chart
            </button>
          </div>
        }
      />

      <div className="quick-actions-grid">
        {ACTIONS.map((action) => {
          const isArmed = armedType === action.type;
          const cooldownMs = Math.max(0, (cooldownUntil[action.type] ?? 0) - clock);
          const cooldownPct = Math.min(100, Math.round((cooldownMs / COOLDOWN_MS) * 100));
          return (
            <button
              key={action.type}
              type="button"
              className={[
                "quick-action-btn",
                action.primary ? "quick-action-primary" : "",
                action.critical ? "quick-action-critical" : "",
                isArmed ? "quick-action-armed" : "",
                cooldownMs > 0 ? "quick-action-cooldown" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={(event) => void runAction(action, event.currentTarget)}
              disabled={isRefreshing || isSending || cooldownMs > 0}
            >
              <span className="quick-action-icon">{action.icon}</span>
              <span className="quick-action-text">
                <span className="quick-action-label">{action.label}</span>
                <span className="quick-action-sub">{action.sublabel}</span>
              </span>
              {isArmed && <span className="quick-action-countdown">{remainingSeconds}s</span>}
              {isArmed && action.critical ? <span className="quick-action-confirm">CONFIRM</span> : null}
              {isArmed && action.critical ? <span className="quick-action-confirm-layer" aria-hidden /> : null}
              {cooldownMs > 0 ? (
                <span
                  className="quick-action-cooldown-ring"
                  style={{
                    background: `conic-gradient(var(--gold) ${cooldownPct}%, rgba(120,130,160,0.18) ${cooldownPct}% 100%)`,
                  }}
                  aria-hidden
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
