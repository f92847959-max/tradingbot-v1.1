import type {
  ActionLogEntry,
  BotMetricsResponse,
  BotStatusResponse,
  TradeChartPoint,
} from "../../../shared/types";
import type { KpiCardModel, SparkPoint, TradeVisualPoint } from "../types/viewModels";

const DEFAULT_POINTS = 12;

function buildSparkline(values: number[], minPoints = DEFAULT_POINTS): SparkPoint[] {
  const normalized = values.length > 0 ? values : [0];
  const padded: number[] = [...normalized];
  while (padded.length < minPoints) {
    padded.unshift(padded[0] ?? 0);
  }
  return padded.slice(-minPoints).map((value, index) => ({ x: index, value }));
}

function formatShortTime(dateIso: string): string {
  return new Date(dateIso).toLocaleTimeString("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function buildTradeVisualPoints(points: TradeChartPoint[]): TradeVisualPoint[] {
  return [...points]
    .sort((a, b) => new Date(a.opened_at).getTime() - new Date(b.opened_at).getTime())
    .map((item) => ({
      id: item.id,
      label: formatShortTime(item.opened_at),
      zeit: new Date(item.opened_at).toLocaleString("de-DE"),
      openedAtIso: item.opened_at,
      direction: item.direction,
      status: item.status,
      dealId: item.deal_id ?? `trade-${item.id}`,
      entry: item.entry_price,
      sl: item.stop_loss ?? null,
      tp: item.take_profit ?? null,
      exit: item.exit_price ?? null,
      lotSize: item.lot_size ?? null,
      netPnl: item.net_pnl ?? null,
    }));
}

export function buildKpis(
  metrics: BotMetricsResponse | null,
  actions: ActionLogEntry[],
  status: BotStatusResponse | null,
): KpiCardModel[] {
  const commandSeries = actions
    .slice(0, DEFAULT_POINTS)
    .reverse()
    .map((_, index) => index + 1);

  const successRate = metrics
    ? Math.round(
        (metrics.successful_commands_24h /
          Math.max(1, metrics.successful_commands_24h + metrics.failed_commands_24h)) *
          100,
      )
    : 100;

  const riskState = (status?.risk_state ?? "normal").toLowerCase();
  const riskAccent: KpiCardModel["accentState"] =
    riskState.includes("emergency") ? "danger" : riskState.includes("warn") ? "warn" : "safe";
  const openPositions = status?.open_positions ?? 0;
  const strategyName = status?.active_strategy ?? "n/a";
  const failureCount = metrics?.failed_commands_24h ?? 0;

  return [
    {
      id: "strategy",
      icon: "🧠",
      title: "Strategie",
      value: strategyName,
      delta: status?.state ?? "UNBEKANNT",
      trend: status?.state === "RUNNING" ? "up" : status?.state === "STOPPED" ? "down" : "flat",
      tone: status?.state === "RUNNING" ? "positive" : "warning",
      footnote: "Engine",
      sparkline: buildSparkline(commandSeries.map((idx) => idx + (status?.state === "RUNNING" ? 4 : 0))),
    },
    {
      id: "positions",
      icon: "📦",
      title: "Positionen",
      value: String(openPositions),
      delta: openPositions > 0 ? "Aktiv" : "Flat",
      trend: openPositions > 0 ? "up" : "flat",
      tone: openPositions > 0 ? "info" : "neutral",
      footnote: "Live",
      sparkline: buildSparkline(commandSeries.map((idx) => (openPositions > 0 ? idx + 1 : idx - 1))),
    },
    {
      id: "risk",
      icon: "🛡",
      title: "Risiko",
      value: status?.risk_state ?? "normal",
      delta: riskAccent === "danger" ? "Hoch" : riskAccent === "warn" ? "Beobachten" : "Stabil",
      trend: riskAccent === "danger" ? "down" : riskAccent === "warn" ? "flat" : "up",
      tone: riskAccent === "danger" ? "negative" : riskAccent === "warn" ? "warning" : "positive",
      accentState: riskAccent,
      footnote: "Safety",
      sparkline: buildSparkline(
        commandSeries.map((idx) => (riskAccent === "danger" ? 22 + (idx % 3) : 78 + (idx % 4))),
      ),
    },
    {
      id: "trades",
      icon: "📈",
      title: "Trades heute",
      value: String(metrics?.orders_today ?? 0),
      delta: `${metrics?.successful_commands_24h ?? 0} ok`,
      trend: (metrics?.orders_today ?? 0) > 0 ? "up" : "flat",
      tone: "info",
      footnote: "24h",
      sparkline: buildSparkline(commandSeries),
    },
    {
      id: "success",
      icon: "✅",
      title: "Erfolgsrate",
      value: `${successRate}%`,
      delta: `${metrics?.failed_commands_24h ?? 0} Fehler`,
      trend: failureCount > 0 ? "down" : "up",
      tone: successRate >= 80 ? "positive" : "warning",
      badge: failureCount === 0 ? "0 Fehler / 24h" : undefined,
      footnote: "24h",
      sparkline: buildSparkline(
        actions
          .slice(0, DEFAULT_POINTS)
          .reverse()
          .map((item) => (item.status === "success" ? 100 : 20)),
      ),
    },
    {
      id: "api-latency",
      icon: "⚡",
      title: "API Latenz",
      value: `${(metrics?.api_latency_ms ?? 0).toFixed(0)} ms`,
      delta: (metrics?.api_latency_ms ?? 0) < 50 ? "Schnell" : "Langsam",
      trend: (metrics?.api_latency_ms ?? 0) < 50 ? "up" : "down",
      tone: (metrics?.api_latency_ms ?? 0) < 50 ? "positive" : "warning",
      footnote: "Echtzeit",
      sparkline: buildSparkline(
        commandSeries.map((idx) => (metrics?.api_latency_ms ?? 18) + (idx % 4) * 0.65 - 1.3),
      ),
    },
    {
      id: "db-latency",
      icon: "🗄",
      title: "DB Latenz",
      value: `${(metrics?.db_latency_ms ?? 0).toFixed(0)} ms`,
      delta: (metrics?.failed_commands_24h ?? 0) > 0 ? "Fehler" : "Stabil",
      trend: (metrics?.failed_commands_24h ?? 0) > 0 ? "down" : "up",
      tone: (metrics?.failed_commands_24h ?? 0) > 0 ? "warning" : "neutral",
      footnote: "Echtzeit",
      sparkline: buildSparkline(
        commandSeries.map((idx) => (metrics?.db_latency_ms ?? 6) + (idx % 3) * 0.4 - 0.5),
      ),
    },
  ];
}
