export type CommandType =
  | "START_BOT"
  | "STOP_BOT"
  | "RELOAD_CONFIG"
  | "PAUSE_TRADING"
  | "RESUME_TRADING"
  | "EMERGENCY_STOP";

export type BotState = "RUNNING" | "STOPPED" | "PAUSED" | "DEGRADED";

export interface CommandRequest {
  command_id: string;
  command_type: CommandType;
  target?: string | null;
  params: Record<string, unknown>;
  requested_by: string;
  requested_at: string;
  confirm_token?: string | null;
}

export interface CommandResponse {
  accepted: boolean;
  command_id: string;
  command_type: CommandType;
  status: string;
  message: string;
  executed_at: string;
}

export interface BotStatusResponse {
  state: BotState;
  uptime_sec: number;
  last_heartbeat: string;
  active_strategy: string;
  open_positions: number;
  risk_state: string;
  last_error?: string | null;
}

export interface BotMetricsResponse {
  orders_today: number;
  successful_commands_24h: number;
  failed_commands_24h: number;
  api_latency_ms: number;
  db_latency_ms: number;
}

export interface ActionLogEntry {
  id: number;
  command_id: string;
  command_type: CommandType;
  target?: string | null;
  params: Record<string, unknown>;
  status: string;
  message: string;
  requested_by: string;
  requested_at: string;
  executed_at: string;
}

export interface ErrorLogEntry {
  id: number;
  source: string;
  error_code: string;
  message: string;
  details: string;
  created_at: string;
}

export interface SettingsResponse {
  polling_interval_seconds: number;
  confirmations_enabled: boolean;
  updated_at: string;
}

export interface TradeChartPoint {
  id: number;
  deal_id?: string | null;
  opened_at: string;
  closed_at?: string | null;
  direction: string;
  status: string;
  entry_price: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  exit_price?: number | null;
  lot_size?: number | null;
  net_pnl?: number | null;
}
