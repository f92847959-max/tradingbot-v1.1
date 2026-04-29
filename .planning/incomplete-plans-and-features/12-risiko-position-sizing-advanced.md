# Advanced Risk & Position Sizing

## Status: Geplant

## Beschreibung
Intelligenteres Risikomanagement und dynamische Positionsgroessen-Berechnung basierend auf Marktbedingungen, Confidence und aktueller Performance.

## Features

### Dynamische Positionsgroesse
- **Kelly Criterion:** Optimale Positionsgroesse basierend auf Win-Rate und Risk-Reward
  - Half-Kelly fuer konservativere Trades
  - Quarter-Kelly bei unsicheren Signalen
- **Volatilitaets-basiert:** Hohe Vola = kleinere Position, niedrige Vola = groessere
- **Confidence-basiert:** ML-Confidence 90% = groessere Position als 70%
- **Streak-basiert:**
  - 3 Gewinne in Folge = leicht groessere Position (Hot Hand)
  - 3 Verluste in Folge = kleinere Position (Cooldown)
- **Equity-Curve basiert:**
  - Equity ueber EMA = volle Groesse
  - Equity unter EMA = halbe Groesse (System laeuft schlecht)

### Portfolio Heat Management
- **Gesamt-Exposure:** Max. X% des Kapitals gleichzeitig riskiert
- **Korrelations-Risiko:** Wenn mehrere korrelierte Trades offen = Risiko reduzieren
- **Tages-Budget:** Max. Verlust pro Tag, danach Stop
- **Wochen-Budget:** Max. Verlust pro Woche
- **Recovery Mode:** Nach grossem Drawdown automatisch kleinere Positionen

### Monte Carlo Simulation
- 10.000 Simulationen der naechsten 100 Trades
- Erwarteter Drawdown mit 95% Konfidenz
- Ruin-Wahrscheinlichkeit berechnen
- Optimale Positionsgroesse fuer gegebene Ruin-Toleranz

### ML-Features
- `optimal_position_pct` (Kelly-berechnete Groesse)
- `current_drawdown_pct` (Aktueller Drawdown vom Peak)
- `equity_vs_ema` (Equity-Kurve Gesundheit)
- `win_streak` / `loss_streak` (Aktuelle Serie)
- `portfolio_heat` (Gesamt-Exposure in %)

## Technische Umsetzung
- Erweiterung: `risk/position_sizer.py` (existiert bereits)
  - `kelly_calculator.py` - Kelly Criterion
  - `volatility_sizer.py` - Vola-basierte Groesse
  - `portfolio_heat.py` - Gesamt-Exposure Management
  - `monte_carlo.py` - Simulation
  - `equity_curve_filter.py` - Equity-basierte Anpassung

## Prioritaet: Hoch
