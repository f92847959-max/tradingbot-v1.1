# Backtesting & Replay Engine

## Status: Geplant

## Beschreibung
Vollstaendige Backtesting-Engine die alle Strategien und ML-Modelle auf historischen Daten testen kann. Mit Replay-Modus um Trades visuell nachzuspielen.

## Features

### Backtesting-Engine
- **Tick-by-Tick Simulation:** Realistisch, nicht nur Kerzen-Close
- **Spread-Simulation:** Realistische Spreads je nach Session/Volatilitaet
- **Slippage-Simulation:** Realistischer Slippage bei Market Orders
- **Commission-Berechnung:** Swap/Overnight Kosten einbeziehen
- **Multi-Timeframe:** Gleichzeitig M1, M5, M15, H1, H4, D1 simulieren

### Performance-Metriken
- Net Profit / Gross Profit / Gross Loss
- Win Rate, Profit Factor
- Sharpe Ratio, Sortino Ratio, Calmar Ratio
- Max Drawdown (absolut und prozentual)
- Max Consecutive Wins/Losses
- Average Trade Duration
- Best/Worst Trade
- Monthly Returns Heatmap
- Equity Curve + Drawdown Chart

### Replay-Modus
- Trade-fuer-Trade durchspielen mit Chart
- Entry/Exit Punkte visuell markiert
- Indikatoren-Werte zum Zeitpunkt des Trades anzeigen
- Grund fuer Entry/Exit (welches Signal hat ausgeloest)
- Vorwaerts/Rueckwaerts spulen, Geschwindigkeit anpassen

### Walk-Forward Analyse
- Train auf Periode 1, Test auf Periode 2
- Sliding Window ueber gesamten Datensatz
- Out-of-Sample Performance = echte Performance-Erwartung
- Overfitting-Erkennung: In-Sample vs. Out-of-Sample Gap

### Monte Carlo Stress Test
- Trade-Reihenfolge zufaellig mischen (10.000x)
- Worst-Case Drawdown mit 95%/99% Konfidenz
- Ruin-Wahrscheinlichkeit
- Robust genug fuer Live-Trading?

### Vergleichs-Tool
- Strategie A vs. B vs. C nebeneinander
- Gleicher Zeitraum, gleiche Bedingungen
- Welche Strategie ist besser und warum?

## Technische Umsetzung
- Erweiterung: `strategy/backtesting/` (existiert bereits)
  - `tick_simulator.py` - Tick-genaue Simulation
  - `spread_model.py` - Realistische Spread-Simulation
  - `performance_calculator.py` - Alle Metriken
  - `replay_engine.py` - Visueller Replay
  - `walk_forward.py` - Walk-Forward Analyse
  - `monte_carlo.py` - Stress Tests
  - `strategy_comparator.py` - A/B Vergleich
- Frontend: Streamlit Dashboard fuer Charts und Replay

## Prioritaet: Hoch
