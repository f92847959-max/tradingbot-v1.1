import type {
  ActionLogEntry,
  AIDecisionResponse,
  BotMetricsResponse,
  BotStatusResponse,
  CommandRequest,
  CommandResponse,
  ErrorLogEntry,
  SettingsResponse,
  TradeChartPoint,
} from "../../../shared/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8060/api/v1";
const TOKEN_KEY = "control_api_token";

// SECURITY TODO: Move token to httpOnly cookie with CSRF protection.
// localStorage is XSS-readable; switching requires backend changes
// (set-cookie on auth, CSRF middleware) so this is tracked as a TODO.
export function getApiToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setApiToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token.trim());
}

export function clearApiToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function explainApiError(status: number, statusText: string, body: string): string {
  let detail = "";
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    detail = parsed.detail ?? "";
  } catch {
    detail = body;
  }

  const normalized = detail || `${status} ${statusText}`;
  if (normalized.includes("confirm_token='CONFIRM'")) {
    return "GUARD_BLOCKED: Sicherheits-Schloss aktiv. Für kritische Befehle muss confirm_token=CONFIRM gesetzt sein.";
  }
  return `${status} ${statusText}: ${normalized}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getApiToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "X-Control-Token": token,
    },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(explainApiError(response.status, response.statusText, body));
  }
  return (await response.json()) as T;
}

export function fetchStatus(): Promise<BotStatusResponse> {
  return request<BotStatusResponse>("/bot/status");
}

export function fetchMetrics(): Promise<BotMetricsResponse> {
  return request<BotMetricsResponse>("/bot/metrics");
}

export function postCommand(payload: CommandRequest): Promise<CommandResponse> {
  return request<CommandResponse>("/bot/commands", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchActions(): Promise<ActionLogEntry[]> {
  return request<ActionLogEntry[]>("/logs/actions?limit=20");
}

export function fetchErrors(): Promise<ErrorLogEntry[]> {
  return request<ErrorLogEntry[]>("/logs/errors?limit=20");
}

export function fetchSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>("/settings");
}

export function fetchTradeChartPoints(days = 14, limit = 400): Promise<TradeChartPoint[]> {
  return request<TradeChartPoint[]>(`/trades/chart?days=${days}&limit=${limit}`);
}

export function fetchAIDecision(): Promise<AIDecisionResponse> {
  return request<AIDecisionResponse>("/ai/decisions/latest");
}
