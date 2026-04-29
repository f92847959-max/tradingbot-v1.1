# Smart Exit Engine (Dynamische TP/SL)

## Status: Geplant

## Beschreibung
Intelligentes Exit-Management statt fester Take-Profit/Stop-Loss Werte. Passt TP und SL dynamisch an Marktbedingungen, Volatilitaet und Preis-Levels an.

## Features

### Dynamischer Stop-Loss
- **ATR-basiert:** SL = Aktueller Preis - (ATR * Multiplikator)
  - Hohe Volatilitaet = weiterer SL, niedrige = enger SL
- **Struktur-basiert:** SL unter/ueber letztem Swing Low/High
- **Chandelier Exit:** Trailing Stop basiert auf ATR
- **Parabolic SAR:** Nachziehender Stop der sich beschleunigt

### Dynamischer Take-Profit
- **Risk-Reward basiert:** Minimum 1:2, Ziel 1:3
- **Fibonacci-basiert:** TP an naechstem Fibonacci-Extension Level
- **S/R-basiert:** TP vor naechster Resistance (Long) oder Support (Short)
- **Partial TP:**
  - 50% Position bei 1:1 Risk-Reward schliessen
  - 30% bei 1:2 schliessen
  - 20% laufen lassen mit Trailing Stop

### Trailing Stop Strategien
- **Fixed Trailing:** Nachziehen um festen Betrag (z.B. 5 Pips)
- **ATR Trailing:** Nachziehen um ATR-Vielfaches
- **Breakeven + Trail:** Erst auf Breakeven ziehen, dann trailen
- **Stufenweise:** Bei bestimmten Gewinn-Levels SL anpassen

### Exit-Signale
- **Reversal-Erkennung:** Entgegengesetztes Signal = Position schliessen
- **Momentum-Verlust:** RSI/MACD Divergenz = Gewinne mitnehmen
- **Volumen-Erschoepfung:** Volumen faellt bei weiterem Preisanstieg
- **Zeitbasiert:** Max. Haltedauer (z.B. 24h fuer Intraday)

### ML-Features (fuer optimalen Exit-Zeitpunkt)
- `unrealized_pnl_pips` (Aktueller Gewinn/Verlust)
- `time_in_trade_minutes` (Wie lange laeuft der Trade)
- `momentum_remaining` (RSI-Trend, MACD-Histogram)
- `distance_to_next_sr` (Naehe zum naechsten S/R Level)
- `volatility_current_vs_entry` (Hat sich Vola geaendert)

## Technische Umsetzung
- Neues Modul: `exit_engine/`
  - `dynamic_sl.py` - ATR/Struktur-basierter Stop-Loss
  - `dynamic_tp.py` - Fibonacci/S/R-basierter Take-Profit
  - `trailing_manager.py` - Verschiedene Trailing-Strategien
  - `partial_close.py` - Teilweise Position schliessen
  - `exit_signal_detector.py` - Reversal/Momentum Exit-Signale
- Integration in `trading/monitors.py` fuer Echtzeit-Position-Management

## Prioritaet: Hoch
