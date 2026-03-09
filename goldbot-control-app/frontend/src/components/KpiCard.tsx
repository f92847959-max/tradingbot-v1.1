import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
} from "recharts";
import type { KpiCardModel, Tone, TrendDirection } from "../types/viewModels";

type KpiCardProps = {
  model: KpiCardModel;
};

const TONE_COLOR: Record<Tone, string> = {
  neutral: "#887e6a",
  positive: "#2dd4a0",
  warning: "#f5a623",
  negative: "#ef5350",
  info: "#d4a843",
};

const TREND_LABEL: Record<TrendDirection, string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

function SparkTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return <div className="spark-tooltip">{payload[0]?.value?.toFixed(2)}</div>;
}

export function KpiCard({ model }: KpiCardProps) {
  const toneColor = TONE_COLOR[model.tone];
  return (
    <article className={`kpi-card tone-${model.tone} ${model.accentState ? `kpi-accent-${model.accentState}` : ""}`}>
      <div className="kpi-meta">
        <div className="kpi-top-row">
          <p className="kpi-title">
            <span className="kpi-icon">{model.icon}</span>
            {model.title}
          </p>
          <span className={`kpi-trend kpi-trend-${model.trend}`}>{TREND_LABEL[model.trend]}</span>
        </div>
        <p className="kpi-value">{model.value}</p>
        {model.badge ? <span className="kpi-badge">{model.badge}</span> : null}
      </div>
      <div className="kpi-spark">
        <ResponsiveContainer width="100%" height={48}>
          <AreaChart data={model.sparkline}>
            <defs>
              <linearGradient id={`spark-${model.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={toneColor} stopOpacity={0.55} />
                <stop offset="100%" stopColor={toneColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <Tooltip content={<SparkTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke={toneColor}
              strokeWidth={2}
              fill={`url(#spark-${model.id})`}
              animationDuration={800}
              animationEasing="ease-in-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="kpi-footer">
        <span className="kpi-delta">{model.delta}</span>
        <span className="kpi-footnote">{model.footnote}</span>
      </div>
    </article>
  );
}
