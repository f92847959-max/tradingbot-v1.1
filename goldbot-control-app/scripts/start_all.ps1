$ErrorActionPreference = "Stop"

$scriptRoot = Resolve-Path $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptRoot "start_backend.ps1")
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptRoot "start_frontend.ps1")

Write-Output "Started backend and frontend in separate PowerShell windows."

