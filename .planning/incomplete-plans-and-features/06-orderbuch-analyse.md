# Orderbuch-Analyse (Order Flow / DOM)

## Status: Geplant

## Beschreibung
Analyse des Orderbuchs (Depth of Market) um zu sehen wo grosse Kauf-/Verkaufsorders liegen. Zeigt was die grossen Spieler vorhaben BEVOR der Preis sich bewegt.

## Features

### Level 2 Daten (Orderbuch-Tiefe)
- **Bid/Ask Walls erkennen:** Grosse Orders die als Support/Resistance wirken
  - z.B. 500 Lots bei 2950$ = starker Support
- **Orderbuch-Imbalance:** Mehr Bids als Asks = Kaufdruck, umgekehrt = Verkaufsdruck
- **Spoofing-Erkennung:** Grosse Orders die kurz vor Ausfuehrung verschwinden (Manipulation)
- **Iceberg-Orders:** Versteckte grosse Orders erkennen (nur kleine Teile sichtbar)

### Order Flow Analyse
- **Delta:** Differenz zwischen aggressiven Kaeufen und Verkaeufen pro Kerze
- **Cumulative Delta:** Aufgelaufener Delta ueber Zeit - zeigt echten Kauf-/Verkaufsdruck
- **Footprint Charts:** Volumen pro Preis-Level innerhalb jeder Kerze
- **Absorption:** Grosse Sell-Orders werden aufgekauft ohne Preisrueckgang = bullish

### Liquiditaets-Zonen
- **Liquiditaets-Heatmap:** Wo liegen die meisten Stop-Loss Orders?
  - Unter letztem Swing Low = Stop-Loss Cluster der Long-Positionen
  - Ueber letztem Swing High = Stop-Loss Cluster der Short-Positionen
- **Liquidity Grab:** Preis faehrt kurz unter Support, loest Stops aus, dreht dann um
- **Fair Value Gaps:** Preis-Luecken die oft gefuellt werden

### ML-Features
- `orderbook_imbalance` (-1 bis +1)
- `bid_wall_distance` (Abstand zum naechsten grossen Bid)
- `ask_wall_distance` (Abstand zum naechsten grossen Ask)
- `cumulative_delta` (positiv = Kaufdruck)
- `delta_divergence` (Preis steigt aber Delta faellt = Schwaeche)
- `liquidity_zone_above` (Abstand zur naechsten Liquidity Zone oben)
- `liquidity_zone_below` (Abstand zur naechsten Liquidity Zone unten)
- `absorption_score` (0-100)
- `spread_normalized` (aktueller Spread vs. Durchschnitt)

## Datenquellen
- Capital.com API (Level 2 wenn verfuegbar)
- CME Gold Futures (offizielles Orderbuch)
- Alternative: Bookmap API, Sierra Chart Data Feed

## Technische Umsetzung
- Neues Modul: `orderflow/`
  - `orderbook_analyzer.py` - Bid/Ask Walls, Imbalance
  - `delta_calculator.py` - Delta, Cumulative Delta
  - `liquidity_mapper.py` - Liquiditaets-Zonen erkennen
  - `absorption_detector.py` - Absorption erkennen
  - `orderflow_features.py` - Alle Features fuer ML aufbereiten
- WebSocket-Verbindung fuer Echtzeit-Orderbuch Updates

## Prioritaet: Hoch
