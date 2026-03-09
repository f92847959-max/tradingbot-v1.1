# Verbindliche Ordnernutzung

**Pfadbindung:** Diese App wird nur in `C:\Users\roder\gold_bot\goldbot-control-app` aufgebaut und betrieben.

## `frontend`
- **Genau dieser Ordner wird genutzt** fuer die Browser-UI.
- Inhalt: React Komponenten, Hooks, API-Client, Styles, Build-Konfiguration.

## `backend`
- **Genau dieser Ordner wird genutzt** fuer die FastAPI-Serverlogik.
- Inhalt: Router, Service-Schicht, Guards, DB-Access, App-Entry.

## `shared`
- **Genau dieser Ordner wird genutzt** fuer gemeinsame Vertraege.
- Inhalt: Python-Contracts (`contracts.py`) und TypeScript-Typen (`types.ts`).

## `database`
- **Genau dieser Ordner wird genutzt** fuer die lokale SQLite-Datenbank und DB-Hinweise.
- Inhalt: `control_app.db` (runtime), DB-README.

## `integration`
- **Genau dieser Ordner wird genutzt** fuer Adapter zum bestehenden Trading-System.
- Inhalt: `goldbot_adapter.py` als Anbindungsflaeche.

## `scripts`
- **Genau dieser Ordner wird genutzt** fuer lokale Betriebs-Skripte.
- Inhalt: Start Backend/Frontend/All und DB-Init.

## `tests`
- **Genau dieser Ordner wird genutzt** fuer die Control-App Tests.
- Inhalt: `unit`, `api`, `e2e` mit pytest.

## `docs`
- **Genau dieser Ordner wird genutzt** fuer technische Dokumentation.
- Inhalt: API-Vertrag, Architektur, Runbook, Strukturregeln.

## `ops`
- **Genau dieser Ordner wird genutzt** fuer lokale Betriebs-Konfiguration.
- Inhalt: `app.env.example`, Logging-Konfiguration.

## `logs`
- **Genau dieser Ordner wird genutzt** fuer Laufzeit-Logdateien der Control-App.
- Inhalt: Audit/Fehler-Logs (mit 30-Tage-Retention ueber Backend-Logik).

