# Phase 12: Korrelations-Engine - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via user directive)

<domain>
## Phase Boundary

Inter-Market-Korrelationen (DXY, US10Y, Silber, VIX, S&P500) als zusaetzliche Signalquelle fuer das Gold-Trading-System. Scope: Asset-Daten-Retrieval, Rolling Correlation ueber mehrere Zeitfenster, Korrelations-Regime-Detection (normal/breakdown/inversion), Divergenz-Scanner (Gold vs. DXY, Gold vs. US10Y), Lead-Lag-Analyse und ML-Features (correlation_dxy, correlation_us10y, divergence_score, lead_lag_score).

Requirements: CORR-01, CORR-02, CORR-03, CORR-04.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
Alle Implementierungs-Entscheidungen liegen bei Claude — Diskussionsphase wurde uebersprungen. Orientiere dich an ROADMAP-Phase-Goal, UAT-Kriterien, RESEARCH.md und bestehenden Codebase-Konventionen (Phase 11 News-Sentiment als Referenz fuer Feature-Integration in signal_generator / ML-Pipeline).

</decisions>

<code_context>
## Existing Code Insights

Codebase-Kontext wird waehrend Plan-Phase Research-Agent gesammelt. Referenzen: Phase 11 (News-Sentiment) fuer Feature-Integration, bestehende ML-Feature-Pipeline, signal_generator.py.

</code_context>

<specifics>
## Specific Ideas

Keine spezifischen Anforderungen ausser UAT — Diskussionsphase uebersprungen. Siehe ROADMAP Phase-Scope und RESEARCH.md.

</specifics>

<deferred>
## Deferred Ideas

Keine — Diskussionsphase uebersprungen.

</deferred>
