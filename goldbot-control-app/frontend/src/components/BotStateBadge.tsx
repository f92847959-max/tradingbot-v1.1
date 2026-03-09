import type { BotState } from "../../../shared/types";

type BotStateBadgeProps = {
  state: BotState;
};

const STATE_CLASS_MAP: Record<BotState, string> = {
  RUNNING: "state-positive",
  STOPPED: "state-negative",
  PAUSED: "state-warning",
  DEGRADED: "state-warning",
};

export function BotStateBadge({ state }: BotStateBadgeProps) {
  return (
    <span className={`state-badge ${STATE_CLASS_MAP[state]}`}>
      <span className="state-dot" />
      {state}
    </span>
  );
}

