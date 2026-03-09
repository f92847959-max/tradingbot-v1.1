$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
$projectVenv = Join-Path $root ".venv\Scripts\python.exe"
$parentVenv = Join-Path (Split-Path $root -Parent) ".venv\Scripts\python.exe"

if (Test-Path $projectVenv) {
  $python = $projectVenv
} elseif (Test-Path $parentVenv) {
  $python = $parentVenv
} else {
  $python = "python"
}

Push-Location $root
try {
  & $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8060 --reload
} finally {
  Pop-Location
}
