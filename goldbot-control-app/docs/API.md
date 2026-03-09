# API (MVP)

Base URL: `http://127.0.0.1:8060/api/v1`

## Endpunkte
- `GET /health`
- `GET /bot/status`
- `GET /bot/metrics`
- `POST /bot/commands`
- `GET /logs/actions`
- `GET /logs/errors`
- `GET /settings`
- `PUT /settings`
- `GET /trades/chart`

## Privatmodus (neu)
- Alle Endpunkte ausser `GET /health` sind privat.
- Header ist Pflicht: `X-Control-Token: <dein_token>`
- Token kommt aus `CONTROL_APP_ACCESS_TOKEN`.

## Soft-Guards
- Kritische Befehle (`STOP_BOT`, `RELOAD_CONFIG`, `EMERGENCY_STOP`) benoetigen `confirm_token=CONFIRM`, solange `confirmations_enabled=true`.

## Retention
- Action- und Error-Logs werden auf 30 Tage begrenzt (konfigurierbar via `CONTROL_APP_RETENTION_DAYS`).

## Trade-Chart-Daten
- `GET /trades/chart?days=30&limit=600`
- Liefert pro Trade: Einstieg (`entry_price`), `stop_loss`, `take_profit`, optional `exit_price` fuer die Visualisierung.
