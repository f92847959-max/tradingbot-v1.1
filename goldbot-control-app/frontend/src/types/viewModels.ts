export type Tone = "neutral" | "positive" | "warning" | "negative" | "info";
export type TrendDirection = "up" | "down" | "flat";

export interface SparkPoint {
  x: number;
  value: number;
}

export interface KpiCardModel {
  id: string;
  icon: string;
  title: string;
  value: string;
  delta: string;
  trend: TrendDirection;
  tone: Tone;
  footnote: string;
  badge?: string;
  accentState?: "safe" | "warn" | "danger";
  sparkline: SparkPoint[];
}

export interface TradeVisualPoint {
  id: number;
  label: string;
  zeit: string;
  openedAtIso: string;
  direction: string;
  status: string;
  dealId: string;
  entry: number;
  sl: number | null;
  tp: number | null;
  exit: number | null;
  lotSize: number | null;
  netPnl: number | null;
}

export interface ToastMessage {
  id: string;
  kind: "success" | "error" | "info";
  text: string;
}
