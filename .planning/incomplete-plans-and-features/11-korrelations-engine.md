# Korrelations-Engine (Inter-Market Analyse)

## Status: Geplant

## Beschreibung
Gold bewegt sich nicht isoliert. Es korreliert stark mit Dollar, Anleihen, Aktien und anderen Rohstoffen. Diese Korrelationen nutzen um bessere Signale zu generieren.

## Features

### Kern-Korrelationen fuer Gold
| Asset | Korrelation | Logik |
|---|---|---|
| DXY (Dollar Index) | Negativ | Dollar stark = Gold faellt |
| US10Y (10J Anleihen) | Negativ | Hohe Renditen = Gold weniger attraktiv |
| S&P500 | Variabel | Krise = negativ korreliert, normal = schwach |
| Silber (XAG/USD) | Stark positiv | Bewegt sich oft vor Gold |
| EUR/USD | Positiv | Euro stark = Dollar schwach = Gold hoch |
| USD/JPY | Negativ | Yen = Safe Haven wie Gold |
| Oel (WTI/Brent) | Positiv | Inflation -> Gold hoch |
| Bitcoin | Variabel | "Digitales Gold" Narrativ |
| VIX | Positiv | Angst = Gold steigt |
| Kupfer | Positiv | Wirtschaftsaktivitaet |

### Korrelations-Analyse
- **Rolling Correlation:** 20/50/100 Perioden rollierend
- **Korrelations-Regime:** Phasen erkennen wo Korrelation wechselt
  - z.B. Gold-DXY normalerweise -0.8, aber in Krise manchmal +0.3
- **Lead/Lag Analyse:** Welches Asset bewegt sich zuerst?
  - Silber fuehrt oft Gold um 1-2 Kerzen
  - DXY-Bewegung fuehrt oft Gold-Bewegung
- **Korrelations-Breakdowns:** Wenn normale Korrelation bricht = wichtiges Signal

### Divergenz-Signale
- Dollar faellt aber Gold faellt auch = Schwaeche, irgendwas stimmt nicht
- Silber steigt stark, Gold noch nicht = Gold wird nachziehen (Lead-Signal)
- VIX steigt, Gold steigt nicht = Safe-Haven Demand fehlt
- Anleihen steigen (Renditen fallen), Gold steigt nicht = verdaechtig

### ML-Features
- `dxy_correlation_20` (Rolling Korrelation mit Dollar)
- `dxy_change_1h` (Dollar Aenderung letzte Stunde)
- `us10y_change_1h` (Anleihen-Rendite Aenderung)
- `silver_lead_signal` (Silber-Bewegung als Fruehindikator)
- `sp500_change_1h` (Aktienmarkt-Richtung)
- `vix_level` + `vix_change`
- `correlation_regime` (Normal / Breakdown / Crisis)
- `cross_market_divergence` (Anzahl Divergenzen)
- `oil_change_1h` (Inflation-Proxy)

## Technische Umsetzung
- Neues Modul: `correlation/`
  - `asset_fetcher.py` - Preis-Daten fuer alle korrelierten Assets
  - `correlation_calculator.py` - Rolling Correlations
  - `regime_detector.py` - Korrelations-Regime erkennen
  - `divergence_scanner.py` - Cross-Market Divergenzen
  - `lead_lag_analyzer.py` - Welches Asset fuehrt?
  - `correlation_features.py` - Features fuer ML
- Datenquellen: Yahoo Finance, Capital.com, Alpha Vantage

## Prioritaet: Hoch
