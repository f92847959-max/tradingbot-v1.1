# Copy Trading / Smart Money Tracking

## Status: Geplant

## Beschreibung
Kompetente Trader und institutionelle Akteure identifizieren und ihre Strategien nachahmen. Lernen von den Besten statt nur eigene Signale zu nutzen.

## Features

### 1. Top-Trader Tracking (Social Trading)
- **Quellen:**
  - eToro Top Traders (CopyTrader Daten, oeffentliche Profile)
  - ZuluTrade Signal Provider Rankings
  - MQL5 Signal Service (MetaTrader)
  - TradingView Top-Autoren (Gold-spezifisch)
- **Filter fuer gute Trader:**
  - Min. 12 Monate Track Record
  - Max Drawdown < 20%
  - Sharpe Ratio > 1.5
  - Min. 100 Trades
  - Konsistente Performance (nicht nur 1 Lucky Trade)
- **Aggregiertes Signal:**
  - Wenn 7/10 Top-Trader Long sind = starkes Bullish-Signal
  - Gewichtung nach Performance des Traders

### 2. Institutionelle Positionierung
- **COT-Report (CFTC):**
  - Managed Money (Hedgefonds) Position: Long vs. Short
  - Commercial Hedgers Position: Smart Money
  - Extreme Positionierung = Reversal-Signal
- **Gold ETF Holdings:**
  - GLD (SPDR Gold Trust) - Taegliche Holdings-Aenderung
  - IAU (iShares Gold Trust)
  - Anstieg = institutionelles Kaufinteresse
  - Abfluss = Institutionen verkaufen
- **Central Bank Kaeufe/Verkaeufe:**
  - World Gold Council Daten
  - China, Russland, Indien = groesste Kaeufer
  - Zentralbank kauft = langfristig bullish

### 3. Whale-Tracking
- **Grosse Trades erkennen:**
  - Ungewoehnlich grosse Orders auf Futures-Maerkten
  - Block Trades (ausserboerslich, dann gemeldet)
  - Dark Pool Aktivitaet (wenn Daten verfuegbar)
- **Signal:** Whale kauft = dem Whale folgen (mit Verzoegerung)

### 4. Consensus-Signal
- Alle Quellen zusammenfuehren zu einem Score:
  - Top-Trader Consensus: -1 bis +1
  - Institutional Positioning: -1 bis +1
  - ETF Flow Direction: -1 bis +1
  - Central Bank Trend: -1 bis +1
  - Whale Activity: -1 bis +1
- Gewichteter Durchschnitt = **Smart Money Score**

### ML-Features
- `top_trader_consensus` (-1 bis +1)
- `cot_managed_money_net` (Netto-Position Hedgefonds)
- `cot_commercial_net` (Netto-Position Smart Money)
- `etf_flow_7d` (7-Tage ETF Zufluss/Abfluss)
- `central_bank_buying` (Monatlicher Kauf-Trend)
- `whale_activity_score` (-1 bis +1)
- `smart_money_score` (Aggregiert, -1 bis +1)

## Technische Umsetzung
- Neues Modul: `smart_money/`
  - `top_trader_tracker.py` - Social Trading Plattformen scrapen
  - `cot_analyzer.py` - CFTC COT-Report parsen
  - `etf_flow_tracker.py` - Gold ETF Holdings tracken
  - `central_bank_tracker.py` - Zentralbank-Kaeufe
  - `whale_detector.py` - Grosse Trades erkennen
  - `consensus_calculator.py` - Smart Money Score berechnen
- Datenquellen: CFTC API, World Gold Council, eToro API, Yahoo Finance

## Prioritaet: Hoch
