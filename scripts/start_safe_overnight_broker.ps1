param(
    [double]$Hours = 8,
    [double]$IntervalMinutes = 0,
    [int]$Count = 200000,
    [int]$MinCandles = 200000
)

$ErrorActionPreference = "Stop"

$Root = "C:\Users\roder\gold_bot"
$Py = "C:\Users\roder\tradingsystem\.venv\Scripts\python.exe"
$EnvPath = Join-Path $Root ".env"
$StdOut = Join-Path $Root "logs\overnight_training_stdout.log"
$StdErr = Join-Path $Root "logs\overnight_training_stderr.log"
$RunLog = "logs/overnight_training_runs.jsonl"
$HealthFile = "logs/overnight_training_health.json"
$LockFile = "logs/overnight_training.lock"

if (-not (Test-Path $EnvPath)) {
    throw ".env fehlt in $Root. Bitte erstelle .env mit echten CAPITAL_* Werten."
}

$required = @("CAPITAL_EMAIL", "CAPITAL_PASSWORD", "CAPITAL_API_KEY")
$defaults = @{
    "CAPITAL_EMAIL" = "your-email@example.com"
    "CAPITAL_PASSWORD" = "your-password"
    "CAPITAL_API_KEY" = "your-api-key"
}

$missing = @()
foreach ($k in $required) {
    $line = Select-String -Path $EnvPath -Pattern "^$k=" | Select-Object -First 1
    if (-not $line) {
        $missing += $k
        continue
    }
    $val = ($line.Line -split "=", 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($val) -or $val -eq $defaults[$k]) {
        $missing += $k
    }
}

if ($missing.Count -gt 0) {
    throw "Ungültige .env Werte: $($missing -join ', '). Bitte echte Capital-Credentials eintragen."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

Write-Host "1/2 Smoke-Test (Broker + Training, einmalig) ..."
Push-Location $Root
try {
    & $Py "scripts\train_real_overnight.py" `
        --source broker `
        --timeframe 5m `
        --count $Count `
        --no-allow-count-fallback `
        --min-candles $MinCandles `
        --require-new-candle `
        --no-new-data-sleep-seconds 5 `
        --min-profit-factor 1.05 `
        --min-f1 0.55 `
        --once `
        --preflight `
        --fetch-retries 3 `
        --retry-delay-seconds 20 `
        --max-consecutive-errors 6
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "Smoke-Test fehlgeschlagen (ExitCode=$code). Kein Nachtlauf gestartet."
    }

    Write-Host "2/2 Nachtlauf starten (Hours=$Hours, Interval=$IntervalMinutes min) ..."
    $proc = Start-Process -FilePath $Py -ArgumentList @(
        "scripts\train_real_overnight.py",
        "--source", "broker",
        "--timeframe", "5m",
        "--count", "$Count",
        "--no-allow-count-fallback",
        "--min-candles", "$MinCandles",
        "--hours", "$Hours",
        "--interval-minutes", "$IntervalMinutes",
        "--require-new-candle",
        "--no-new-data-sleep-seconds", "5",
        "--min-profit-factor", "1.05",
        "--min-f1", "0.55",
        "--run-log", $RunLog,
        "--health-file", $HealthFile,
        "--lock-file", $LockFile,
        "--preflight",
        "--fetch-retries", "3",
        "--retry-delay-seconds", "20",
        "--max-consecutive-errors", "6"
    ) -WorkingDirectory $Root -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr -PassThru

    Write-Host "STARTED_PID=$($proc.Id)"
    Write-Host "STDOUT=$StdOut"
    Write-Host "STDERR=$StdErr"
    Write-Host "HEALTH=$($Root)\$HealthFile"
    Write-Host "RUNLOG=$($Root)\$RunLog"
}
finally {
    Pop-Location
}
