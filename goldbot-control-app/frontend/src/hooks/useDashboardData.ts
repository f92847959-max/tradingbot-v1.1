import { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  fetchActions,
  fetchAIDecision,
  fetchErrors,
  fetchMetrics,
  fetchSettings,
  fetchStatus,
  fetchTradeChartPoints,
  postCommand,
} from "../api/client";

const DEFAULT_INTERVAL_SECONDS = 0.25;

export function useDashboardData(enabled = true) {
  const [status, setStatus] = useState<BotStatusResponse | null>(null);
  const [metrics, setMetrics] = useState<BotMetricsResponse | null>(null);
  const [actions, setActions] = useState<ActionLogEntry[]>([]);
  const [errors, setErrors] = useState<ErrorLogEntry[]>([]);
  const [tradePoints, setTradePoints] = useState<TradeChartPoint[]>([]);
  const [aiDecision, setAiDecision] = useState<AIDecisionResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [consecutiveFailures, setConsecutiveFailures] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      return;
    }
    setIsRefreshing(true);
    try {
      const [
        statusData,
        metricData,
        actionData,
        errorData,
        settingsData,
        tradeData,
        aiData,
      ] = await Promise.all([
        fetchStatus(),
        fetchMetrics(),
        fetchActions(),
        fetchErrors(),
        fetchSettings(),
        fetchTradeChartPoints(30, 600),
        fetchAIDecision().catch(() => null),
      ]);
      setStatus(statusData);
      setMetrics(metricData);
      setActions(actionData);
      setErrors(errorData);
      setTradePoints(tradeData);
      setSettings(settingsData);
      setAiDecision(aiData);
      setGlobalError(null);
      setConsecutiveFailures(0);
      setLastUpdatedAt(new Date());
    } catch (error) {
      setGlobalError(String(error));
      setConsecutiveFailures((value) => value + 1);
    } finally {
      setIsRefreshing(false);
      setHasLoadedOnce(true);
    }
  }, [enabled]);

  const submitCommand = useCallback(
    async (payload: CommandRequest): Promise<CommandResponse> => {
      const response = await postCommand(payload);
      await refresh();
      return response;
    },
    [refresh],
  );

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void refresh();
  }, [enabled, refresh]);

  const pollIntervalSeconds = useMemo(() => {
    const base = DEFAULT_INTERVAL_SECONDS;
    const backoffMultiplier = Math.pow(2, Math.min(consecutiveFailures, 3));
    return Math.min(base * backoffMultiplier, 30);
  }, [consecutiveFailures]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timer = window.setInterval(() => {
      void refresh();
    }, pollIntervalSeconds * 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [enabled, pollIntervalSeconds, refresh]);

  return {
    status,
    metrics,
    actions,
    errors,
    tradePoints,
    aiDecision,
    settings,
    globalError,
    isRefreshing,
    isInitialLoading: !hasLoadedOnce,
    pollIntervalSeconds,
    lastUpdatedAt,
    refresh,
    submitCommand,
  };
}
