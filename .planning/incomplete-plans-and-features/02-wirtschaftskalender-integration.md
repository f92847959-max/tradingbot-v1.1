# Wirtschaftskalender-Integration

## Status: Geplant

## Beschreibung
Automatische Integration von Wirtschaftsevents (NFP, CPI, Fed etc.) in die Trading-Entscheidungen. Schuetzt vor unkontrollierten Verlusten bei High-Impact Events.

## Features

### Event-Daten laden
- API-Anbindung: Forex Factory, Investing.com Calendar, FXStreet
- Events automatisch taeglich aktualisieren
- Felder: Datum/Uhrzeit, Event-Name, Land, Impact (Low/Medium/High), Forecast, Previous, Actual

### Gold-relevante Events filtern
- US-Daten (Fed Zinsentscheid, NFP, CPI, GDP, PMI, Retail Sales)
- EZB/BoE/BoJ Zinsentscheide (indirekt ueber Dollar)
- Geopolitische Events (manuell taggen)
- Gold-spezifisch: COT-Report, COMEX Inventory, Central Bank Gold Purchases

### Trading-Regeln
- **Pre-Event (30 Min vorher):**
  - High Impact: Keine neuen Trades, bestehende Positionen absichern (enger SL)
  - Medium Impact: Reduzierte Positionsgroesse (50%)
  - Low Impact: Normal traden
- **Post-Event:**
  - Volatilitaets-Cooldown: 15 Min nach High-Impact Event warten
  - Erst traden wenn Spread wieder normal ist
- **Event-Ueberraschung:**
  - Actual vs. Forecast Abweichung messen
  - Grosse Abweichung = staerkeres Signal

### ML-Features
- Minuten bis naechstes High-Impact Event
- Anzahl Events heute (Busy Day = vorsichtiger)
- Event-Surprise-Score (Actual vs. Forecast)
- Ist gerade "Event Season" (NFP-Woche, Fed-Woche)

## Technische Umsetzung
- Neues Modul: `calendar/`
  - `event_fetcher.py` - API-Anbindung Wirtschaftskalender
  - `event_filter.py` - Gold-relevante Events filtern
  - `event_rules.py` - Pre/Post Event Trading-Regeln
  - `event_repository.py` - DB-Speicherung
- Integration in `risk/risk_manager.py` - Pre-Trade Check: "Event in der Naehe?"
- Integration in `ai_engine/features/` - Event-Features fuers Modell

## Prioritaet: Hoch
