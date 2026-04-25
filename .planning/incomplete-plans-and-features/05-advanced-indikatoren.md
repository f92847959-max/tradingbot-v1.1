# Advanced Indikatoren-Engine

## Status: Geplant

## Beschreibung
Erweiterte technische Indikatoren ueber Standard-RSI/MACD hinaus. Professionelle Indikatoren die institutionelle Trader nutzen.

## Features

### Volumen-basierte Indikatoren
- **VWAP** (Volume Weighted Average Price) - Wo liegt der faire Preis heute?
- **VPVR** (Volume Profile Visible Range) - Bei welchem Preis wurde am meisten gehandelt?
- **OBV** (On Balance Volume) - Akkumulieren oder distribuieren die Grossen?
- **MFI** (Money Flow Index) - RSI + Volumen kombiniert
- **Accumulation/Distribution Line** - Geldfluss rein/raus

### Momentum-Indikatoren
- **Stochastic RSI** - RSI vom RSI, sensibler bei Extremen
- **Williams %R** - Ueberkauft/Ueberverkauft mit schnellerer Reaktion
- **CCI** (Commodity Channel Index) - Speziell fuer Rohstoffe wie Gold
- **ROC** (Rate of Change) - Momentum-Geschwindigkeit
- **ADX + DI+/DI-** - Trendstaerke messen (nicht Richtung)

### Volatilitaets-Indikatoren
- **ATR** (Average True Range) - Fuer dynamische SL/TP Berechnung
- **Keltner Channels** - Wie Bollinger, aber stabiler
- **Donchian Channels** - Breakout-Erkennung
- **Historical vs. Implied Volatility Spread** - Ueber/Unterbewertete Optionen

### Trend-Indikatoren
- **Ichimoku Cloud** - Komplettsystem (Trend, Support, Resistance, Momentum)
- **SuperTrend** - Klares Buy/Sell Signal
- **Hull Moving Average** - Schnellster gleitender Durchschnitt, wenig Lag
- **DEMA/TEMA** - Doppelt/Dreifach exponentiell, fruehe Signale

### Multi-Timeframe Confluence
- Alle Indikatoren auf M5, M15, H1, H4, D1 berechnen
- Confluence-Score: Wie viele Timeframes zeigen gleiche Richtung?
- Divergenz-Scanner: RSI/MACD Divergenz auf allen Timeframes

## Technische Umsetzung
- Erweiterung: `ai_engine/features/advanced_indicators.py`
- Erweiterung: `ai_engine/features/volume_profile.py`
- Erweiterung: `ai_engine/features/multi_tf_confluence.py`
- Alle als ML-Features + eigenstaendige Signale nutzbar

## Prioritaet: Hoch
