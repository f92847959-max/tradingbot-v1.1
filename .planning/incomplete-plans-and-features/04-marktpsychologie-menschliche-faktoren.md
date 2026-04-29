# Marktpsychologie / Menschliche Faktoren

## Status: Geplant

## Beschreibung
Integration menschlicher psychologischer Faktoren (Angst, Gier, Panik, Euphorie, Herdenverhalten) als messbare Indikatoren in das Trading-System. Der Markt wird von Menschen bewegt - das Modell soll diese Emotionen erkennen und ausnutzen.

## Features

### 1. Fear & Greed Index (Gold-spezifisch)
Eigener zusammengesetzter Index von 0 (Extreme Angst) bis 100 (Extreme Gier):

| Komponente | Gewicht | Misst |
|---|---|---|
| VIX (Volatilitaetsindex) | 15% | Angst-Level am Gesamtmarkt |
| Put/Call Ratio Gold-Optionen | 15% | Hedging-Verhalten, Absicherungsbedarf |
| Gold/S&P500 Ratio | 15% | Safe-Haven-Nachfrage |
| DXY (Dollar Index) | 10% | Flucht in/aus USD |
| US10Y Anleihen-Rendite | 10% | Opportunitaetskosten fuer Gold |
| Volumen vs. 20-Tage-Durchschnitt | 10% | Panik oder Euphorie |
| Preis vs. 200-Tage-MA | 10% | Ueberkauft/Ueberverkauft |
| Gold ETF Flows (GLD, IAU) | 10% | Institutionelles Geld rein/raus |
| Implied Volatility Gold | 5% | Erwartete Schwankung |

### 2. Herdenverhalten-Detektor
- **Erkennung:** Ploetzlicher Volumen-Spike (>3x Durchschnitt) + einseitige Preisbewegung
- **Signal:** Herde kauft/verkauft → kurzfristig mitgehen, dann Reversal erwarten
- **Messung:** Volumen-Preis-Korrelation, Tick-Imbalance

### 3. FOMO-Detektor (Fear of Missing Out)
- **Erkennung:** Zu schneller Preisanstieg ohne fundamentalen Grund
  - Preis > 2 Standardabweichungen ueber kurzfristigem MA
  - Volumen steigt exponentiell
  - Sentiment extrem positiv
- **Signal:** FOMO-Phase = Korrektur wahrscheinlich → NICHT kaufen, Short erwaegen
- **Metrik:** FOMO-Score 0-100

### 4. Panik-Detektor
- **Erkennung:** Kombination aus:
  - VIX-Spike (>20% Anstieg in 24h)
  - Gold-Spike (>1.5% in 1h)
  - Volumen-Explosion (>5x Durchschnitt)
  - Negative Nachrichten-Flut
- **Signal:** Safe-Haven-Kauf → Gold steigt, ABER oft Ueberreaktion → schneller TP
- **Metrik:** Panik-Score 0-100

### 5. Gier-Filter
- **Erkennung:** Alle Indikatoren schreien "BUY":
  - RSI > 70
  - Preis am oberen Bollinger Band
  - Sentiment extrem bullish
  - Fear & Greed > 80
- **Signal:** Wenn ALLES bullish ist → Vorsicht, Reversal kommt oft
- **Aktion:** Positionsgroesse reduzieren, engerer Stop-Loss

### 6. Retail vs. Smart Money (COT-Report)
- **Datenquelle:** CFTC Commitments of Traders Report (woechentlich, Freitag)
- **Analyse:**
  - Commercials (Hedger/Smart Money): Grosse Positionen = wissen was kommt
  - Non-Commercials (Spekulanten): Oft zu spaet dran
  - Small Traders (Retail): Fast immer falsch bei Extremen
- **Signal:**
  - Smart Money kauft + Retail verkauft = BULLISH
  - Smart Money verkauft + Retail kauft = BEARISH
  - Extreme Positionierung = Reversal wahrscheinlich

### 7. Contrarian-Signal
- **Logik:** Wenn die Masse extrem einseitig positioniert ist → gegen die Masse handeln
- **Trigger:**
  - Fear & Greed < 15 (Extreme Angst) → KAUFEN
  - Fear & Greed > 85 (Extreme Gier) → VERKAUFEN
  - COT Retail extrem Long → SHORT erwaegen
  - COT Retail extrem Short → LONG erwaegen
- **Bestaetigung:** Nur mit technischem Reversal-Signal (Divergenz, Candlestick Pattern)

### 8. Emotionale Marktphasen erkennen
Automatische Klassifizierung der aktuellen Marktphase:

| Phase | Merkmale | Trading-Strategie |
|---|---|---|
| **Angst** | VIX hoch, Gold steigt, Volumen hoch | Mit dem Trend, weiter SL |
| **Panik** | VIX Spike, alles faellt, Gold Spike | Schneller TP, kein Nachkauf |
| **Erholung** | VIX faellt, Maerkte stabilisieren | Vorsichtig Long |
| **Optimismus** | Steigende Kurse, moderates Volumen | Normal traden |
| **Euphorie** | Alles steigt, FOMO, extremes Volumen | Gewinne mitnehmen, kein neuer Long |
| **Selbstzufriedenheit** | Niedrige Volatilitaet, wenig Volumen | Achtung: Ruhe vor dem Sturm |
| **Gier** | Extremes Bullish-Sentiment, Retail all-in | Contrarian Short vorbereiten |

## ML-Integration
Alle Faktoren als numerische Features fuer XGBoost/LightGBM:
- `fear_greed_index` (0-100)
- `fomo_score` (0-100)
- `panic_score` (0-100)
- `herd_behavior_score` (-1 bis +1)
- `cot_smart_money_position` (-1 bis +1)
- `cot_retail_position` (-1 bis +1)
- `market_phase` (0-6, encoded)
- `contrarian_signal` (-1, 0, +1)
- `volume_emotion_ratio` (Volumen vs. Durchschnitt)
- `vix_level` und `vix_change_24h`
- `gold_sp500_ratio` und `gold_sp500_ratio_change`

## Technische Umsetzung
- Neues Modul: `psychology/`
  - `fear_greed_index.py` - Zusammengesetzter Index
  - `herd_detector.py` - Herdenverhalten erkennen
  - `fomo_detector.py` - FOMO-Phasen erkennen
  - `panic_detector.py` - Panik-Phasen erkennen
  - `greed_filter.py` - Gier-Filter
  - `cot_analyzer.py` - COT-Report Analyse
  - `contrarian_signal.py` - Gegen-die-Masse Signale
  - `market_phase_classifier.py` - Emotionale Phase klassifizieren
  - `psychology_aggregator.py` - Alle Scores zusammenfuehren
- Datenquellen: Yahoo Finance API (VIX, DXY), CFTC API (COT), CBOE (Put/Call)

## Prioritaet: Hoch
