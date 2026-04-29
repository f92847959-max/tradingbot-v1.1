# Roadmap: GoldBot 2

## Milestone: v1.0 — Profitable Demo Trading

**Goal:** Bot trades profitably on Capital.com demo account with a clean, maintainable codebase and functional web control interface.

---

### Phase 1: Code Cleanup & Project Foundation
**Goal:** Clean, well-structured codebase ready for improvements
**Requirements:** CODE-01, CODE-02, CODE-03, CODE-04, CODE-05, CODE-06
**Plans:** 4 plans

Plans:
- [x] 01-01-PLAN.md — Gitignore update and German-to-English comment translation
- [x] 01-02-PLAN.md — main.py refactor into trading/ mixin modules + lazy import fixes
- [x] 01-03-PLAN.md — trainer.py split into trade_filter.py and pipeline.py
- [x] 01-04-PLAN.md — Full test suite verification (no regressions)

---

### Phase 2: Training Pipeline — Walk-Forward Validation
**Goal:** Training produces models validated with walk-forward method, preventing overfitting
**Requirements:** TRAIN-01, TRAIN-02, TRAIN-05, TRAIN-06, TRAIN-07
**Plans:** 3 plans

Plans:
- [x] 02-01-PLAN.md — Walk-forward validation engine + 6-month data validation
- [x] 02-02-PLAN.md — Model versioning with version.json and production pointer
- [x] 02-03-PLAN.md — Training report generation + end-to-end integration

---

### Phase 3: Feature Engineering — SHAP & Pruning
**Goal:** Remove noisy features, keep only those that contribute to model performance
**Requirements:** TRAIN-03, TRAIN-04
**Plans:** 3 plans

Plans:
- [x] 03-01-PLAN.md — SHAP importance module + dependencies
- [x] 03-02-PLAN.md — Replace feature selection with SHAP pruning in walk-forward windows
- [x] 03-03-PLAN.md — Wire SHAP persistence into pipeline and version directory

---

### Phase 4: Strategy Improvements — Dynamic TP/SL & Regime Detection
**Goal:** Trading strategy adapts to market conditions instead of using fixed parameters
**Requirements:** STRAT-01, STRAT-02, STRAT-03, STRAT-04
**Plans:** 3 plans

Plans:
- [x] 04-01-PLAN.md — Regime detection foundation
- [x] 04-02-PLAN.md — Dynamic ATR-based label generation and backtester alignment
- [x] 04-03-PLAN.md — Regime-aware strategy parameters and ATR position sizing

---

### Phase 5: Backtesting & Validation
**Goal:** Proven strategy performance on historical data with realistic conditions
**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04
**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Commission support, BacktestRunner, and BacktestReport
- [x] 05-02-PLAN.md — CLI backtest script and end-to-end integration test

---

### Phase 6: MiroFish Swarm Intelligence Integration
**Goal:** MiroFish multi-agent prediction engine integrated to enhance gold trading signals with swarm intelligence
**Requirements:** MIRO-01, MIRO-02, MIRO-03, MIRO-04, MIRO-05, MIRO-06
**Plans:** 3 plans

Plans:
- [x] 06-01-PLAN.md — MiroFish setup
- [x] 06-02-PLAN.md — MiroFishClient module
- [x] 06-03-PLAN.md — Trading system wiring

---

### Phase 8: Wirtschaftskalender-Integration
**Goal:** Automatischer Schutz vor Verlusten bei High-Impact Events durch Trading-Pausen und Position-Management
**Requirements:** ECAL-01, ECAL-02, ECAL-03, ECAL-04
**Plans:** 2 plans

Plans:
- [x] 08-01-PLAN.md — Economic calendar module
- [x] 08-02-PLAN.md — Calendar wiring

---

### Phase 9: Advanced Risk & Position Sizing
**Goal:** Dynamische Positionsgroessen-Berechnung mit Kelly Criterion, Volatilitaets-Anpassung und Portfolio Heat Management
**Requirements:** RISK-01, RISK-02, RISK-03, RISK-04, RISK-05
**Plans:** 3 plans

Plans:
- [x] 09-01-PLAN.md — Kelly Criterion and advanced position sizing
- [x] 09-02-PLAN.md — Monte Carlo simulation and drawdown distribution
- [x] 09-03-PLAN.md — Portfolio Heat Management and Equity Curve Filter

---

### Phase 10: Smart Exit Engine
**Goal:** Intelligentes dynamisches TP/SL-Management statt fixer Werte — ATR, Struktur und Trailing fuer bessere Exits
**Requirements:** EXIT-01, EXIT-02, EXIT-03, EXIT-04, EXIT-05
**Plans:** 3 plans

Plans:
- [x] 10-01-PLAN.md — Dynamic SL/TP core and exit signal detector
- [x] 10-02-PLAN.md — ATR trailing stop with breakeven after +1R
- [x] 10-03-PLAN.md — TP1 partial close decision manager

---

### Phase 11: News-Sentiment-Analyse
**Goal:** Echtzeit-Nachrichtenanalyse mit automatischer Sentiment-Bewertung als ML-Feature und MiroFish-Input
**Requirements:** SENT-01, SENT-02, SENT-03, SENT-04, SENT-05
**Plans:** 2 plans

Plans:
- [x] 11-01-PLAN.md — News sentiment database and models
- [ ] 11-02-PLAN.md — RSS fetcher and FinBERT scoring

---

### Phase 12: Korrelations-Engine
**Goal:** Inter-Market-Korrelationen (DXY, US10Y, Silber, VIX) als zusaetzliche Signalquelle
**Requirements:** CORR-01, CORR-02, CORR-03, CORR-04
**Plans:** 2 plans

Plans:
- [x] 12-01-PLAN.md — Asset fetcher and correlation calculator
- [ ] 12-02-PLAN.md — Correlation divergence signals and ML features

---

### Phase 12.1: AI Confidence Calibration & Decision Governance
**Goal:** Kalibrierte AI-Confidence und datenbasierte Decision-Governance einfuehren
**Requirements:** CONF-01, CONF-02, CONF-03, CONF-04, CONF-05
**Plans:** 3 plans

Plans:
- [x] 12.1-01-PLAN.md — Calibration artifacts and threshold tuning
- [x] 12.1-02-PLAN.md — DecisionGovernor runtime integration
- [x] 12.1-03-PLAN.md — Governance audit logging and monitoring

---

### Phase 12.3: AI Indicator Specialist Training
**Goal:** Specialist-AI-Modell fuer einen zweiten Indikator-/Feature-Block trainieren
**Requirements:** AITRAIN-01, AITRAIN-02, AITRAIN-03, AITRAIN-04
**Plans:** 3 plans

Plans:
- [x] 12.3-01-PLAN.md — Specialist feature block
- [x] 12.3-02-PLAN.md — Specialist training pipeline
- [x] 12.3-03-PLAN.md — Runtime specialist overlay

---

### Phase 12.4: Exit AI Training & Baseline Evaluation
**Goal:** Exit-AI als separates Modell trainieren und leakage-sicher vergleichen
**Requirements:** EXITAI-01, EXITAI-02, EXITAI-03, EXITAI-04
**Plans:** 3 plans

Plans:
- [x] 12.4-01-PLAN.md — Exit snapshot dataset and action labels
- [x] 12.4-02-PLAN.md — Exit AI training pipeline and baseline comparison
- [x] 12.4-03-PLAN.md — Exit AI calibration and promotion gate

---

### Phase 12.5: Exit AI Runtime Integration & Governance
**Goal:** Exit-AI als governter Overlay-Entscheider integrieren
**Requirements:** EXITAI-05, EXITAI-06, EXITAI-07, EXITAI-08
**Plans:** 3 plans

Plans:
- [x] 12.5-01-PLAN.md — Exit AI runtime loader and no-risk-widening guardrails
- [x] 12.5-02-PLAN.md — Order manager integration for exit actions
- [x] 12.5-03-PLAN.md — Exit AI audit logging and drift monitoring

---

### Phase 12.6: Existing AI Autonomy Distillation
**Goal:** Bestehende KI-Kette autonomer machen durch Kausale Distillation
**Requirements:** AUTOAI-01, AUTOAI-02, AUTOAI-03, AUTOAI-04, AUTOAI-05, AUTOAI-06
**Plans:** 3 plans

Plans:
- [x] 12.6-01-PLAN.md — Teacher snapshot capture
- [x] 12.6-02-PLAN.md — Learned decision head and promotion gate
- [x] 12.6-03-PLAN.md — Shadow rollout and guarded runtime selection

---

### Phase 12.7: AI Training Pipeline Hardening
**Goal:** Haerten der Pipeline fuer belastbare historische Datenabdeckung und Promotion-Gates
**Requirements:** AITRAIN2-01, AITRAIN2-02, AITRAIN2-03, AITRAIN2-04, AITRAIN2-05
**Plans:** 3 plans

Plans:
- [ ] 12.7-01-PLAN.md — Data coverage preflight and row-loss telemetry
- [ ] 12.7-02-PLAN.md — Causal label builder and leakage-safe splits
- [ ] 12.7-03-PLAN.md — Walk-forward promotion gate and calibration report

---

### Phase 13: Orderbuch-Analyse
**Goal:** Order Flow / DOM Analyse zur Erkennung institutioneller Aktivitaet
**Requirements:** FLOW-01, FLOW-02, FLOW-03, FLOW-04
**Plans:** 3 plans

Plans:
- [x] 13-01-PLAN.md — OHLCV-derived order-flow feature core
- [x] 13-02-PLAN.md — Optional L1 quote-flow enrichment
- [x] 13-03-PLAN.md — FeatureEngineer/ML integration

---

### Phase 14: Elliott Wave Theorie Integration
**Goal:** Automatische Wellenzaehlung und Fibonacci-Targets aus Wellen-Verhaeltnissen
**Requirements:** EWT-01, EWT-02, EWT-03, EWT-04
**Plans:** 3 plans

Plans:
- [ ] 14-01-PLAN.md — Wave detection core (1-5, A-B-C)
- [ ] 14-02-PLAN.md — Fibonacci targets from wave ratios
- [ ] 14-03-PLAN.md — Strategy integration and ML features

---

### Phase 15: Fibonacci Engine & S/R Zones
**Goal:** Automatisierung der S/R-Zonen-Erkennung und Fibonacci-Analyse zur Identifizierung von Confluence-Zonen.
**Requirements:** SR-01, FIB-01, TREND-01, CONF-01, FEAT-15
**Plans:** 3 plans

Plans:
- [ ] 15-01-PLAN.md — Support/Resistance & Fibonacci Core Engines (SR-01, FIB-01)
- [ ] 15-02-PLAN.md — Trendline Engine & Confluence Scoring (TREND-01, CONF-01)
- [ ] 15-03-PLAN.md — System Integration & ML Features (FEAT-15)

---

### Phase 16: Channel Formation (Kanalbildung)
**Goal:** Automatische Erkennung von Preis-Kanaelen und Trendlinien mit SMC Fakeout-Schutz.
**Requirements:** CHAN-01, CHAN-02, CHAN-03, CHAN-04
**Plans:** 3 plans

Plans:
- [x] 16-01-PLAN.md — Statistical Channel Engine (LR Channels)
- [x] 16-02-PLAN.md — Structural Trendline Engine (Pivot Trendlines)
- [x] 16-03-PLAN.md — Breakout Detection & SMC Integration

---

### Phase 17: Demo Trading Validation
**Goal:** Bot runs profitably on demo account, proving the system works
**Requirements:** DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Plans:** 3 plans

Plans:
- [ ] 17-01-PLAN.md — Stability hardening (keepalive, heartbeat, reasoning defaults, daily stats)
- [ ] 17-02-PLAN.md — Operational scripts (preflight check, demo report, PowerShell restart wrapper)
- [ ] 17-03-PLAN.md — Demo readiness verification and operator checkpoint

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-04-28 — Phase 16 planned and Phase 17 renumbered*
