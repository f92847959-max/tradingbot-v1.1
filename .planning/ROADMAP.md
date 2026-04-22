# Roadmap: GoldBot 2

## Milestone: v1.0 — Profitable Demo Trading

**Goal:** Bot trades profitably on Capital.com demo account with a clean, maintainable codebase and functional web control interface.

---

### Phase 1: Code Cleanup & Project Foundation
**Goal:** Clean, well-structured codebase ready for improvements
**Requirements:** CODE-01, CODE-02, CODE-03, CODE-04, CODE-05, CODE-06
**Plans:** 4 plans

Plans:
- [ ] 01-01-PLAN.md — Gitignore update and German-to-English comment translation
- [ ] 01-02-PLAN.md — main.py refactor into trading/ mixin modules + lazy import fixes
- [ ] 01-03-PLAN.md — trainer.py split into trade_filter.py and pipeline.py
- [ ] 01-04-PLAN.md — Full test suite verification (no regressions)

**Scope:**
- Refactor main.py into smaller modules
- Split trainer.py into sub-modules
- Fix lazy imports
- Standardize comments to English
- Add proper .gitignore
- Verify all existing tests still pass

**UAT:**
- [ ] main.py < 200 lines, trading logic in separate module
- [ ] trainer.py split into files < 300 lines each
- [ ] No lazy imports inside methods
- [ ] .gitignore covers .venv, __pycache__, .env, logs, saved_models
- [ ] All existing tests pass

---

### Phase 2: Training Pipeline — Walk-Forward Validation
**Goal:** Training produces models validated with walk-forward method, preventing overfitting
**Requirements:** TRAIN-01, TRAIN-02, TRAIN-05, TRAIN-06, TRAIN-07
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — Walk-forward validation engine + 6-month data validation
- [ ] 02-02-PLAN.md — Model versioning with version.json and production pointer
- [ ] 02-03-PLAN.md — Training report generation + end-to-end integration

**Scope:**
- Implement walk-forward validation (train on rolling window, test on next period)
- Ensure features computed after split (no data leakage)
- Add model versioning (save metadata per training run)
- Generate walk-forward training report
- Ensure minimum 6 months of data used

**UAT:**
- [ ] Walk-forward validation with at least 5 windows
- [ ] Features computed per-window, not on full dataset
- [ ] Each model save includes version.json with date, params, metrics
- [ ] Training report shows metrics per window

---

### Phase 3: Feature Engineering — SHAP & Pruning
**Goal:** Remove noisy features, keep only those that contribute to model performance
**Requirements:** TRAIN-03, TRAIN-04
**Plans:** 3 plans

Plans:
- [ ] 03-01-PLAN.md — SHAP importance module + dependencies (compute_shap_importance, save_feature_importance_chart)
- [ ] 03-02-PLAN.md — Replace feature selection with SHAP pruning in walk-forward windows
- [ ] 03-03-PLAN.md — Wire SHAP persistence into pipeline and version directory

**Scope:**
- Integrate SHAP for feature importance analysis
- Automatic pruning of low-importance features
- Compare model performance with full vs pruned feature sets
- Visualize feature importance

**UAT:**
- [ ] SHAP values computed and saved per training run
- [ ] Feature pruning removes bottom 50% by importance
- [ ] Pruned model performance >= full model performance
- [ ] Feature importance chart saved with training report

---

### Phase 4: Strategy Improvements — Dynamic TP/SL & Regime Detection
**Goal:** Trading strategy adapts to market conditions instead of using fixed parameters
**Requirements:** STRAT-01, STRAT-02, STRAT-03, STRAT-04
**Plans:** 3 plans

Plans:
- [ ] 04-01-PLAN.md — Regime detection foundation (MarketRegime enum, RegimeDetector, REGIME_PARAMS)
- [ ] 04-02-PLAN.md — Dynamic ATR-based label generation and backtester alignment
- [ ] 04-03-PLAN.md — Regime-aware strategy parameters and ATR position sizing

**Scope:**
- Replace fixed 50/30 pip TP/SL with ATR-based dynamic levels
- Implement market regime detection (trending/ranging/volatile)
- Adjust strategy parameters per regime
- ATR-based position sizing

**UAT:**
- [ ] TP/SL calculated from ATR, not hardcoded
- [ ] Regime detector classifies market into at least 3 states
- [ ] Different strategy params applied per regime
- [ ] Position size adapts to ATR

---

### Phase 5: Backtesting & Validation
**Goal:** Proven strategy performance on historical data with realistic conditions
**Requirements:** BACK-01, BACK-02, BACK-03, BACK-04
**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Commission support, BacktestRunner, and BacktestReport with consistency checks
- [x] 05-02-PLAN.md — CLI backtest script and end-to-end integration test

**Scope:**
- Build/improve backtesting framework with realistic costs
- Run walk-forward backtest across multiple time periods
- Generate comprehensive performance report
- Validate consistency across periods

**UAT:**
- [x] Backtest includes spread, slippage, commissions
- [x] Report shows Sharpe ratio, max drawdown, win rate, profit factor
- [x] Walk-forward backtest shows positive results in >60% of windows
- [x] No single window has >20% drawdown

---

### Phase 6: MiroFish Swarm Intelligence Integration
**Goal:** MiroFish multi-agent prediction engine integrated to enhance gold trading signals with swarm intelligence
**Requirements:** MIRO-01, MIRO-02, MIRO-03, MIRO-04, MIRO-05, MIRO-06
**Plans:** 3/3 plans complete

Plans:
- [x] 06-01-PLAN.md — MiroFish setup: seed templates, settings extension, startup script (MIRO-01, MIRO-02, MIRO-03)
- [x] 06-02-PLAN.md — MiroFishClient module: simulation pipeline, cache, cost limiter, veto logic, tests (MIRO-04, MIRO-05, MIRO-06)
- [x] 06-03-PLAN.md — Trading system wiring: signal_generator veto check, lifecycle background task, integration tests

**System-Profil (zugeschnitten):**
- Windows 11, AMD Ryzen 5 4500 (6C/12T), 16 GB RAM, GTX 1650 4GB
- Python 3.12.10, Node.js 25.6, PyTorch 2.10
- LLM: OpenAI API (gpt-4o-mini) — Ollama gemma3:1b zu klein fuer MiroFish
- Kein Docker, kein Neo4j (nicht noetig)
- Package Manager: uv (noetig fuer camel-oasis Dependency)
- Externer Dienst: Zep Cloud (kostenloser Tier, Pflicht fuer Knowledge Graph)

**Scope:**
- `uv` Package Manager installieren (camel-oasis braucht uv statt pip)
- Zep Cloud Account anlegen (app.getzep.com, Free Tier)
- MiroFish klonen (github.com/666ghj/MiroFish) nach `mirofish/` im Projekt
- `.env` konfigurieren: LLM_API_KEY (OpenAI), ZEP_API_KEY, LLM_MODEL_NAME=gpt-4o-mini
- MiroFish Backend (Flask :5001) starten und Health-Check verifizieren
- Gold-spezifische Seed-Templates erstellen (Marktdaten + Indikatoren als Markdown/TXT)
- MiroFish REST-API Python-Client in `ai_engine/mirofish_client.py` bauen
- Agenten-Profile fuer Gold-Markt konfigurieren (Trader, Analysten, Zentralbanker, etc.)
- MiroFish-Predictions in `trading/signal_generator.py` als zusaetzliches Signal einbauen
- Ensemble-Gewichtung: XGBoost/LightGBM + MiroFish Swarm Score kombinieren
- API-Kosten-Limiter einbauen (max Simulationen pro Tag, Token-Budget)

**UAT:**
- [ ] `uv` installiert und `uv pip install` funktioniert auf Windows 11
- [ ] Zep Cloud API Key funktioniert (Graph-Erstellung erfolgreich)
- [ ] MiroFish Backend startet auf localhost:5001 (Flask)
- [ ] POST /api/graph/ontology/generate gibt JSON-Antwort mit Gold-Ontologie
- [ ] Gold-Seed-Template mit XAUUSD-Daten erzeugt Agenten-Simulation
- [ ] Simulation laeuft mit gpt-4o-mini als LLM (kein lokales Modell)
- [ ] mirofish_client.py kann Simulation starten und Ergebnis abholen
- [ ] MiroFish-Score in signal_generator.py verfuegbar als Signal-Komponente
- [ ] API-Kosten pro Simulation unter $0.50 (gpt-4o-mini, 10-20 Agenten)
- [ ] RAM-Verbrauch unter 4 GB waehrend Simulation (16 GB gesamt)

---

### Phase 8: Wirtschaftskalender-Integration
**Goal:** Automatischer Schutz vor Verlusten bei High-Impact Events (NFP, FOMC, CPI) durch Trading-Pausen und Position-Management
**Requirements:** ECAL-01, ECAL-02, ECAL-03, ECAL-04
**Plans:** 2/2 plans complete

Plans:
- [x] 08-01-PLAN.md — Economic calendar module: models, fetcher, filter, rules, service facade
- [x] 08-02-PLAN.md — Calendar wiring: trading loop veto, force-close, lifecycle refresh, 57 tests

**Scope:**
- Wirtschaftskalender-Daten abrufen (Investing.com / ForexFactory)
- Gold-relevante Events filtern (USD, EUR, Zinsen, Inflation)
- Trading-Regeln: kein neuer Trade 30min vor High-Impact, Position schliessen bei Extrem-Events
- Historische Event-Daten fuer Backtesting speichern
- Integration in signal_generator.py als Veto-Logik

**UAT:**
- [x] Kalender-Daten werden regelmaessig abgerufen und gefiltert
- [x] High-Impact Events blockieren neue Trades automatisch
- [x] Bestehende Positionen werden bei Extrem-Events geschlossen
- [x] Historische Events fuer Backtesting verfuegbar

---

### Phase 9: Advanced Risk & Position Sizing
**Goal:** Dynamische Positionsgroessen-Berechnung mit Kelly Criterion, Volatilitaets-Anpassung und Portfolio Heat Management
**Requirements:** RISK-01, RISK-02, RISK-03, RISK-04, RISK-05

**Scope:**
- Kelly Criterion (optimal f) basierend auf Win-Rate und RRR
- Volatilitaets-basiertes Sizing (ATR-normalisiert)
- Portfolio Heat: max 5% Gesamt-Risiko offen
- Monte Carlo Simulation (1000 Pfade, Drawdown-Verteilung)
- Equity Curve Filter (kein Trading bei Drawdown > Threshold)

**UAT:**
- [x] Position Size berechnet sich dynamisch nach Kelly/Volatilitaet
- [x] Portfolio Heat ueberschreitet nie 5% des Kontostands
- [x] Monte Carlo zeigt Drawdown-Verteilung und Confidence Intervals
- [x] Equity Curve Filter stoppt Trading bei starkem Drawdown
- [x] Alle Sizing-Entscheidungen geloggt mit Begruendung

---

### Phase 10: Smart Exit Engine
**Goal:** Intelligentes dynamisches TP/SL-Management statt fixer Werte — ATR, Struktur und Trailing fuer bessere Exits
**Requirements:** EXIT-01, EXIT-02, EXIT-03, EXIT-04, EXIT-05
**Plans:** 3/3 plans complete

Plans:
- [x] 10-01-PLAN.md — Dynamic SL/TP core and exit signal detector
- [x] 10-02-PLAN.md — ATR trailing stop with breakeven after +1R
- [x] 10-03-PLAN.md — TP1 partial close decision manager

**Scope:**
- Dynamischer SL: ATR-basiert + unter/ueber Struktur-Level
- Dynamischer TP: Fibonacci Extensions, naechste S/R-Zone
- Trailing Stop: ATR-Trail, Breakeven nach +1R
- Partial Close: 50% bei TP1, Rest mit Trailing
- Exit-Signale: Reversal-Kerzen, Momentum-Divergenz

**UAT:**
- [x] SL wird dynamisch aus ATR + Struktur berechnet, nicht fix
- [x] TP passt sich an Marktbedingungen an (Fibonacci/S/R)
- [x] Trailing Stop aktiviert sich nach definiertem Gewinn
- [x] Partial Close schliesst Teilposition bei TP1
- [x] Exit-Signale erkennen Reversals und schliessen frueh

---

---

### Phase 11: News-Sentiment-Analyse
**Goal:** Echtzeit-Nachrichtenanalyse mit automatischer Sentiment-Bewertung als ML-Feature und MiroFish-Input
**Requirements:** SENT-01, SENT-02, SENT-03, SENT-04, SENT-05

**Scope:**
- RSS-Feed Parser: Reuters, Bloomberg, Investing.com, Kitco Gold News
- Gold-relevante Keywords filtern (Fed, Inflation, Zinsen, Krieg, Dollar)
- NLP Sentiment-Scoring (FinBERT / VADER, -1.0 bis +1.0)
- Quellen-Gewichtung + Aktualitaets-Decay
- Aggregation: 1h, 4h, 24h rollierend + Sentiment-Momentum + Divergenz
- ML-Features: sentiment_1h, sentiment_4h, sentiment_24h, momentum, divergenz, news_count
- MiroFish Seed-Template Integration

**UAT:**
- [ ] RSS-Feeds werden alle 5min abgerufen und Gold-relevant gefiltert
- [ ] Sentiment-Score pro Nachricht berechnet (-1.0 bis +1.0)
- [ ] Aggregierte Sentiment-Werte (1h/4h/24h) verfuegbar
- [ ] Sentiment-Features im ML-Modell als Input nutzbar
- [ ] Historische Sentiment-Daten fuer Backtesting gespeichert

---

### Phase 12: Korrelations-Engine
**Goal:** Inter-Market-Korrelationen (DXY, US10Y, Silber, VIX) als zusaetzliche Signalquelle
**Requirements:** CORR-01, CORR-02, CORR-03, CORR-04

**Scope:**
- Asset-Daten abrufen: DXY, US10Y, Silber, VIX, S&P500
- Rolling Correlation berechnen (20/60/120 Perioden)
- Korrelations-Regime erkennen (normal, breakdown, inversion)
- Divergenz-Scanner: Gold vs. DXY, Gold vs. Anleihen
- Lead-Lag Analyse: welches Asset fuehrt Gold?
- ML-Features: correlation_dxy, correlation_us10y, divergence_score, lead_lag_score

**UAT:**
- [ ] Mindestens 4 korrelierte Assets werden regelmaessig abgerufen
- [ ] Rolling Correlation ueber mehrere Zeitfenster berechnet
- [ ] Korrelations-Breakdowns werden erkannt und gemeldet
- [ ] Divergenz-Signale als ML-Features verfuegbar

---

### Phase 12.1 (INSERTED): AI Confidence Calibration & Decision Governance
**Goal:** Kalibrierte AI-Confidence und datenbasierte Decision-Governance einfuehren, damit Buy/Sell/Hold-Gates nachvollziehbar, versioniert und rolloutsicher sind.
**Requirements:** CONF-01, CONF-02, CONF-03, CONF-04, CONF-05
**Depends on:** Phase 12
**Plans:** 0 planned

Plans:
- [x] 12.1-RESEARCH.md - Confidence calibration and decision governance researched
- [ ] TBD (run /gsd:plan-phase 12.1 to break down)

**Scope:**
- Confidence Calibration fuer Modell- und Ensemble-Scores
- Datenbasierte Buy/Sell/Hold-Schwellen statt fixer Confidence-Grenzen
- Regime-spezifische Gate-Logik fuer Signal-Freigabe
- Decision Logging fuer Confidence, Konflikte und Ablehnungsgruende
- Vorbereitung fuer Champion/Challenger- und Auto-Retraining-Entscheidungen

**UAT:**
- [ ] Modell- und Ensemble-Confidence wird gegen reale Trefferquoten kalibriert
- [ ] Thresholds sind versioniert und datenbasiert ableitbar
- [ ] Regime-spezifische Gates koennen schwache Signale konsistent blockieren
- [ ] Live-Entscheidungen loggen Confidence, Threshold und Gate-Reason

---

### Phase 12.3 (INSERTED): AI Indicator Specialist Training
**Goal:** Zusaetzliches Specialist-AI-Modell fuer einen zweiten Indikator-/Feature-Block trainieren und als separate Stimme in das Ensemble laden.
**Requirements:** AITRAIN-01, AITRAIN-02, AITRAIN-03, AITRAIN-04
**Depends on:** Phase 12.1
**Plans:** 0 planned

Plans:
- [x] 12.3-RESEARCH.md - Market-structure/liquidity specialist architecture researched
- [ ] TBD (run /gsd:plan-phase 12.3)

**Scope:**
- Zweites AI-Modell als Specialist laden, getrennt von XGBoost/LightGBM Core-Ensemble
- Kandidat-Indikator: Market-Structure/Liquidity-Sweep/Fair-Value-Gap-Features als Gold-spezifischer Signalblock
- Eigene Trainingspipeline fuer den Specialist mit Walk-Forward-Validation und Feature-Leakage-Schutz
- Specialist-Output als `specialist_score`, `specialist_confidence`, `specialist_reason` ins Ensemble geben
- Governance aus Phase 12.1 nutzen: Specialist darf Signale bestaetigen, abschwaechen oder vetoen, aber nicht ungeprueft alleine traden
- Vergleich gegen Baseline: Core-Ensemble vs. Core+Specialist mit Profit Factor, Drawdown, Calibration und Trade Count

**UAT:**
- [ ] Specialist-Feature-Block wird berechnet und versioniert
- [ ] Specialist-AI-Modell wird separat trainiert und geladen
- [ ] Walk-Forward-Vergleich zeigt messbaren Mehrwert oder blockiert Rollout
- [ ] Ensemble loggt Core-Score, Specialist-Score und finale Governance-Entscheidung

---

### Phase 13: Orderbuch-Analyse
**Goal:** Order Flow / DOM Analyse zur Erkennung institutioneller Aktivitaet und grosser Bewegungen
**Requirements:** FLOW-01, FLOW-02, FLOW-03, FLOW-04

**Scope:**
- Bid/Ask Walls erkennen (grosse Orders im Orderbuch)
- Delta berechnen: Kauf- vs. Verkaufsdruck pro Kerze
- Liquiditaets-Zonen identifizieren (Stop-Loss Cluster)
- Absorption erkennen (grosse Orders aufgesaugt = Reversal-Signal)
- Order Flow Features fuer ML-Modell

**UAT:**
- [ ] Order Flow Daten werden abgerufen und verarbeitet
- [ ] Delta (Kauf/Verkaufsdruck) pro Kerze berechnet
- [ ] Liquiditaets-Zonen und Bid/Ask Walls erkannt
- [ ] Order Flow Features im ML-Modell nutzbar

---

**Total phases:** 16
**Total requirements:** 67 (31 v1 + 36 new)

### Phase 14: Elliott Wave Theorie Integration — automatische Wellenzaehlung (1-5 Impuls, A-B-C Korrektur), Fibonacci-Targets aus Wellen-Verhaeltnissen, Wellen-Position als ML-Feature, Integration in signal_generator.py und MiroFish-Seed-Templates

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 13
**Plans:** 1/3 plans executed

Plans:
- [ ] TBD (run /gsd:plan-phase 14 to break down)

---

### Phase 15: Demo Trading Validation
**Goal:** Bot runs profitably on demo account, proving the system works
**Requirements:** DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Plans:** 3 plans

Plans:
- [ ] 15-01-PLAN.md — Stability hardening (keepalive, heartbeat, reasoning defaults, daily stats)
- [ ] 15-02-PLAN.md — Operational scripts (preflight check, demo report, PowerShell restart wrapper)
- [ ] 15-03-PLAN.md — Demo readiness verification and operator checkpoint

**Scope:**
- Deploy bot on Capital.com demo account
- Run for 2+ weeks continuously
- Monitor and log all trades
- Evaluate profitability

**UAT:**
- [ ] Bot runs 24+ hours without crashes
- [ ] Trades open and close automatically
- [ ] Positive P&L over 2-week period
- [ ] All trades logged with full details

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-04-17 — moved demo validation to Phase 15 (deferred until after new features)*
