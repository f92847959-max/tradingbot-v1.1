# Requirements: GoldBot 2

**Defined:** 2026-03-03
**Core Value:** Der Bot muss im Demo-Modus profitabel traden — deutlich mehr Gewinne als Verluste, nachweisbar über Zeit.

## v1 Requirements

### Code Quality

- [ ] **CODE-01**: main.py is refactored into smaller, focused modules (TradingLoop, SignalGenerator, SystemLifecycle)
- [ ] **CODE-02**: trainer.py is split into manageable sub-modules (<300 lines each)
- [ ] **CODE-03**: All lazy imports moved to top-level or proper factory pattern
- [ ] **CODE-04**: Consistent English code comments (German OK for user-facing strings)
- [ ] **CODE-05**: Proper .gitignore covering .venv, __pycache__, .env, saved_models, logs
- [ ] **CODE-06**: All existing tests pass after refactoring

### Training Pipeline

- [ ] **TRAIN-01**: Walk-forward validation replaces simple chronological split
- [ ] **TRAIN-02**: Features are computed AFTER train/test split to prevent data leakage
- [ ] **TRAIN-03**: SHAP-based feature importance analysis is integrated
- [ ] **TRAIN-04**: Bottom 50% features by importance can be pruned automatically
- [ ] **TRAIN-05**: Model versioning — each training run saves version metadata (date, params, metrics)
- [x] **TRAIN-06**: Training report shows walk-forward results across all windows
- [ ] **TRAIN-07**: Minimum 6 months of historical data used for training

### Strategy

- [x] **STRAT-01**: Dynamic TP/SL based on ATR instead of fixed 50/30 pips
- [ ] **STRAT-02**: ATR-based position sizing adapts to market volatility
- [x] **STRAT-03**: Regime detection classifies market as trending/ranging/volatile
- [ ] **STRAT-04**: Strategy parameters differ per detected regime

### Backtesting

- [x] **BACK-01**: Backtesting framework validates strategy on out-of-sample data
- [x] **BACK-02**: Backtest includes realistic costs (spread, slippage, commissions)
- [x] **BACK-03**: Backtest report shows key metrics (Sharpe ratio, max drawdown, win rate, profit factor)
- [x] **BACK-04**: Walk-forward backtest shows consistent performance across time periods

### MiroFish Swarm Intelligence

- [x] **MIRO-01**: MiroFish (666ghj/MiroFish) kloned, uv-Deps installiert, Flask-Backend laeuft auf localhost:5001 (Windows 11, Python 3.12, kein Docker)
- [x] **MIRO-02**: Zep Cloud verbunden (Free Tier), Knowledge Graph erstellt Gold-Markt-Ontologie aus Seed-Daten
- [x] **MIRO-03**: LLM via OpenAI API (gpt-4o-mini), .env konfiguriert mit LLM_API_KEY + ZEP_API_KEY + LLM_MODEL_NAME
- [x] **MIRO-04**: Gold-Agenten (Trader, Analysten, Zentralbanker) simulieren XAUUSD-Szenarien, Ergebnis als Prediction-Score
- [x] **MIRO-05**: mirofish_client.py integriert Swarm-Score in signal_generator.py neben XGBoost/LightGBM Ensemble
- [x] **MIRO-06**: API-Kosten-Limiter begrenzt Simulationen pro Tag (Token-Budget fuer gpt-4o-mini)

### Demo Trading

- [ ] **DEMO-01**: Bot runs stable on Capital.com demo account for 24+ hours without crashes
- [ ] **DEMO-02**: Bot opens and closes trades automatically based on AI signals
- [ ] **DEMO-03**: Bot shows positive P&L over a 2-week demo period
- [ ] **DEMO-04**: All trades are logged with entry/exit prices, P&L, reasoning

### Wirtschaftskalender

- [x] **ECAL-01**: Wirtschaftskalender-Daten werden automatisch abgerufen und Gold-relevante Events gefiltert
- [x] **ECAL-02**: High-Impact Events (NFP, FOMC, CPI) blockieren neue Trades 30min vorher
- [x] **ECAL-03**: Extrem-Events schliessen bestehende Positionen automatisch
- [ ] **ECAL-04**: Historische Event-Daten gespeichert und fuer Backtesting nutzbar

### Advanced Risk & Position Sizing

- [x] **RISK-01**: Kelly Criterion berechnet optimale Positionsgroesse aus Win-Rate und RRR
- [x] **RISK-02**: Volatilitaets-basiertes Sizing normalisiert Positionen nach ATR
- [x] **RISK-03**: Portfolio Heat Management begrenzt offenes Gesamtrisiko auf max 5%
- [x] **RISK-04**: Monte Carlo Simulation zeigt Drawdown-Verteilung (1000+ Pfade)
- [x] **RISK-05**: Equity Curve Filter stoppt Trading bei Drawdown ueber Threshold

### Smart Exit Engine

- [x] **EXIT-01**: Dynamischer SL berechnet aus ATR + Struktur-Level (nicht fix)
- [x] **EXIT-02**: Dynamischer TP anhand Fibonacci Extensions / naechste S/R-Zone
- [x] **EXIT-03**: Trailing Stop aktiviert nach +1R, trailt per ATR
- [x] **EXIT-04**: Partial Close schliesst 50% bei TP1, Rest laeuft mit Trailing
- [x] **EXIT-05**: Exit-Signale erkennen Reversals (Kerzen, Momentum-Divergenz)

### News-Sentiment-Analyse

- [x] **SENT-01**: RSS-Feeds (Reuters, Bloomberg, Investing.com, Kitco) werden alle 5min abgerufen und Gold-relevant gefiltert
- [x] **SENT-02**: NLP Sentiment-Score pro Nachricht berechnet (-1.0 bis +1.0, FinBERT/VADER)
- [x] **SENT-03**: Aggregierte Sentiment-Werte (1h/4h/24h rollierend) und Sentiment-Momentum verfuegbar
- [x] **SENT-04**: Sentiment-Features (score, momentum, divergenz, news_count) als ML-Input nutzbar
- [x] **SENT-05**: Historische Sentiment-Daten gespeichert und fuer Backtesting abrufbar

### Korrelations-Engine

- [x] **CORR-01**: Asset-Daten (DXY, US10Y, Silber, VIX, S&P500) werden regelmaessig abgerufen
- [ ] **CORR-02**: Rolling Correlation ueber mehrere Zeitfenster (20/60/120 Perioden) berechnet
- [ ] **CORR-03**: Korrelations-Breakdowns und Divergenzen werden erkannt und als Signal gemeldet
- [ ] **CORR-04**: Korrelations-Features als ML-Input nutzbar (correlation, divergence, lead_lag)

### AI Confidence Calibration & Decision Governance

- [ ] **CONF-01**: Modell- und Ensemble-Confidence wird gegen OOS-/Walk-Forward-Trefferquoten kalibriert
- [ ] **CONF-02**: Buy/Sell/Hold-Thresholds sind versioniert, datenbasiert und optional regime-spezifisch
- [ ] **CONF-03**: Signal-Gates loggen Confidence, Threshold, Regime, Konfliktquote und Gate-Reason je Entscheidung
- [ ] **CONF-04**: Champion/Challenger- oder Shadow-Auswertung prueft neue Gates/Modelle vor Rollout
- [ ] **CONF-05**: Auto-Retraining-Trigger basiert auf kalibrierter Performance-Degradation statt roher Confidence

### AI Indicator Specialist Training

- [ ] **AITRAIN-01**: Specialist-Feature-Block fuer zusaetzlichen Indikator wird reproduzierbar berechnet und versioniert
- [ ] **AITRAIN-02**: Separates Specialist-AI-Modell wird trainiert, gespeichert und zur Laufzeit geladen
- [ ] **AITRAIN-03**: Walk-Forward-Vergleich prueft Core-Ensemble gegen Core+Specialist ohne Leakage
- [ ] **AITRAIN-04**: Ensemble-Governance loggt Core-Score, Specialist-Score, Confidence und finale Gate-Entscheidung

### Exit AI Training & Runtime Governance

- [ ] **EXITAI-01**: Trade-Lifecycle-Snapshots und Smart-Exit-Signale werden kausal in Exit-AI-Trainingssamples ueberfuehrt
- [ ] **EXITAI-02**: Ein separates Exit-AI-Modell wird trainiert, versioniert und getrennt vom Core-Ensemble gespeichert
- [ ] **EXITAI-03**: Walk-Forward- und Baseline-Vergleich messen Drawdown-Schutz, Upside-Retention und Early-Exit-Kosten leakage-sicher
- [ ] **EXITAI-04**: Exit-AI-Action-Scores und Confidence werden kalibriert und duerfen nur mit dokumentiertem Promotion-Gate ausgerollt werden
- [ ] **EXITAI-05**: Runtime-Exit-AI darf nur Risiko reduzieren (SL tighten, Partial Close, Early Exit) und niemals Risiko vergroessern oder Trades eroeffnen
- [ ] **EXITAI-06**: Live-Integration nutzt bestehende Modify-/Close-/Partial-Close-Pfade mit no-op Fallback bei fehlenden Artefakten
- [ ] **EXITAI-07**: Exit-AI-Entscheidungen loggen Baseline-Exit-Kontext, gewaehlte Aktion, Confidence und Broker-Ergebnis fuer Audit und Retraining
- [ ] **EXITAI-08**: Monitoring und Reconciliation erkennen Drift zwischen Exit-AI-Empfehlung, Smart-Exit-Baseline und realem Trade-Verlauf

### Existing AI Autonomy Distillation

- [ ] **AUTOAI-01**: Decision-Snapshots erfassen pro Tick die bestehende Teacher-Kette kausal mit Ensemble-, Governance-, Strategie-, Kalender-, Risk- und spaeterem Execution-Kontext
- [ ] **AUTOAI-02**: Distillation-Dataset trennt `preliminary_action`, `policy_action`, `final_action`, `block_stage` und `block_codes`, statt geblockte Entscheidungen pauschal zu `HOLD` zu kollabieren
- [ ] **AUTOAI-03**: Ein gelernter Decision-Head wird auf Decision-State-Features trainiert, versioniert und mit bestehender Calibration-/Threshold-Infrastruktur kompatibel gespeichert
- [ ] **AUTOAI-04**: Walk-Forward- und Promotion-Gates vergleichen Champion gegen Candidate auf Profit Factor, Drawdown, Calibration und Non-HOLD-Qualitaet statt nur auf Accuracy
- [ ] **AUTOAI-05**: Runtime-Rollout erfolgt als `shadow` -> `agreement_guarded` -> `primary_with_challenger`, ohne bestehende Kill-Switch-, Kalender-, Strategie- oder Risk-Guards zu umgehen
- [ ] **AUTOAI-06**: Governance- und Monitoring-Persistenz loggen Champion/Candidate-Auswahl, Disagreements, Guard-Blocks und Promotionsmetriken strukturiert fuer Operator Review und Retraining

### AI Training Pipeline Hardening

- [ ] **AITRAIN2-01**: Trainingslaeufe pruefen vor dem Fitten die tatsaechlich trainierbare historische Zeitspanne und brechen mit einer konkreten Datenabdeckungsdiagnose ab, wenn der Mindestzeitraum nicht erreicht wird
- [ ] **AITRAIN2-02**: Trainingsreports unterscheiden empfangene, gespeicherte, feature-ready und label-ready Samples inklusive Dropped-Row-Gruenden
- [ ] **AITRAIN2-03**: Causale Label-Builder erzeugen Entry-, HOLD/Abstain-, Exit-, Confidence- und Risk-aware Labels ohne Future-Leakage
- [ ] **AITRAIN2-04**: Candidate-Modelle werden walk-forward gegen den aktuellen Champion auf identischen Fenstern und nach Kosten verglichen
- [ ] **AITRAIN2-05**: Promotion in Shadow oder Runtime wird durch Kalibrierung, Drawdown, Profit Factor, Confidence-Bucket-Qualitaet und dokumentierte Manifest-Artefakte gegated

### Orderbuch-Analyse

- [x] **FLOW-01**: Order Flow / Level 2 Daten werden abgerufen und verarbeitet
- [x] **FLOW-02**: Delta (Kauf- vs. Verkaufsdruck) pro Kerze berechnet
- [x] **FLOW-03**: Liquiditaets-Zonen und Bid/Ask Walls automatisch erkannt
- [x] **FLOW-04**: Order Flow Features (delta, absorption, liquidity) als ML-Input nutzbar

## v2 Requirements

### Advanced ML

- **ML-01**: Ensemble model weights auto-tuned based on recent performance
- **ML-02**: Online learning — model updates incrementally with new data
- **ML-03**: Correlation features (DXY, US10Y, S&P500) added to feature set

### Notifications

- **NOTIF-01**: WhatsApp notifications for trade opens/closes
- **NOTIF-02**: Daily performance summary notification
- **NOTIF-03**: Kill switch activation alert

### Monitoring

- **MON-01**: Model degradation detection with automatic retraining trigger
- **MON-02**: API latency monitoring dashboard
- **MON-03**: Automated health checks with alerting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deep learning models (LSTM/Transformer) | Overfit easily on small datasets, XGBoost/LightGBM better for this |
| Sentiment-only trading decisions | Sentiment ist nur Zusatz-Feature, keine eigenstaendige Intraday-Gold-Strategie |
| Multiple trading pairs | Focus on Gold only until profitable |
| Mobile app | Web interface sufficient |
| Live trading with real money | Must prove profitability in demo first |
| Broker switch | Capital.com integration works, no reason to change |
| Pre-trained external models | None exist for gold trading that are production-ready |
| Reinforcement learning | Extremely hard to get right, overkill |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CODE-01 | Phase 1 | Pending |
| CODE-02 | Phase 1 | Pending |
| CODE-03 | Phase 1 | Pending |
| CODE-04 | Phase 1 | Pending |
| CODE-05 | Phase 1 | Pending |
| CODE-06 | Phase 1 | Pending |
| TRAIN-01 | Phase 2 | Pending |
| TRAIN-02 | Phase 2 | Pending |
| TRAIN-05 | Phase 2 | Pending |
| TRAIN-06 | Phase 2 | Complete |
| TRAIN-07 | Phase 2 | Pending |
| TRAIN-03 | Phase 3 | Pending |
| TRAIN-04 | Phase 3 | Pending |
| STRAT-01 | Phase 4 | Complete |
| STRAT-02 | Phase 4 | Pending |
| STRAT-03 | Phase 4 | Complete |
| STRAT-04 | Phase 4 | Pending |
| BACK-01 | Phase 5 | Complete |
| BACK-02 | Phase 5 | Complete |
| BACK-03 | Phase 5 | Complete |
| BACK-04 | Phase 5 | Complete |
| MIRO-01 | Phase 6 | Complete |
| MIRO-02 | Phase 6 | Complete |
| MIRO-03 | Phase 6 | Complete |
| MIRO-04 | Phase 6 | Complete |
| MIRO-05 | Phase 6 | Complete |
| MIRO-06 | Phase 6 | Complete |
| ECAL-01 | Phase 8 | Complete |
| ECAL-02 | Phase 8 | Complete |
| ECAL-03 | Phase 8 | Complete |
| ECAL-04 | Phase 8 | Pending |
| RISK-01 | Phase 9 | Complete |
| RISK-02 | Phase 9 | Complete |
| RISK-03 | Phase 9 | Complete |
| RISK-04 | Phase 9 | Complete |
| RISK-05 | Phase 9 | Complete |
| EXIT-01 | Phase 10 | Complete |
| EXIT-02 | Phase 10 | Complete |
| EXIT-03 | Phase 10 | Complete |
| EXIT-04 | Phase 10 | Complete |
| EXIT-05 | Phase 10 | Complete |
| SENT-01 | Phase 11 | Complete |
| SENT-02 | Phase 11 | Complete |
| SENT-03 | Phase 11 | Complete |
| SENT-04 | Phase 11 | Complete |
| SENT-05 | Phase 11 | Complete |
| CORR-01 | Phase 12 | Complete |
| CORR-02 | Phase 12 | Pending |
| CORR-03 | Phase 12 | Pending |
| CORR-04 | Phase 12 | Pending |
| CONF-01 | Phase 12.1 | Pending |
| CONF-02 | Phase 12.1 | Pending |
| CONF-03 | Phase 12.1 | Pending |
| CONF-04 | Phase 12.1 | Pending |
| CONF-05 | Phase 12.1 | Pending |
| AITRAIN-01 | Phase 12.3 | Pending |
| AITRAIN-02 | Phase 12.3 | Pending |
| AITRAIN-03 | Phase 12.3 | Pending |
| AITRAIN-04 | Phase 12.3 | Pending |
| EXITAI-01 | Phase 12.4 | Pending |
| EXITAI-02 | Phase 12.4 | Pending |
| EXITAI-03 | Phase 12.4 | Pending |
| EXITAI-04 | Phase 12.4 | Pending |
| EXITAI-05 | Phase 12.5 | Pending |
| EXITAI-06 | Phase 12.5 | Pending |
| EXITAI-07 | Phase 12.5 | Pending |
| EXITAI-08 | Phase 12.5 | Pending |
| AUTOAI-01 | Phase 12.6 | Pending |
| AUTOAI-02 | Phase 12.6 | Pending |
| AUTOAI-03 | Phase 12.6 | Pending |
| AUTOAI-04 | Phase 12.6 | Pending |
| AUTOAI-05 | Phase 12.6 | Pending |
| AUTOAI-06 | Phase 12.6 | Pending |
| AITRAIN2-01 | Phase 12.7 | Pending |
| AITRAIN2-02 | Phase 12.7 | Pending |
| AITRAIN2-03 | Phase 12.7 | Pending |
| AITRAIN2-04 | Phase 12.7 | Pending |
| AITRAIN2-05 | Phase 12.7 | Pending |
| FLOW-01 | Phase 13 | Complete |
| FLOW-02 | Phase 13 | Complete |
| FLOW-03 | Phase 13 | Complete |
| FLOW-04 | Phase 13 | Complete |
| DEMO-01 | Phase 15 | Pending |
| DEMO-02 | Phase 15 | Pending |
| DEMO-03 | Phase 15 | Pending |
| DEMO-04 | Phase 15 | Pending |


**Coverage:**
- Active requirements tracked above: 81 total
- Mapped to phases: 81
- Unmapped: 0

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-04-25 after planning Phase 12.6 existing AI autonomy distillation*
