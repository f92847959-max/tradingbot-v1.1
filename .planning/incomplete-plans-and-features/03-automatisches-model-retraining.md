# Automatisches Model-Retraining

## Status: Geplant

## Beschreibung
Automatisiertes System das ML-Modelle regelmaessig mit neuen Marktdaten neu trainiert, validiert und nur deployed wenn das neue Modell besser performt als das aktuelle.

## Features

### Scheduler
- Retraining-Zyklus: Wochentlich (Sonntag Nacht) oder Monatlich
- Trigger auch bei Performance-Degradation (z.B. Win-Rate < 50% ueber 50 Trades)
- APScheduler-basiert (bereits im Projekt)

### Walk-Forward Validation
- Trainieren nur auf vergangenen Daten (kein Data Leakage)
- Sliding Window: z.B. 12 Monate Training, 1 Monat Validation
- Mehrere Folds fuer robuste Bewertung
- Out-of-Sample Performance als Entscheidungskriterium

### Model-Vergleich (Champion/Challenger)
- Aktuelles Modell = "Champion"
- Neu trainiertes Modell = "Challenger"
- Vergleichsmetriken:
  - Sharpe Ratio
  - Win-Rate
  - Max Drawdown
  - Profit Factor
  - Calmar Ratio
- Challenger wird nur deployed wenn mindestens 2 von 5 Metriken besser sind UND kein Metrik deutlich schlechter

### Model-Versionierung
- Jedes Modell mit Timestamp + Metriken speichern
- Ordner: `ai_engine/saved_models/archive/`
- Metadata-Datei pro Modell: Trainings-Zeitraum, Features, Hyperparameter, Metriken
- Rollback moeglich auf vorheriges Modell

### Monitoring & Alerting
- Dashboard-Widget: aktuelle Model-Performance vs. historisch
- WhatsApp/Telegram Alert wenn:
  - Retraining gestartet
  - Neues Modell deployed (mit Metriken-Vergleich)
  - Retraining fehlgeschlagen
  - Performance unter kritischem Schwellwert

### Hyperparameter-Optimierung
- Optuna-basierte Optimierung bei jedem Retraining
- Suchraum: Learning Rate, Max Depth, Estimators, Regularization
- Zeitlimit: max 2 Stunden pro Retraining

## Technische Umsetzung
- Neues Modul: `retraining/`
  - `scheduler.py` - Cron-basierter Retraining-Trigger
  - `trainer_pipeline.py` - Daten laden, Features bauen, trainieren
  - `validator.py` - Walk-Forward Validation
  - `model_comparator.py` - Champion vs. Challenger Vergleich
  - `model_registry.py` - Versionierung und Deployment
  - `performance_monitor.py` - Live-Performance tracken
- Dependencies: optuna, mlflow (optional)

## Prioritaet: Hoch
