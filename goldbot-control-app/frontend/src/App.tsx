import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  BotMetricsResponse,
  BotStatusResponse,
  CommandRequest,
  CommandType,
} from "../../shared/types";
import { clearApiToken, getApiToken, setApiToken } from "./api/client";
import { ActivityFeed } from "./components/ActivityFeed";
import { BotStateBadge } from "./components/BotStateBadge";
import { ChartPanel } from "./components/ChartPanel";
import { ErrorPanel } from "./components/ErrorPanel";
import { KpiCard } from "./components/KpiCard";
import { LoginGate } from "./components/LoginGate";
import {
  ParticleField,
  type ParticleDirection,
  type ParticleFieldHandle,
} from "./components/ParticleField";
import { Sidebar, type Page } from "./components/Sidebar";
import { ToastStack } from "./components/ToastStack";
import { useDashboardData } from "./hooks/useDashboardData";
import type { ToastMessage } from "./types/viewModels";
import { buildKpis, buildTradeVisualPoints } from "./utils/chartData";

const STUDIO_STORAGE_KEY = "goldbot-dashboard-studio-v1";
const CUSTOM_PRESET_STORAGE_KEY = "goldbot-dashboard-custom-preset-v1";
const STUDIO_VERSION = 1;

type ThemeMode = "dark" | "light";
type UiPresetId = "minimal" | "professional" | "cinematic";

type ThemeConfig = {
  mode: ThemeMode;
  primary: string;
  accent: string;
  error: string;
  background: string;
  contrast: number;
  fontSans: string;
  fontMono: string;
  fontSize: number;
};

type LayoutConfig = {
  kpiColumns: number;
  panelGap: number;
  splitLeftRatio: number;
  compactCards: boolean;
  lockWidgets: boolean;
};

type VisibilityConfig = {
  header: boolean;
  statusStrip: boolean;
  chart: boolean;
  activity: boolean;
  errors: boolean;
};

type MotionConfig = {
  enabled: boolean;
  intensity: number;
  density: number;
  durationMs: number;
  delayMs: number;
  direction: ParticleDirection;
};

type StudioConfig = {
  preset: UiPresetId;
  theme: ThemeConfig;
  layout: LayoutConfig;
  visibility: VisibilityConfig;
  motion: MotionConfig;
};

const PAGE_TITLES: Record<Page, string> = {
  dashboard: "Dashboard",
  trades: "Trades",
  risk: "Risiko",
  logs: "Logs",
  settings: "Einstellungen",
};

const PRESET_LABELS: Record<UiPresetId, string> = {
  minimal: "Minimal",
  professional: "Professional",
  cinematic: "Cinematic",
};

const COMMAND_PARTICLE_SIGNAL: Record<
  CommandType,
  { color: string; direction: ParticleDirection }
> = {
  START_BOT: { color: "#2dd4a0", direction: "up" },
  STOP_BOT: { color: "#ef5350", direction: "away" },
  RELOAD_CONFIG: { color: "#65d6ff", direction: "radial" },
  PAUSE_TRADING: { color: "#f5a623", direction: "down" },
  RESUME_TRADING: { color: "#2dd4a0", direction: "up" },
  EMERGENCY_STOP: { color: "#ef5350", direction: "away" },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isPreset(value: unknown): value is UiPresetId {
  return value === "minimal" || value === "professional" || value === "cinematic";
}

function normalizeHex(value: string, fallback: string): string {
  const raw = value.trim();
  if (/^#[a-fA-F0-9]{6}$/.test(raw)) {
    return raw.toLowerCase();
  }
  if (/^#[a-fA-F0-9]{3}$/.test(raw)) {
    return `#${raw[1]}${raw[1]}${raw[2]}${raw[2]}${raw[3]}${raw[3]}`.toLowerCase();
  }
  return fallback;
}

function isValidHex(value: string): boolean {
  return /^#[a-fA-F0-9]{6}$/.test(value.trim());
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const normalized = normalizeHex(hex, "");
  if (!/^#[a-f0-9]{6}$/.test(normalized)) return null;
  return {
    r: Number.parseInt(normalized.slice(1, 3), 16),
    g: Number.parseInt(normalized.slice(3, 5), 16),
    b: Number.parseInt(normalized.slice(5, 7), 16),
  };
}

function blendHex(hexA: string, hexB: string, ratio: number): string {
  const a = hexToRgb(hexA);
  const b = hexToRgb(hexB);
  if (!a || !b) return hexA;
  const mix = clamp(ratio, 0, 1);
  const r = Math.round(a.r + (b.r - a.r) * mix);
  const g = Math.round(a.g + (b.g - a.g) * mix);
  const bVal = Math.round(a.b + (b.b - a.b) * mix);
  return `#${r.toString(16).padStart(2, "0")}${g
    .toString(16)
    .padStart(2, "0")}${bVal.toString(16).padStart(2, "0")}`;
}

function hexToRgba(hex: string, alpha: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return `rgba(212, 168, 67, ${alpha})`;
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${clamp(alpha, 0, 1)})`;
}

function createPreset(id: UiPresetId): Omit<StudioConfig, "preset"> {
  if (id === "minimal") {
    return {
      theme: {
        mode: "dark",
        primary: "#d4a843",
        accent: "#65d6ff",
        error: "#ef5350",
        background: "#090b12",
        contrast: 102,
        fontSans: "\"Inter\", system-ui, sans-serif",
        fontMono: "\"Roboto Mono\", ui-monospace, monospace",
        fontSize: 14,
      },
      layout: {
        kpiColumns: 3,
        panelGap: 12,
        splitLeftRatio: 1.1,
        compactCards: true,
        lockWidgets: false,
      },
      visibility: {
        header: true,
        statusStrip: true,
        chart: true,
        activity: true,
        errors: false,
      },
      motion: {
        enabled: true,
        intensity: 36,
        density: 8,
        durationMs: 420,
        delayMs: 8,
        direction: "radial",
      },
    };
  }

  if (id === "cinematic") {
    return {
      theme: {
        mode: "dark",
        primary: "#00a3ff",
        accent: "#1df7d2",
        error: "#ff4d6d",
        background: "#060a16",
        contrast: 110,
        fontSans: "\"Inter\", system-ui, sans-serif",
        fontMono: "\"Roboto Mono\", ui-monospace, monospace",
        fontSize: 14,
      },
      layout: {
        kpiColumns: 4,
        panelGap: 16,
        splitLeftRatio: 1.4,
        compactCards: false,
        lockWidgets: false,
      },
      visibility: {
        header: true,
        statusStrip: true,
        chart: true,
        activity: true,
        errors: true,
      },
      motion: {
        enabled: true,
        intensity: 88,
        density: 18,
        durationMs: 760,
        delayMs: 24,
        direction: "away",
      },
    };
  }

  return {
    theme: {
      mode: "dark",
      primary: "#d4a843",
      accent: "#65d6ff",
      error: "#ef5350",
      background: "#08090e",
      contrast: 100,
      fontSans: "\"Inter\", system-ui, sans-serif",
      fontMono: "\"Roboto Mono\", ui-monospace, monospace",
      fontSize: 14,
    },
    layout: {
      kpiColumns: 4,
      panelGap: 14,
      splitLeftRatio: 1.3,
      compactCards: false,
      lockWidgets: false,
    },
    visibility: {
      header: true,
      statusStrip: true,
      chart: true,
      activity: true,
      errors: true,
    },
    motion: {
      enabled: true,
      intensity: 68,
      density: 12,
      durationMs: 560,
      delayMs: 14,
      direction: "away",
    },
  };
}

function defaultStudio(): StudioConfig {
  return {
    preset: "professional",
    ...createPreset("professional"),
  };
}

function sanitizeStudio(candidate?: Partial<StudioConfig>): StudioConfig {
  const base = defaultStudio();
  if (!candidate) return base;

  const themeSource = { ...base.theme, ...(candidate.theme ?? {}) };
  const layoutSource = { ...base.layout, ...(candidate.layout ?? {}) };
  const visibilitySource = { ...base.visibility, ...(candidate.visibility ?? {}) };
  const motionSource = { ...base.motion, ...(candidate.motion ?? {}) };

  return {
    preset: isPreset(candidate.preset) ? candidate.preset : base.preset,
    theme: {
      mode: themeSource.mode === "light" ? "light" : "dark",
      primary: normalizeHex(String(themeSource.primary), base.theme.primary),
      accent: normalizeHex(String(themeSource.accent), base.theme.accent),
      error: normalizeHex(String(themeSource.error), base.theme.error),
      background: normalizeHex(String(themeSource.background), base.theme.background),
      contrast: clamp(Number(themeSource.contrast) || base.theme.contrast, 90, 120),
      fontSans: String(themeSource.fontSans || base.theme.fontSans),
      fontMono: String(themeSource.fontMono || base.theme.fontMono),
      fontSize: clamp(Number(themeSource.fontSize) || base.theme.fontSize, 12, 18),
    },
    layout: {
      kpiColumns: clamp(Number(layoutSource.kpiColumns) || base.layout.kpiColumns, 2, 6),
      panelGap: clamp(Number(layoutSource.panelGap) || base.layout.panelGap, 8, 24),
      splitLeftRatio: clamp(
        Number(layoutSource.splitLeftRatio) || base.layout.splitLeftRatio,
        1,
        2,
      ),
      compactCards: Boolean(layoutSource.compactCards),
      lockWidgets: Boolean(layoutSource.lockWidgets),
    },
    visibility: {
      header: Boolean(visibilitySource.header),
      statusStrip: Boolean(visibilitySource.statusStrip),
      chart: Boolean(visibilitySource.chart),
      activity: Boolean(visibilitySource.activity),
      errors: Boolean(visibilitySource.errors),
    },
    motion: {
      enabled: Boolean(motionSource.enabled),
      intensity: clamp(Number(motionSource.intensity) || base.motion.intensity, 0, 100),
      density: clamp(Number(motionSource.density) || base.motion.density, 4, 24),
      durationMs: clamp(Number(motionSource.durationMs) || base.motion.durationMs, 300, 1200),
      delayMs: clamp(Number(motionSource.delayMs) || base.motion.delayMs, 0, 180),
      direction:
        motionSource.direction === "up" ||
        motionSource.direction === "down" ||
        motionSource.direction === "radial" ||
        motionSource.direction === "away"
          ? motionSource.direction
          : base.motion.direction,
    },
  };
}

function loadStoredStudio(): StudioConfig {
  if (typeof window === "undefined") return defaultStudio();
  try {
    const raw = window.localStorage.getItem(STUDIO_STORAGE_KEY);
    if (!raw) return defaultStudio();
    const parsed = JSON.parse(raw) as unknown;
    if (isRecord(parsed) && "studio" in parsed && isRecord(parsed.studio)) {
      return sanitizeStudio(parsed.studio as Partial<StudioConfig>);
    }
    if (isRecord(parsed)) {
      return sanitizeStudio(parsed as Partial<StudioConfig>);
    }
  } catch {
    return defaultStudio();
  }
  return defaultStudio();
}

function hasCustomPreset(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.localStorage.getItem(CUSTOM_PRESET_STORAGE_KEY));
}

function loadCustomPreset(): StudioConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CUSTOM_PRESET_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (isRecord(parsed) && "studio" in parsed && isRecord(parsed.studio)) {
      return sanitizeStudio(parsed.studio as Partial<StudioConfig>);
    }
    if (isRecord(parsed)) {
      return sanitizeStudio(parsed as Partial<StudioConfig>);
    }
  } catch {
    return null;
  }
  return null;
}

function formatDuration(totalSeconds: number | null | undefined): string {
  const value = Math.max(0, Math.floor(totalSeconds ?? 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = value % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(
    seconds,
  ).padStart(2, "0")}`;
}

function computeIntegrityScore(
  metrics: BotMetricsResponse | null,
  guardBlockedCount: number,
): number {
  if (!metrics) return 100;
  const totalCommands = metrics.successful_commands_24h + metrics.failed_commands_24h;
  const successRate =
    totalCommands <= 0
      ? 100
      : (metrics.successful_commands_24h / Math.max(1, totalCommands)) * 100;
  const failurePenalty = metrics.failed_commands_24h * 8;
  const guardPenalty = guardBlockedCount * 5;
  return clamp(Math.round(successRate - failurePenalty - guardPenalty), 0, 100);
}

function buildDiff(beforeJson: string, afterJson: string): string {
  const before = beforeJson.split("\n");
  const after = afterJson.split("\n");
  const output: string[] = [];
  const maxLines = Math.max(before.length, after.length);

  for (let index = 0; index < maxLines; index += 1) {
    const oldLine = before[index];
    const newLine = after[index];
    if (oldLine === newLine) {
      if (oldLine !== undefined) output.push(`  ${oldLine}`);
      continue;
    }
    if (oldLine !== undefined) output.push(`- ${oldLine}`);
    if (newLine !== undefined) output.push(`+ ${newLine}`);
  }
  return output.join("\n");
}

function buildCommandRequest(
  commandType: CommandType,
  confirmToken?: string,
): CommandRequest {
  const isCritical =
    commandType === "STOP_BOT" ||
    commandType === "EMERGENCY_STOP" ||
    commandType === "RELOAD_CONFIG";

  return {
    command_id: `${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    command_type: commandType,
    target: "trading-engine",
    params: isCritical ? { reason: "manual check" } : {},
    requested_by: "local-user",
    requested_at: new Date().toISOString(),
    confirm_token: confirmToken ?? null,
  };
}

export function App() {
  const [isLocked, setIsLocked] = useState<boolean>(() => getApiToken().trim().length === 0);
  const [authHint, setAuthHint] = useState<string | undefined>(undefined);
  const [activePage, setActivePage] = useState<Page>("dashboard");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [studio, setStudio] = useState<StudioConfig>(() => loadStoredStudio());
  const [hasStoredCustomPreset, setHasStoredCustomPreset] = useState<boolean>(() =>
    hasCustomPreset(),
  );
  const [showTokenExport, setShowTokenExport] = useState(false);
  const [importDraft, setImportDraft] = useState("");
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  const statusCapsuleRef = useRef<HTMLDivElement | null>(null);
  const particleFieldRef = useRef<ParticleFieldHandle | null>(null);
  const previousStateRef = useRef<BotStatusResponse["state"] | null>(null);
  const lastErrorRef = useRef<string | null>(null);

  const {
    status,
    metrics,
    actions,
    errors,
    tradePoints,
    settings,
    globalError,
    isRefreshing,
    isInitialLoading,
    pollIntervalSeconds,
    refresh,
    submitCommand,
  } = useDashboardData(!isLocked);

  const pushToast = useCallback((kind: ToastMessage["kind"], text: string): void => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    setToasts((current) => [...current, { id, kind, text }].slice(-6));
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, 5200);
  }, []);

  const dismissToast = useCallback((id: string): void => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setPrefersReducedMotion(mediaQuery.matches);
    onChange();
    mediaQuery.addEventListener("change", onChange);
    return () => mediaQuery.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!globalError || globalError === lastErrorRef.current) return;
    lastErrorRef.current = globalError;
    const normalized = globalError.toLowerCase();
    if (normalized.includes("401") || normalized.includes("nicht autorisiert")) {
      clearApiToken();
      setIsLocked(true);
      setAuthHint("Token ungültig. Bitte neu anmelden.");
      pushToast("error", "Token ungültig. Bitte neu anmelden.");
      return;
    }
    pushToast("error", globalError);
  }, [globalError, pushToast]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      STUDIO_STORAGE_KEY,
      JSON.stringify({
        version: STUDIO_VERSION,
        studio,
      }),
    );
  }, [studio]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = studio.theme.mode;
    root.dataset.compact = studio.layout.compactCards ? "1" : "0";
    root.style.setProperty("--font-sans", studio.theme.fontSans);
    root.style.setProperty("--font-mono", studio.theme.fontMono);
    root.style.setProperty("--font-size-base", `${studio.theme.fontSize}px`);
    root.style.setProperty("--ui-contrast", `${studio.theme.contrast}%`);

    root.style.setProperty("--gold", studio.theme.primary);
    root.style.setProperty("--gold-light", blendHex(studio.theme.primary, "#ffffff", 0.22));
    root.style.setProperty("--gold-dark", blendHex(studio.theme.primary, "#000000", 0.25));
    root.style.setProperty("--gold-glow", hexToRgba(studio.theme.primary, 0.36));
    root.style.setProperty("--info", studio.theme.accent);
    root.style.setProperty("--danger", studio.theme.error);
    root.style.setProperty("--bg-0", studio.theme.background);

    root.style.setProperty("--kpi-cols", String(studio.layout.kpiColumns));
    root.style.setProperty("--panel-gap", `${studio.layout.panelGap}px`);
    root.style.setProperty("--split-left", `${studio.layout.splitLeftRatio}fr`);

    root.style.setProperty("--motion-duration-base", `${studio.motion.durationMs}ms`);
    root.style.setProperty("--particle-count-default", String(studio.motion.density));
  }, [studio]);

  const displayRiskState = useMemo(() => {
    if (!status) return "normal";
    const risk = (status.risk_state || "normal").toLowerCase();
    if (status.state === "RUNNING" && risk === "emergency_stop") {
      return "normal";
    }
    return status.risk_state;
  }, [status]);

  const normalizedStatus = useMemo<BotStatusResponse | null>(() => {
    if (!status) return null;
    return {
      ...status,
      risk_state: displayRiskState,
    };
  }, [status, displayRiskState]);

  const tradeSeries = useMemo(() => buildTradeVisualPoints(tradePoints), [tradePoints]);
  const kpis = useMemo(
    () => buildKpis(metrics, actions, normalizedStatus),
    [metrics, actions, normalizedStatus],
  );

  const guardBlockedCount = useMemo(
    () => errors.filter((item) => item.error_code === "GUARD_BLOCKED").length,
    [errors],
  );

  const integrityScore = useMemo(
    () => computeIntegrityScore(metrics, guardBlockedCount),
    [metrics, guardBlockedCount],
  );

  const integrityClass =
    integrityScore >= 85
      ? "integrity-positive"
      : integrityScore >= 65
      ? "integrity-warning"
      : "integrity-negative";

  const engineLatencyMs = useMemo(
    () => Math.max(8, Math.round((pollIntervalSeconds * 1000) / 5 + (isRefreshing ? 24 : 8))),
    [pollIntervalSeconds, isRefreshing],
  );

  const validationMessages = useMemo(() => {
    const items: string[] = [];
    if (!isValidHex(studio.theme.primary)) {
      items.push("Primärfarbe ist kein gültiger HEX-Wert.");
    }
    if (!isValidHex(studio.theme.accent)) {
      items.push("Akzentfarbe ist kein gültiger HEX-Wert.");
    }
    if (!isValidHex(studio.theme.error)) {
      items.push("Fehlerfarbe ist kein gültiger HEX-Wert.");
    }
    if (studio.motion.enabled && studio.motion.intensity > 80 && studio.motion.density > 18) {
      items.push("Hohe Animationslast aktiv: bei schwachen Geräten automatisch reduzieren.");
    }
    if (prefersReducedMotion && studio.motion.enabled) {
      items.push("Systemvorgabe 'Bewegung reduzieren' aktiv: Partikeleffekte sind gedämpft.");
    }
    if ((metrics?.failed_commands_24h ?? 0) > 0) {
      items.push(`Fehler in 24h: ${metrics?.failed_commands_24h ?? 0}.`);
    }
    if (guardBlockedCount > 0) {
      items.push(`GUARD_BLOCKED in 24h: ${guardBlockedCount}.`);
    }
    if (items.length === 0) {
      items.push("Keine Warnungen. Konfiguration ist stabil.");
    }
    return items;
  }, [studio, prefersReducedMotion, metrics?.failed_commands_24h, guardBlockedCount]);

  const navBadges = useMemo<Partial<Record<Page, number>>>(
    () => ({
      trades: tradeSeries.length > 0 ? Math.min(99, tradeSeries.length) : 0,
      risk: normalizedStatus?.risk_state === "normal" ? 0 : 1,
      logs: errors.length > 0 ? Math.min(99, errors.length) : 0,
      settings:
        validationMessages.length === 1 &&
        validationMessages[0] === "Keine Warnungen. Konfiguration ist stabil."
          ? 0
          : Math.min(99, validationMessages.length),
    }),
    [tradeSeries.length, normalizedStatus?.risk_state, errors.length, validationMessages],
  );

  const presetBaseline = useMemo(
    () => ({
      version: STUDIO_VERSION,
      preset: studio.preset,
      ...createPreset(studio.preset),
    }),
    [studio.preset],
  );

  const currentConfig = useMemo(
    () => ({
      version: STUDIO_VERSION,
      ...studio,
    }),
    [studio],
  );

  const configDiff = useMemo(
    () =>
      buildDiff(
        JSON.stringify(presetBaseline, null, 2),
        JSON.stringify(currentConfig, null, 2),
      ),
    [presetBaseline, currentConfig],
  );

  const tokenExport = useMemo(
    () =>
      JSON.stringify(
        {
          version: STUDIO_VERSION,
          studio: currentConfig,
        },
        null,
        2,
      ),
    [currentConfig],
  );

  const particlesDisabled =
    prefersReducedMotion || !studio.motion.enabled || studio.motion.intensity <= 0;

  const triggerParticleBurst = useCallback(
    (
      sourceElement: HTMLElement | null | undefined,
      color: string,
      direction?: ParticleDirection,
    ): void => {
      if (particlesDisabled) return;
      const field = particleFieldRef.current;
      if (!field) return;

      const fallbackX = window.innerWidth * 0.5;
      const fallbackY = 120;
      const rect = sourceElement?.getBoundingClientRect();
      const centerX = rect ? rect.left + rect.width / 2 : fallbackX;
      const centerY = rect ? rect.top + rect.height / 2 : fallbackY;
      const intensity = studio.motion.intensity / 100;

      field.burst({
        x: centerX,
        y: centerY,
        count: clamp(Math.round(studio.motion.density * (0.5 + intensity)), 4, 24),
        spreadRadius: 26 + intensity * 140,
        velocity: 120 + intensity * 280,
        rotationRange: 160,
        color,
        durationMs: studio.motion.durationMs,
        delayMs: studio.motion.delayMs,
        direction: direction ?? studio.motion.direction,
      });
    },
    [particlesDisabled, studio.motion],
  );

  useEffect(() => {
    if (!normalizedStatus?.state) return;
    const previous = previousStateRef.current;
    if (previous && previous !== normalizedStatus.state) {
      const signal =
        normalizedStatus.state === "RUNNING"
          ? { color: "#2dd4a0", direction: "up" as const }
          : normalizedStatus.state === "PAUSED"
          ? { color: "#f5a623", direction: "down" as const }
          : normalizedStatus.state === "STOPPED"
          ? { color: "#ef5350", direction: "away" as const }
          : { color: "#f5a623", direction: "radial" as const };
      triggerParticleBurst(statusCapsuleRef.current, signal.color, signal.direction);
      pushToast("info", `Statuswechsel: ${previous} -> ${normalizedStatus.state}`);
    }
    previousStateRef.current = normalizedStatus.state;
  }, [normalizedStatus?.state, triggerParticleBurst, pushToast]);

  const handleUnlock = useCallback(
    (token: string): void => {
      setApiToken(token);
      setIsLocked(false);
      setAuthHint(undefined);
      pushToast("success", "Anmeldung erfolgreich.");
    },
    [pushToast],
  );

  const handleLock = useCallback((): void => {
    clearApiToken();
    setIsLocked(true);
    setActivePage("dashboard");
    setAuthHint("Sitzung gesperrt.");
  }, []);

  const handleQuickAction = useCallback(
    async (
      commandType: CommandType,
      confirmToken?: string,
      sourceElement?: HTMLElement,
    ): Promise<void> => {
      const payload = buildCommandRequest(commandType, confirmToken);
      try {
        const response = await submitCommand(payload);
        pushToast(response.status === "success" ? "success" : "info", response.message);
        const signal = COMMAND_PARTICLE_SIGNAL[commandType];
        triggerParticleBurst(sourceElement, signal.color, signal.direction);
      } catch (error) {
        const message = String(error);
        pushToast("error", message);
        if (message.includes("GUARD_BLOCKED")) {
          triggerParticleBurst(sourceElement, "#ff9f43", "away");
        }
        throw error;
      }
    },
    [submitCommand, pushToast, triggerParticleBurst],
  );

  function applyPreset(presetId: UiPresetId): void {
    setStudio({
      preset: presetId,
      ...createPreset(presetId),
    });
    pushToast("info", `Preset "${PRESET_LABELS[presetId]}" aktiviert.`);
  }

  function saveCustomPreset(): void {
    window.localStorage.setItem(
      CUSTOM_PRESET_STORAGE_KEY,
      JSON.stringify({
        version: STUDIO_VERSION,
        studio,
      }),
    );
    setHasStoredCustomPreset(true);
    pushToast("success", "Eigenes Preset gespeichert.");
  }

  function restoreCustomPreset(): void {
    const loaded = loadCustomPreset();
    if (!loaded) {
      pushToast("error", "Kein gültiges eigenes Preset gefunden.");
      return;
    }
    setStudio(loaded);
    pushToast("success", "Eigenes Preset geladen.");
  }

  async function copyTokenExport(): Promise<void> {
    try {
      await navigator.clipboard.writeText(tokenExport);
      pushToast("success", "Token-JSON in die Zwischenablage kopiert.");
    } catch {
      pushToast("error", "Konnte Token-JSON nicht kopieren.");
    }
  }

  function importTokenConfig(): void {
    try {
      const parsed = JSON.parse(importDraft) as unknown;
      let candidate: Partial<StudioConfig> | undefined;
      if (isRecord(parsed) && "studio" in parsed && isRecord(parsed.studio)) {
        candidate = parsed.studio as Partial<StudioConfig>;
      } else if (isRecord(parsed)) {
        candidate = parsed as Partial<StudioConfig>;
      }
      if (!candidate) {
        throw new Error("Ungültiges JSON-Format.");
      }
      setStudio(sanitizeStudio(candidate));
      pushToast("success", "Studio-Konfiguration importiert.");
    } catch (error) {
      pushToast("error", `Import fehlgeschlagen: ${String(error)}`);
    }
  }

  function updateTheme<K extends keyof ThemeConfig>(key: K, value: ThemeConfig[K]): void {
    setStudio((current) => ({
      ...current,
      theme: { ...current.theme, [key]: value },
    }));
  }

  function updateLayout<K extends keyof LayoutConfig>(key: K, value: LayoutConfig[K]): void {
    setStudio((current) => ({
      ...current,
      layout: { ...current.layout, [key]: value },
    }));
  }

  function updateVisibility<K extends keyof VisibilityConfig>(
    key: K,
    value: VisibilityConfig[K],
  ): void {
    setStudio((current) => ({
      ...current,
      visibility: { ...current.visibility, [key]: value },
    }));
  }

  function updateMotion<K extends keyof MotionConfig>(key: K, value: MotionConfig[K]): void {
    setStudio((current) => ({
      ...current,
      motion: { ...current.motion, [key]: value },
    }));
  }

  const currentPageTitle = PAGE_TITLES[activePage];
  const statusLabel = normalizedStatus?.state ?? "STOPPED";

  if (isLocked) {
    return <LoginGate onUnlock={handleUnlock} hint={authHint} />;
  }

  return (
    <div className="app-layout">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        botState={normalizedStatus?.state ?? null}
        badges={navBadges}
        isDark={studio.theme.mode === "dark"}
        onToggleTheme={() =>
          updateTheme("mode", studio.theme.mode === "dark" ? "light" : "dark")
        }
        onLock={handleLock}
      />

      <main className="main-content">
        <header className="mobile-bar">
          <strong>GoldBot</strong>
          <span className="mobile-page-pill">{currentPageTitle}</span>
        </header>

        {studio.visibility.header ? (
          <header className="page-header reveal">
            <div>
              <h2>{currentPageTitle}</h2>
              <p className="page-header-sub">
                Echtzeit-Übersicht deines Trading-Systems mit konfigurierbaren Widgets und
                Animationen.
              </p>
            </div>
            <div className="header-actions">
              <button
                type="button"
                className="button-secondary"
                disabled={isRefreshing}
                onClick={() => void refresh()}
              >
                Aktualisieren
              </button>
            </div>
          </header>
        ) : null}

        {isInitialLoading ? <p className="loading-hint">Daten werden geladen ...</p> : null}

        {globalError && !globalError.toLowerCase().includes("nicht autorisiert") ? (
          <section className="global-error-box reveal delay-1">
            <strong>API-Fehler</strong>
            <p className="global-error">{globalError}</p>
            <div className="global-error-actions">
              <button type="button" className="button-secondary" onClick={() => void refresh()}>
                Erneut laden
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  clearApiToken();
                  setIsLocked(true);
                  setAuthHint("Token ungültig. Bitte neu anmelden.");
                }}
              >
                Neu anmelden
              </button>
            </div>
          </section>
        ) : null}

        {activePage === "dashboard" ? (
          <>
            {studio.visibility.statusStrip ? (
              <section className="status-kpi-strip reveal delay-1" role="region" aria-label="Status und Kennzahlen">
                <article
                  ref={statusCapsuleRef}
                  className={`status-card strip-card status-${statusLabel.toLowerCase()}`}
                >
                  <p className="label">Status</p>
                  {normalizedStatus ? (
                    <BotStateBadge state={normalizedStatus.state} />
                  ) : (
                    <span className="state-placeholder">--</span>
                  )}
                </article>
                <article className="status-card strip-card">
                  <p className="label">Uptime</p>
                  <strong>{formatDuration(normalizedStatus?.uptime_sec)}</strong>
                </article>
                <article className={`status-card strip-card ${integrityClass}`}>
                  <p className="label">Integrity</p>
                  <strong>{integrityScore}</strong>
                </article>
                <article className="status-card strip-card">
                  <p className="label">Engine</p>
                  <strong>{engineLatencyMs.toFixed(0)} ms</strong>
                </article>
                {kpis.map((item) => (
                  <KpiCard key={item.id} model={item} />
                ))}
              </section>
            ) : null}

            {studio.visibility.activity ? (
              <ActivityFeed className="reveal delay-2" actions={actions} />
            ) : null}

            {studio.visibility.chart ? (
              <ChartPanel className="reveal delay-3" series={tradeSeries} actions={actions} />
            ) : null}

            {studio.visibility.errors ? (
              <ErrorPanel className="reveal delay-4" errors={errors} />
            ) : null}
          </>
        ) : null}

        {activePage === "trades" ? (
          <>
            <ChartPanel className="reveal delay-1" series={tradeSeries} actions={actions} />
            <ActivityFeed className="reveal delay-2" actions={actions} />
          </>
        ) : null}

        {activePage === "risk" ? (
          <>
            <section className="risk-grid reveal delay-1">
              <article
                className={`panel risk-tile ${
                  normalizedStatus?.risk_state === "normal" ? "risk-safe" : "risk-danger"
                }`}
              >
                <h3>Risikostatus</h3>
                <p className="risk-value">{normalizedStatus?.risk_state ?? "normal"}</p>
                <small>Live-Zustand aus der Engine.</small>
              </article>
              <article className="panel risk-tile">
                <h3>Guard-Blockaden</h3>
                <p className="risk-value">{guardBlockedCount}</p>
                <small>Kritische Aktionen ohne CONFIRM.</small>
              </article>
              <article className="panel risk-tile">
                <h3>Fehler 24h</h3>
                <p className="risk-value">{metrics?.failed_commands_24h ?? 0}</p>
                <small>Fehlgeschlagene Kommandos in 24 Stunden.</small>
              </article>
              <article className="panel risk-tile">
                <h3>Integrity</h3>
                <p className="risk-value">{integrityScore}</p>
                <small>Abgeleitet aus Erfolg, Fehlern und Guard-Events.</small>
              </article>
            </section>

            <ErrorPanel className="reveal delay-2" errors={errors} />
          </>
        ) : null}

        {activePage === "logs" ? (
          <section className="split-zone reveal delay-1">
            <ActivityFeed actions={actions} />
            <ErrorPanel errors={errors} />
          </section>
        ) : null}

        {activePage === "settings" ? (
          <>
            <section className="panel reveal delay-1">
              <div className="section-header">
                <div>
                  <h2>Systemeinstellungen</h2>
                  <p className="section-subtitle">
                    Runtime-Einstellungen, Live-Diff und Validierungs-Assistent.
                  </p>
                </div>
                <button
                  type="button"
                  className="button-secondary btn-sm"
                  onClick={(event) =>
                    void handleQuickAction("RELOAD_CONFIG", "CONFIRM", event.currentTarget)
                  }
                >
                  Config neu laden
                </button>
              </div>

              <div className="config-meta">
                <span>
                  Polling: <strong>{Math.round(pollIntervalSeconds * 1000)} ms</strong>
                </span>
                <span>
                  Confirmations:{" "}
                  <strong>{settings?.confirmations_enabled ? "aktiv" : "deaktiviert"}</strong>
                </span>
                <span>
                  Stand:{" "}
                  <strong>
                    {settings?.updated_at
                      ? new Date(settings.updated_at).toLocaleString("de-DE")
                      : "--"}
                  </strong>
                </span>
              </div>

              <div className="settings-grid">
                <div className="config-diff">
                  <h3>Live-Diff (Preset -&gt; Aktuell)</h3>
                  <pre className="config-diff-code">{configDiff}</pre>
                </div>
                <div className="config-validation">
                  <h3>Validierungs-Assistent</h3>
                  <ul>
                    {validationMessages.map((message, index) => (
                      <li
                        key={`${message}-${index}`}
                        className={
                          message === "Keine Warnungen. Konfiguration ist stabil."
                            ? "validation-ok"
                            : "validation-warn"
                        }
                      >
                        {message}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="panel reveal delay-2">
              <div className="section-header">
                <div>
                  <h2>Theme- und Layout-Studio</h2>
                  <p className="section-subtitle">
                    Farben, Panels, Typografie, Presets und Animationen vollständig steuern.
                  </p>
                </div>
              </div>

              <div className="preset-row">
                {(["minimal", "professional", "cinematic"] as UiPresetId[]).map((presetId) => (
                  <button
                    key={presetId}
                    type="button"
                    className={`chip ${studio.preset === presetId ? "chip-active" : ""}`}
                    onClick={() => applyPreset(presetId)}
                  >
                    {PRESET_LABELS[presetId]}
                  </button>
                ))}
                <button type="button" className="button-secondary btn-sm" onClick={saveCustomPreset}>
                  Eigenes Preset speichern
                </button>
                <button
                  type="button"
                  className="button-secondary btn-sm"
                  onClick={restoreCustomPreset}
                  disabled={!hasStoredCustomPreset}
                >
                  Eigenes Preset laden
                </button>
              </div>

              <div className="studio-grid">
                <article className="studio-card">
                  <h3>Theme-Editor</h3>
                  <div className="studio-row">
                    <label className="field">
                      <span>Theme</span>
                      <select
                        value={studio.theme.mode}
                        onChange={(event) =>
                          updateTheme("mode", event.target.value === "light" ? "light" : "dark")
                        }
                      >
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>Kontrast</span>
                      <input
                        type="range"
                        min={90}
                        max={120}
                        value={studio.theme.contrast}
                        onChange={(event) =>
                          updateTheme("contrast", Number(event.target.value))
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Primärfarbe</span>
                      <input
                        type="color"
                        value={studio.theme.primary}
                        onChange={(event) => updateTheme("primary", event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>Akzentfarbe</span>
                      <input
                        type="color"
                        value={studio.theme.accent}
                        onChange={(event) => updateTheme("accent", event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>Fehlerfarbe</span>
                      <input
                        type="color"
                        value={studio.theme.error}
                        onChange={(event) => updateTheme("error", event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>Hintergrund</span>
                      <input
                        type="color"
                        value={studio.theme.background}
                        onChange={(event) => updateTheme("background", event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>Sans Font</span>
                      <select
                        value={studio.theme.fontSans}
                        onChange={(event) => updateTheme("fontSans", event.target.value)}
                      >
                        <option value="&quot;Inter&quot;, system-ui, sans-serif">Inter</option>
                        <option value="&quot;Space Grotesk&quot;, system-ui, sans-serif">
                          Space Grotesk
                        </option>
                        <option value="&quot;Manrope&quot;, system-ui, sans-serif">Manrope</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>Mono Font</span>
                      <select
                        value={studio.theme.fontMono}
                        onChange={(event) => updateTheme("fontMono", event.target.value)}
                      >
                        <option value="&quot;Roboto Mono&quot;, ui-monospace, monospace">
                          Roboto Mono
                        </option>
                        <option value="&quot;JetBrains Mono&quot;, ui-monospace, monospace">
                          JetBrains Mono
                        </option>
                        <option value="&quot;IBM Plex Mono&quot;, ui-monospace, monospace">
                          IBM Plex Mono
                        </option>
                      </select>
                    </label>
                    <label className="field field-wide">
                      <span>Schriftgröße ({studio.theme.fontSize}px)</span>
                      <input
                        type="range"
                        min={12}
                        max={18}
                        value={studio.theme.fontSize}
                        onChange={(event) =>
                          updateTheme("fontSize", Number(event.target.value))
                        }
                      />
                    </label>
                  </div>
                </article>

                <article className="studio-card">
                  <h3>Layout-Editor</h3>
                  <div className="toggle-row">
                    <span>Widgets sperren</span>
                    <input
                      type="checkbox"
                      checked={studio.layout.lockWidgets}
                      onChange={(event) =>
                        updateLayout("lockWidgets", event.target.checked)
                      }
                    />
                  </div>
                  <div className="toggle-row">
                    <span>Kompakte Karten</span>
                    <input
                      type="checkbox"
                      checked={studio.layout.compactCards}
                      onChange={(event) =>
                        updateLayout("compactCards", event.target.checked)
                      }
                    />
                  </div>
                  <label className="field">
                    <span>KPI-Spalten ({studio.layout.kpiColumns})</span>
                    <input
                      type="range"
                      min={2}
                      max={6}
                      value={studio.layout.kpiColumns}
                      disabled={studio.layout.lockWidgets}
                      onChange={(event) =>
                        updateLayout("kpiColumns", Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Panel-Abstand ({studio.layout.panelGap}px)</span>
                    <input
                      type="range"
                      min={8}
                      max={24}
                      value={studio.layout.panelGap}
                      disabled={studio.layout.lockWidgets}
                      onChange={(event) =>
                        updateLayout("panelGap", Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Split-Verhältnis ({studio.layout.splitLeftRatio.toFixed(1)})</span>
                    <input
                      type="range"
                      min={1}
                      max={2}
                      step={0.1}
                      value={studio.layout.splitLeftRatio}
                      disabled={studio.layout.lockWidgets}
                      onChange={(event) =>
                        updateLayout("splitLeftRatio", Number(event.target.value))
                      }
                    />
                  </label>
                </article>

                <article className="studio-card">
                  <h3>Sichtbarkeit</h3>
                  <div className="visibility-grid">
                    <label className="visibility-item">
                      <input
                        type="checkbox"
                        checked={studio.visibility.header}
                        onChange={(event) =>
                          updateVisibility("header", event.target.checked)
                        }
                      />
                      Header
                    </label>
                    <label className="visibility-item">
                      <input
                        type="checkbox"
                        checked={studio.visibility.statusStrip}
                        onChange={(event) =>
                          updateVisibility("statusStrip", event.target.checked)
                        }
                      />
                      Statuszeile
                    </label>
                    <label className="visibility-item">
                      <input
                        type="checkbox"
                        checked={studio.visibility.chart}
                        onChange={(event) => updateVisibility("chart", event.target.checked)}
                      />
                      Chart
                    </label>
                    <label className="visibility-item">
                      <input
                        type="checkbox"
                        checked={studio.visibility.activity}
                        onChange={(event) => updateVisibility("activity", event.target.checked)}
                      />
                      Log-Konsole
                    </label>
                    <label className="visibility-item">
                      <input
                        type="checkbox"
                        checked={studio.visibility.errors}
                        onChange={(event) => updateVisibility("errors", event.target.checked)}
                      />
                      Fehlerpanel
                    </label>
                  </div>
                </article>

                <article className="studio-card">
                  <h3>Animationssystem</h3>
                  <div className="toggle-row">
                    <span>Animationen aktiv</span>
                    <input
                      type="checkbox"
                      checked={studio.motion.enabled}
                      onChange={(event) => updateMotion("enabled", event.target.checked)}
                    />
                  </div>
                  <label className="field">
                    <span>Intensität ({studio.motion.intensity})</span>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={studio.motion.intensity}
                      onChange={(event) =>
                        updateMotion("intensity", Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Dichte ({studio.motion.density})</span>
                    <input
                      type="range"
                      min={4}
                      max={24}
                      value={studio.motion.density}
                      onChange={(event) => updateMotion("density", Number(event.target.value))}
                    />
                  </label>
                  <label className="field">
                    <span>Dauer ({studio.motion.durationMs}ms)</span>
                    <input
                      type="range"
                      min={300}
                      max={1200}
                      step={20}
                      value={studio.motion.durationMs}
                      onChange={(event) =>
                        updateMotion("durationMs", Number(event.target.value))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Verzögerung ({studio.motion.delayMs}ms)</span>
                    <input
                      type="range"
                      min={0}
                      max={180}
                      step={2}
                      value={studio.motion.delayMs}
                      onChange={(event) => updateMotion("delayMs", Number(event.target.value))}
                    />
                  </label>
                  <label className="field">
                    <span>Richtung</span>
                    <select
                      value={studio.motion.direction}
                      onChange={(event) =>
                        updateMotion("direction", event.target.value as ParticleDirection)
                      }
                    >
                      <option value="radial">radial</option>
                      <option value="up">nach oben</option>
                      <option value="down">nach unten</option>
                      <option value="away">auseinander</option>
                    </select>
                  </label>
                  <p className="settings-note">
                    Bei aktiver Systemoption "Bewegung reduzieren" werden Partikeleffekte automatisch
                    gedrosselt.
                  </p>
                </article>
              </div>

              <div className="token-actions">
                <button
                  type="button"
                  className="button-secondary btn-sm"
                  onClick={() => setShowTokenExport((value) => !value)}
                >
                  {showTokenExport ? "Token-Export ausblenden" : "Token-Export anzeigen"}
                </button>
                <button
                  type="button"
                  className="button-secondary btn-sm"
                  onClick={() => void copyTokenExport()}
                >
                  Token-JSON kopieren
                </button>
              </div>

              {showTokenExport ? (
                <textarea className="token-output" readOnly value={tokenExport} rows={12} />
              ) : null}

              <label className="field field-wide">
                <span>Token-JSON importieren</span>
                <textarea
                  className="token-input"
                  value={importDraft}
                  onChange={(event) => setImportDraft(event.target.value)}
                  rows={8}
                  placeholder='{"studio": {...}}'
                />
              </label>
              <button type="button" className="button-secondary btn-sm" onClick={importTokenConfig}>
                Import anwenden
              </button>
            </section>
          </>
        ) : null}
      </main>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      <ParticleField ref={particleFieldRef} disabled={particlesDisabled} />
    </div>
  );
}
