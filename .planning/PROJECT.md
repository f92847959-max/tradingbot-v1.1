# GoldBot 2

## What This Is

Ein KI-gesteuertes Intraday Trading System für Gold (XAU/USD) auf der Capital.com Plattform. Basiert auf dem bestehenden goldbot v2.0 Codebase — wird durch Refactoring, verbessertes AI-Training und Fertigstellung der Control App zu einem profitablen Demo-Trading-System weiterentwickelt.

## Core Value

Der Bot muss im Demo-Modus profitabel traden — deutlich mehr Gewinne als Verluste, nachweisbar über Zeit.

## Requirements

### Validated

- [x] Codebase ist aufgeräumt, verständlich und wartbar — Validated in Phase 1: Code Cleanup
- [x] Training-Pipeline funktioniert nachweisbar (messbare Verbesserung durch Training) — Validated in Phase 2-3: Walk-Forward + SHAP
- [x] Backtesting mit realistischen Kosten (Spread, Slippage, Kommission) — Validated in Phase 5: Backtesting & Validation
- [x] Strategy passt sich an Marktbedingungen an (Regime Detection, dynamische TP/SL) — Validated in Phase 4: Dynamic TP/SL & Regime Detection

### Active

- [ ] AI-Modelle (XGBoost + LightGBM) liefern profitable Signale im Demo-Modus
- [ ] Training-Pipeline funktioniert nachweisbar (messbare Verbesserung durch Training)
- [ ] Recherche zu Open-Source Modellen für Gold/Forex Trading durchgeführt und Ergebnisse eingebaut
- [ ] Codebase ist aufgeräumt, verständlich und wartbar
- [ ] Control App (React Frontend + FastAPI Backend) ist fertig und funktional
- [ ] Bot-Steuerung (Start/Stop/Status) über Web-Interface möglich
- [ ] Live-Dashboard mit Performance-Metriken und Trade-Historie
- [ ] Risk Management funktioniert zuverlässig (Kill-Switch, Position Sizing, etc.)
- [ ] Capital.com Broker-Integration stabil (REST + WebSocket)
- [ ] Bot entscheidet selbstständig über optimale Trading-Zeiten

### Phase 6: Advanced Intelligence (Neu)
- [ ] **MiroFish Integration**: Schwarmintelligenz-Modul als zusätzliche Stimme im Ensemble.
- [ ] **News-Sentiment**: Einbindung von News-APIs (z.B. Bloomberg/Reuters via NLP) für fundamentale Richtung.
- [ ] **Wirtschaftskalender**: Automatisches Blockieren von Trades vor High-Impact Events (NFP, CPI).
- [ ] **Human Factors**: "Fear & Greed" Index Integration (Angst = Gold kaufen, Gier = Vorsicht).
- [ ] **Auto-Retraining**: Pipeline, die Modelle automatisch neu trainiert, wenn die Performance sinkt.

### Out of Scope

- Broker-Wechsel — Capital.com bleibt
- Komplett neuer Tech-Stack — XGBoost + LightGBM, Python, FastAPI bleiben
- Neuschreiben von Grund auf — Refactoring des bestehenden Codes
- Mobile App — Web-Interface reicht
- Live-Trading mit echtem Geld — erst Demo profitabel, dann weiter

## Context

- Bestehende Codebase (goldbot v2.0) wurde 1:1 nach goldbot2 kopiert
- Etwa 247 Dateien, gut strukturiert in Module (ai_engine, strategy, risk, order_management, etc.)
- 28 Test-Dateien vorhanden
- AI-Modelle wurden trainiert, aber nie im echten Demo-Trading validiert
- Es ist unklar ob das Training korrekt funktioniert oder ob die Modelle effektiv lernen
- Control App (React + TypeScript Frontend) ist nur als Gerüst vorhanden, nicht fertig
- Code enthält gemischte Deutsch/Englisch Kommentare
- Einige Module sind sehr groß (main.py ~800 Zeilen, trainer.py ~1000 Zeilen)
- Ohne trainierte Modelle gibt der Bot nur HOLD-Signale

## Constraints

- **Broker**: Capital.com muss als Broker-Integration erhalten bleiben
- **ML Framework**: XGBoost + LightGBM Ensemble bleibt (55%/45% Gewichtung anpassbar)
- **Sprache**: Python 3.11+ als Hauptsprache
- **Datenbank**: PostgreSQL (Produktion) + SQLite (Fallback) bleibt
- **Ansatz**: Refactoring — bestehenden Code verbessern, nicht neu schreiben

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Refactoring statt Neuschreiben | Code-Basis ist solide, braucht Verbesserung nicht Ersatz | — Pending |
| Open-Source Modelle recherchieren | Möglicherweise gibt es bessere vortrainierte Modelle als eigenes Training | — Pending |
| Control App fertigstellen | User will Bot über Web-Interface steuern und überwachen | — Pending |
| Capital.com als Broker beibehalten | Bestehende Integration funktioniert, kein Grund zu wechseln | — Pending |

---
*Last updated: 2026-03-25 after Phase 5 completion*
