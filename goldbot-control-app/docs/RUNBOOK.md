# Runbook (Lokal)

## Backend starten
```powershell
cd C:\Users\roder\gold_bot\goldbot-control-app
.\scripts\start_backend.ps1
```

Wichtig: fuer den Privatmodus `CONTROL_APP_ACCESS_TOKEN` setzen (siehe `ops/app.env.example`).

## Frontend starten
```powershell
cd C:\Users\roder\gold_bot\goldbot-control-app
.\scripts\start_frontend.ps1
```

## Beide starten
```powershell
cd C:\Users\roder\gold_bot\goldbot-control-app
.\scripts\start_all.ps1
```

## Tests
```powershell
cd C:\Users\roder\gold_bot\goldbot-control-app
C:\Users\roder\gold_bot\.venv\Scripts\python.exe -m pytest -q tests
```
