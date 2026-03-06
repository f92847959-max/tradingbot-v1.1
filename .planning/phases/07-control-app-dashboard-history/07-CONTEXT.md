# Phase 7: Control App - Dashboard & History - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Build and refine the control app dashboard and history experience for Phase 7:
- trade history visibility and readability
- model/performance information presentation
- live status/notification feedback in UI

Scope is implementation quality of existing dashboard/history capabilities (layout, visual system, interaction rhythm, micro-animation behavior), not new product modules.

</domain>

<decisions>
## Implementation Decisions

### 1) Density, Rhythm, and Block Sizing
- Activity Feed and Error View should use adaptive heights by viewport (not fixed short/long).
- Status + KPI must be presented as one horizontal strip with scroll-snap, Apple-like cleanliness.
- Vertical rhythm should be airy: 16px spacing between major blocks.
- Dashboard should focus on live data; action controls should not be in dashboard main flow (actions stay in risk/settings contexts).

### 2) Visual Direction
- Primary style direction: Minimal Dark.
- Visual feel: very clean, glassy, futuristic (calm, not noisy).
- Color system: monochrome-first palette with restrained accents.
- Motion style: expressive (allowed up to ~500ms where appropriate), still controlled.

### 3) Action Hierarchy and Critical Interactions
- Primary action emphasis: both `START_BOT` and `RESUME_TRADING`.
- Critical actions should use subdued warning red with pulse feedback (not aggressive permanent red blocks).
- Double-click requirement hint should be compact (mini label), not a large text block.
- Confirm interaction for critical actions: 1s timer ring + second click required.

### 4) Chart and Log Readability
- Default chart layer combination: EMA + VWAP.
- Event markers: small and color-coded by status (minimal footprint, still distinguishable).
- Logs: grouped and compact; timestamps smaller and visually de-emphasized.
- JSON details in logs/errors: accordion behavior with smooth ~300ms expansion.

### 5) Motion and System Feedback (Added Requirement)
- Status transition (`STOPPED -> RUNNING`): color fade + subtle pulse-in on status badge.
- Heartbeat indicator: small pulse every 3s to show system activity.
- Latency badges: subtle green glow on healthy values; warning wobble on degraded values.
- Chart layers (EMA/VWAP/RSI): fade/slide-in when toggled (~200ms target behavior).
- New event markers: soft drop-in effect.
- Replay mode: animated moving cursor over timeline.
- New log entries: slide-down + short highlight flash.
- Guard-blocked feedback: short shake to indicate blocked command.
- Buttons: hover-lift with soft shadow; critical hover pulse for danger awareness.
- Navigation: animated active-tab underline; short fade-through between sections/tabs.
- Theme switch (light/dark): smooth cross-fade (~300ms).

### Claude's Discretion
- Exact easing curves, duration fine-tuning per component, and per-device motion reduction behavior.
- Exact monochrome token values and accent intensity to preserve contrast and readability.
- Final breakpoint thresholds for adaptive panel heights.
- Whether some optional “wow” animations are enabled by default or gated behind a setting.

</decisions>

<specifics>
## Specific Ideas

- “Wie bei Apple”: one-line strip rhythm, calm spacing, no cluttered debug look.
- Keep chart-layer combinations practical:
  - EMA + VWAP for trend + fair price
  - RSI + events for decision comparison
  - VWAP-only mode for calmer/mean-reversion reading
- Premium target: less visual harshness, clear priorities, smooth micro-feedback.

</specifics>

<deferred>
## Deferred Ideas

- Large startup Lottie cinematic sequence is optional and should be treated as non-blocking polish unless explicitly prioritized in planning.
- Additional “wow-only” effects (e.g., stronger risk wave / position flourish variants) should not displace core readability and history/dashboard usability.

</deferred>

---

*Phase: 07-control-app-dashboard-history*  
*Context gathered: 2026-03-06*
