# Advanced Pattern Recognition

## Status: Geplant

## Beschreibung
Erweiterte Chartmuster-Erkennung mit klassischen Patterns, Candlestick-Formationen und Smart Money Concepts (SMC). Erkennt was erfahrene Trader im Chart sehen.

## Features

### Klassische Chart-Patterns
- **Umkehr-Patterns:**
  - Head & Shoulders / Inverse Head & Shoulders
  - Double Top / Double Bottom
  - Triple Top / Triple Bottom
  - Rounding Bottom / Top
  - V-Bottom / V-Top
- **Fortsetzungs-Patterns:**
  - Bull/Bear Flag
  - Ascending/Descending Triangle
  - Symmetrical Triangle
  - Wedge (Rising/Falling)
  - Rectangle/Channel

### Candlestick-Patterns (japanisch)
- **Einzel-Kerzen:** Doji, Hammer, Shooting Star, Marubozu, Spinning Top
- **Zwei-Kerzen:** Engulfing, Harami, Piercing Line, Dark Cloud Cover, Tweezer
- **Drei-Kerzen:** Morning Star, Evening Star, Three White Soldiers, Three Black Crows
- Alle mit Kontext-Bewertung (Pattern am S/R Level = staerker)

### Smart Money Concepts (SMC)
- **Break of Structure (BoS):** Hoehere Highs/Lows gebrochen = Trend bestaetigt
- **Change of Character (ChoCh):** Erste Trendwechsel-Anzeichen
- **Order Blocks:** Letzte Kerze vor einer starken Bewegung = institutioneller Entry
- **Fair Value Gaps (FVG):** Preis-Luecken die als Magneten wirken
- **Equal Highs/Lows:** Liquiditaets-Pools die abgeholt werden
- **Premium/Discount Zones:** Kaufen im Discount (unter 50% Range), verkaufen im Premium

### Harmonic Patterns
- Gartley, Butterfly, Bat, Crab, Shark
- Automatische Erkennung der XABCD-Punkte
- Fibonacci-Verhaeltnisse validieren

### ML-Features
- `pattern_type` (welches Pattern erkannt)
- `pattern_completion` (0-100%, wie weit ist das Pattern)
- `pattern_at_sr` (Boolean: Pattern an S/R Level?)
- `smc_order_block_distance` (Abstand zum naechsten Order Block)
- `smc_fvg_distance` (Abstand zum naechsten Fair Value Gap)
- `smc_structure` (bullish/bearish Structure)
- `candlestick_signal` (-1 bis +1)
- `harmonic_pattern_score` (0-100)

## Technische Umsetzung
- Erweiterung: `strategy/pattern_recognition.py` (existiert bereits)
  - `classic_patterns.py` - Chart-Patterns
  - `candlestick_patterns.py` - Japanische Kerzen
  - `smc_analyzer.py` - Smart Money Concepts
  - `harmonic_patterns.py` - Harmonische Patterns
  - `pattern_scorer.py` - Alle Patterns bewerten + gewichten

## Prioritaet: Hoch
