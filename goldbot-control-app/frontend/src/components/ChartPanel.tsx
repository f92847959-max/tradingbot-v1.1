import { useEffect, useMemo, useState } from "react";
import type { ActionLogEntry } from "../../../shared/types";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import type { TradeVisualPoint } from "../types/viewModels";
import { SectionHeader } from "./SectionHeader";

type ChartPanelProps = {
  series: TradeVisualPoint[];
  actions?: ActionLogEntry[];
  className?: string;
};

function TradeTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload as TradeVisualPoint & { ema: number; vwap: number; rsi: number };
  if (!point) return null;

  const pnlColor = (point.netPnl ?? 0) >= 0 ? "var(--success)" : "var(--danger)";

  return (
    <div className="trade-tooltip">
      <p className="trade-tooltip-title">{point.zeit}</p>
      <p>{point.direction === "BUY" ? "🔼" : "🔽"} {point.direction} — {point.status}</p>
      <p>Entry: <strong>{point.entry.toFixed(2)}</strong></p>
      {point.sl != null && <p style={{ color: "var(--danger)" }}>SL: {point.sl.toFixed(2)}</p>}
      {point.tp != null && <p style={{ color: "var(--success)" }}>TP: {point.tp.toFixed(2)}</p>}
      {point.exit != null && <p>Exit: {point.exit.toFixed(2)}</p>}
      {point.netPnl != null && (
        <p style={{ color: pnlColor, fontWeight: 700, marginTop: 4 }}>
          P&L: {point.netPnl >= 0 ? "+" : ""}{point.netPnl.toFixed(2)}
        </p>
      )}
      <p>EMA: <strong>{point.ema.toFixed(2)}</strong></p>
      <p>VWAP: <strong>{point.vwap.toFixed(2)}</strong></p>
      <p>RSI: <strong>{point.rsi.toFixed(1)}</strong></p>
    </div>
  );
}

type EventMark = {
  id: string;
  chartIndex: number;
  price: number;
  icon: string;
  color: string;
  label: string;
};

function mapActionToIcon(action: string): string {
  if (action === "START_BOT") return "▶";
  if (action === "STOP_BOT") return "■";
  if (action === "PAUSE_TRADING") return "‖";
  if (action === "RESUME_TRADING") return "▷";
  if (action === "EMERGENCY_STOP") return "⚡";
  return "●";
}

function mapActionToColor(action: string): string {
  if (action === "START_BOT" || action === "RESUME_TRADING") return "var(--success)";
  if (action === "EMERGENCY_STOP" || action === "STOP_BOT") return "var(--danger)";
  if (action === "PAUSE_TRADING") return "var(--warning)";
  return "var(--text-muted)";
}

export function ChartPanel({ series, actions = [], className = "" }: ChartPanelProps) {
  const [showEma, setShowEma] = useState(true);
  const [showVwap, setShowVwap] = useState(true);
  const [showRsi, setShowRsi] = useState(false);
  const [showEvents, setShowEvents] = useState(true);
  const [replayMode, setReplayMode] = useState(false);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);

  const chartData = useMemo(() => {
    if (series.length === 0) return [];

    const base = series.map((item, idx) => ({
      ...item,
      idx,
      pnlFill: item.netPnl ?? 0,
      ema: item.entry,
      vwap: item.entry,
      rsi: 50,
    }));

    let emaLast = base[0]?.entry ?? 0;
    let cumulativePV = 0;
    let cumulativeVolume = 0;
    const gains: number[] = [];
    const losses: number[] = [];

    return base.map((item, idx) => {
      const price = item.exit ?? item.entry;
      const volume = item.lotSize && item.lotSize > 0 ? item.lotSize : 1;
      const alpha = 2 / (6 + 1);
      emaLast = alpha * price + (1 - alpha) * emaLast;

      cumulativePV += price * volume;
      cumulativeVolume += volume;
      const vwap = cumulativeVolume > 0 ? cumulativePV / cumulativeVolume : price;

      const prevPrice = idx > 0 ? (base[idx - 1]?.exit ?? base[idx - 1]?.entry ?? price) : price;
      const diff = price - prevPrice;
      gains.push(Math.max(0, diff));
      losses.push(Math.max(0, -diff));
      const period = 6;
      const gainAvg = gains.slice(-period).reduce((sum, value) => sum + value, 0) / Math.min(gains.length, period);
      const lossAvg = losses.slice(-period).reduce((sum, value) => sum + value, 0) / Math.min(losses.length, period);
      const rs = lossAvg === 0 ? 100 : gainAvg / lossAvg;
      const rsi = 100 - (100 / (1 + rs));

      return {
        ...item,
        ema: emaLast,
        vwap,
        rsi: Number.isFinite(rsi) ? rsi : 50,
      };
    });
  }, [series]);

  useEffect(() => {
    if (!replayMode) {
      setReplayIndex(Math.max(0, chartData.length - 1));
      setReplayPlaying(false);
      return;
    }
    if (replayIndex >= chartData.length) {
      setReplayIndex(Math.max(0, chartData.length - 1));
    }
  }, [replayMode, chartData.length, replayIndex]);

  useEffect(() => {
    if (!replayMode || !replayPlaying) return;
    const timer = window.setInterval(() => {
      setReplayIndex((current) => {
        if (current >= chartData.length - 1) {
          setReplayPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 320);
    return () => window.clearInterval(timer);
  }, [replayMode, replayPlaying, chartData.length]);

  const visibleData = useMemo(
    () => (replayMode ? chartData.slice(0, replayIndex + 1) : chartData),
    [chartData, replayMode, replayIndex],
  );

  const eventMarks = useMemo<EventMark[]>(() => {
    if (chartData.length === 0 || actions.length === 0) return [];

    const relevantActions = actions
      .filter((item) => ["START_BOT", "STOP_BOT", "PAUSE_TRADING", "RESUME_TRADING", "EMERGENCY_STOP"].includes(item.command_type))
      .slice(0, 30)
      .sort((a, b) => new Date(a.executed_at).getTime() - new Date(b.executed_at).getTime());

    return relevantActions.map((action, idx) => {
      const actionTs = new Date(action.executed_at).getTime();
      let nearestIndex = 0;
      let nearestDistance = Number.POSITIVE_INFINITY;

      chartData.forEach((point, pointIndex) => {
        const pointTs = new Date(point.openedAtIso).getTime();
        const distance = Math.abs(pointTs - actionTs);
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestIndex = pointIndex;
        }
      });

      const nearestPoint = chartData[nearestIndex];
      return {
        id: `${action.id}-${idx}`,
        chartIndex: nearestIndex,
        price: nearestPoint?.entry ?? 0,
        icon: mapActionToIcon(action.command_type),
        color: mapActionToColor(action.command_type),
        label: action.command_type,
      };
    });
  }, [chartData, actions]);

  const visibleEventMarks = useMemo(
    () => eventMarks.filter((mark) => mark.chartIndex <= Math.max(0, visibleData.length - 1)),
    [eventMarks, visibleData.length],
  );

  return (
    <section className={`panel ${className}`.trim()}>
      <SectionHeader
        title="Market Replay Chart"
        subtitle="Layer: EMA, VWAP, RSI + Event-Marker aus dem Command-Log"
      />
      <div className="chart-toolbar">
        <div className="chart-layer-toggles">
          <button type="button" className={`chip ${showEma ? "chip-active" : ""}`} onClick={() => setShowEma((v) => !v)}>EMA</button>
          <button type="button" className={`chip ${showVwap ? "chip-active" : ""}`} onClick={() => setShowVwap((v) => !v)}>VWAP</button>
          <button type="button" className={`chip ${showRsi ? "chip-active" : ""}`} onClick={() => setShowRsi((v) => !v)}>RSI</button>
          <button type="button" className={`chip ${showEvents ? "chip-active" : ""}`} onClick={() => setShowEvents((v) => !v)}>Events</button>
        </div>
        <div className="chart-replay-controls">
          <button
            type="button"
            className={`chip ${replayMode ? "chip-active" : ""}`}
            onClick={() => {
              setReplayMode((current) => {
                const next = !current;
                if (next) setReplayIndex(0);
                if (!next) setReplayPlaying(false);
                return next;
              });
            }}
          >
            Replay
          </button>
          {replayMode ? (
            <>
              <button type="button" className="chip" onClick={() => setReplayPlaying((v) => !v)}>
                {replayPlaying ? "Pause" : "Play"}
              </button>
              <input
                className="replay-slider"
                type="range"
                min={0}
                max={Math.max(0, chartData.length - 1)}
                value={replayIndex}
                onChange={(event) => setReplayIndex(Number(event.target.value))}
              />
            </>
          ) : null}
        </div>
      </div>
      <div className="chart-layer-tips">
        <span className="chart-layer-tip">EMA + VWAP: Trend + fairer Preis</span>
        <span className="chart-layer-tip">RSI + Events: Signale gegen Aktionen prüfen</span>
        <span className="chart-layer-tip">VWAP only: Mean-Reversion testen</span>
      </div>
      <div className="chart-wrap" style={{ height: 380 }}>
        {visibleData.length === 0 ? (
          <p className="chart-empty">
            Noch keine Trades. Sobald der Bot handelt, erscheinen die Daten hier.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={visibleData}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#d4a843" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#d4a843" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="entryGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#d4a843" stopOpacity={0.12} />
                  <stop offset="100%" stopColor="#d4a843" stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 6"
                stroke="var(--line-subtle)"
                horizontal
                vertical={false}
              />
              <XAxis
                dataKey="idx"
                stroke="var(--text-muted)"
                fontSize={11}
                tickLine={false}
                tickFormatter={(value) => visibleData[value]?.label ?? ""}
                axisLine={{ stroke: "var(--line-subtle)" }}
              />
              <YAxis
                stroke="var(--text-muted)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => Number(value).toFixed(0)}
                width={55}
              />
              {showRsi ? (
                <YAxis
                  yAxisId="rsi"
                  orientation="right"
                  domain={[0, 100]}
                  stroke="var(--text-muted)"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  width={35}
                />
              ) : null}
              <Tooltip
                content={<TradeTooltip />}
                cursor={{ stroke: "var(--gold)", strokeDasharray: "4 4", strokeOpacity: 0.4 }}
              />
              <Legend
                wrapperStyle={{ fontSize: "0.72rem", color: "var(--text-muted)" }}
              />
              <Area
                type="monotone"
                dataKey="entry"
                name="Price"
                stroke="rgba(101, 214, 255, 0.88)"
                strokeWidth={2.2}
                fill="url(#entryGradient)"
                dot={{ r: 0 }}
                activeDot={{ r: 7, fill: "#98f0ff", stroke: "#65d6ff", strokeWidth: 2 }}
                animationDuration={1200}
                animationEasing="ease-in-out"
                style={{ filter: "drop-shadow(0 0 8px rgba(101, 214, 255, 0.22))" }}
              />
              {showEma ? (
                <Line
                  type="monotone"
                  dataKey="ema"
                  name="EMA"
                  stroke="rgba(196, 167, 255, 0.78)"
                  strokeWidth={1.7}
                  dot={false}
                  animationDuration={950}
                  style={{ filter: "drop-shadow(0 0 6px rgba(196, 167, 255, 0.2))" }}
                />
              ) : null}
              {showVwap ? (
                <Line
                  type="monotone"
                  dataKey="vwap"
                  name="VWAP"
                  stroke="rgba(122, 255, 200, 0.72)"
                  strokeWidth={1.7}
                  strokeDasharray="5 4"
                  dot={false}
                  animationDuration={950}
                  style={{ filter: "drop-shadow(0 0 6px rgba(122, 255, 200, 0.18))" }}
                />
              ) : null}
              <Line
                type="stepAfter"
                dataKey="sl"
                name="Stop-Loss"
                stroke="#ef5350"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                connectNulls={false}
                dot={{ r: 3, fill: "#ef5350", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                animationDuration={1000}
                animationEasing="ease-in-out"
              />
              <Line
                type="stepAfter"
                dataKey="tp"
                name="Take-Profit"
                stroke="#2dd4a0"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                connectNulls={false}
                dot={{ r: 3, fill: "#2dd4a0", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                animationDuration={1000}
                animationEasing="ease-in-out"
              />
              <Line
                type="monotone"
                dataKey="exit"
                name="Exit"
                stroke="#887e6a"
                strokeWidth={1.5}
                connectNulls={false}
                dot={{ r: 3, fill: "#887e6a", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                animationDuration={800}
                animationEasing="ease-in-out"
              />
              {showRsi ? (
                <Line
                  yAxisId="rsi"
                  type="monotone"
                  dataKey="rsi"
                  name="RSI"
                  stroke="rgba(249, 213, 110, 0.75)"
                  strokeWidth={1.4}
                  dot={false}
                />
              ) : null}
              {showEvents
                ? visibleEventMarks.map((event) => (
                  <ReferenceDot
                    key={event.id}
                    x={event.chartIndex}
                    y={event.price}
                    r={5}
                    fill={event.color}
                    stroke="#0b0f19"
                    strokeWidth={1.3}
                    label={{
                      value: event.icon,
                      position: "center",
                      fill: "#0b0f19",
                      fontSize: 8,
                      fontWeight: 600,
                    }}
                  />
                ))
                : null}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
      {showEvents && visibleEventMarks.length > 0 ? (
        <div className="chart-event-legend">
          {visibleEventMarks.slice(-5).map((event) => (
            <span key={event.id} className="chart-event-chip" style={{ borderColor: event.color }}>
              <span style={{ color: event.color }}>{event.icon}</span> {event.label}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
