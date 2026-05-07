$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

$logDir = Join-Path (Get-Location) "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$transcript = Join-Path $logDir "full_history_training_$stamp.log"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string[]] $Command
    )

    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    Write-Host ($Command -join " ") -ForegroundColor DarkGray
    & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Start-Transcript -Path $transcript -Append | Out-Null

try {
    Write-Host "Full-history Gold training bootstrap" -ForegroundColor Green
    Write-Host "Transcript: $transcript"
    Write-Host "Daily: LBMA PM 1968 -> latest"
    Write-Host "1h: Dukascopy 2003-01-01 -> 2026-05-08"
    Write-Host "1m/5m: Dukascopy 2010-01-01 -> 2026-05-08"
    Write-Host "Training: 5m one-shot dashboard after downloads"

    Invoke-Step "Fetch LBMA daily" @(
        ".\.venv\Scripts\python.exe",
        "scripts\fetch_lbma_daily_gold.py",
        "--output",
        "data\gold_1d.csv"
    )

    Invoke-Step "Fetch Dukascopy 1h from 2003" @(
        ".\.venv\Scripts\python.exe",
        "scripts\fetch_bulk_history.py",
        "--start",
        "2003-01-01",
        "--end",
        "2026-05-08",
        "--timeframes",
        "1h",
        "--output-dir",
        "data",
        "--overwrite",
        "--retries",
        "3",
        "--sleep-seconds",
        "2"
    )

    Invoke-Step "Fetch Dukascopy 1m and resample 5m from 2010" @(
        ".\.venv\Scripts\python.exe",
        "scripts\fetch_bulk_history.py",
        "--start",
        "2010-01-01",
        "--end",
        "2026-05-08",
        "--timeframes",
        "1m,5m",
        "--base-timeframe",
        "1m",
        "--resample-from-base",
        "--output-dir",
        "data",
        "--overwrite",
        "--retries",
        "3",
        "--sleep-seconds",
        "2"
    )

    Invoke-Step "Start 5m training dashboard" @(
        ".\.venv\Scripts\python.exe",
        "scripts\training\one_shot_dashboard.py",
        "--timeframe",
        "5m",
        "--min-data-months",
        "6"
    )

    Write-Host ""
    Write-Host "Full-history training pipeline completed." -ForegroundColor Green
}
finally {
    Stop-Transcript | Out-Null
}
