# GoldBot Control App

Dieser App-Bereich wird **ausschliesslich** unter folgendem Pfad genutzt:  
`C:\Users\roder\gold_bot\goldbot-control-app`

Alle Implementierungen, Skripte, Tests und Dokumentation fuer die Control-App muessen in genau diesem Ordner liegen.

## Unterordner (verbindlich)
- `frontend`: React + TypeScript Dashboard-UI.
- `backend`: FastAPI API fuer Monitoring und manuelle Befehle.
- `shared`: Geteilte API-Vertraege/Typen fuer Frontend und Backend.
- `database`: SQLite-Datei und DB-bezogene Assets.
- `integration`: Adapter zur Anbindung an bestehende `gold_bot`-Module.
- `scripts`: Lokale Start- und Setup-Skripte.
- `tests`: Unit-, API- und E2E-Smoke-Tests.
- `docs`: Architektur, API und Runbook.
- `ops`: Lokale Betriebs-/Konfigurationsdateien.
- `logs`: Laufzeit-Logs der Control-App.

Details: siehe [docs/STRUCTURE.md](./docs/STRUCTURE.md).

