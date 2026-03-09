import type { BotState } from "../../../shared/types";
import { BotStateBadge } from "./BotStateBadge";

export type Page = "dashboard" | "trades" | "risk" | "logs" | "settings";

type SidebarProps = {
  activePage: Page;
  onNavigate: (page: Page) => void;
  botState: BotState | null;
  badges?: Partial<Record<Page, number>>;
  isDark: boolean;
  onToggleTheme: () => void;
  onLock: () => void;
};

const NAV_ITEMS: { page: Page; icon: string; label: string }[] = [
  { page: "dashboard", icon: "◈", label: "Dashboard" },
  { page: "trades", icon: "↗", label: "Trades" },
  { page: "risk", icon: "⚠", label: "Risiko" },
  { page: "logs", icon: "⌘", label: "Logs" },
  { page: "settings", icon: "⚙", label: "Einstellungen" },
];

export function Sidebar({
  activePage,
  onNavigate,
  botState,
  badges = {},
  isDark,
  onToggleTheme,
  onLock,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">Au</div>
        <div className="brand-text">
          <h1>GoldBot</h1>
          <small>Trading Control</small>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.page}
            type="button"
            className={`nav-link ${activePage === item.page ? "nav-link-active" : ""}`}
            onClick={() => onNavigate(item.page)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {badges[item.page] ? <span className="nav-badge">{badges[item.page]}</span> : null}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-status">
          <span className="label">Bot</span>
          {botState ? <BotStateBadge state={botState} /> : <span className="state-placeholder">--</span>}
        </div>

        <button type="button" className="theme-toggle" onClick={onToggleTheme}>
          {isDark ? "☀" : "☾"} {isDark ? "Hell" : "Dunkel"}
        </button>

        <button type="button" className="lock-btn" onClick={onLock}>
          🔒 Sperren
        </button>
      </div>
    </aside>
  );
}
