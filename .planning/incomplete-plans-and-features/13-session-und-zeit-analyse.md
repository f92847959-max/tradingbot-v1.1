# Session- und Zeit-Analyse

## Status: Geplant

## Beschreibung
Gold verhalt sich je nach Handelssession (Asien, London, New York) komplett anders. Zeitbasierte Strategien die diese Unterschiede ausnutzen.

## Features

### Session-Erkennung
| Session | Zeit (UTC) | Charakter |
|---|---|---|
| Sydney/Asien | 22:00-07:00 | Ruhig, Range-bound, niedrige Spreads |
| London | 07:00-16:00 | Hohe Volatilitaet, Breakouts, Hauptbewegung |
| New York | 13:00-22:00 | Hohe Volatilitaet, News-getrieben |
| London/NY Overlap | 13:00-16:00 | Hoechste Volatilitaet, groesste Bewegungen |
| Dead Zone | 20:00-22:00 | Kaum Bewegung, hohe Spreads |

### Session-basierte Strategien
- **London Breakout:** Range der Asien-Session berechnen, Breakout in London traden
- **NY Reversal:** London-Trend kehrt oft in NY um
- **Kill Zones:** Nur in den liquidesten Zeiten traden (London Open, NY Open, Overlap)
- **Dead Zone Filter:** NICHT traden zwischen 20:00-22:00 UTC

### Tages-/Wochen-Patterns
- **Montag:** Oft Range-Day, Richtung fuer die Woche wird gesucht
- **Dienstag-Donnerstag:** Hauptbewegungen, beste Trading-Tage
- **Freitag:** Gewinnmitnahmen, oft Reversal am Nachmittag, vor Weekend-Gap
- **Monatsanfang/-ende:** Window Dressing, Rebalancing

### Saisonale Patterns
- **September-Februar:** Historisch starkste Gold-Monate (Indien Hochzeits-Saison, Weihnachten)
- **Sommer:** Oft Seitwaertsphase
- **Chinesisches Neujahr:** Gold-Nachfrage in China steigt

### ML-Features
- `session` (asia/london/ny/overlap)
- `minutes_since_session_open`
- `asia_range_size` (Groesse der Asien-Range)
- `london_direction` (Richtung seit London Open)
- `day_of_week` (0-4)
- `week_of_month` (1-5)
- `month` (1-12)
- `is_kill_zone` (Boolean)
- `is_dead_zone` (Boolean)
- `session_volatility_ratio` (aktuelle vs. durchschnittliche Session-Vola)

## Technische Umsetzung
- Neues Modul: `sessions/`
  - `session_detector.py` - Aktuelle Session erkennen
  - `session_statistics.py` - Historische Session-Daten
  - `london_breakout.py` - London Breakout Strategie
  - `kill_zone_filter.py` - Nur in besten Zeiten traden
  - `seasonal_analyzer.py` - Saisonale Patterns
  - `session_features.py` - Alle Zeit-Features fuer ML

## Prioritaet: Mittel
