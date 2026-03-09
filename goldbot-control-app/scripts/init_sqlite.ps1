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
  & $python -c "from backend.app.database import init_db; init_db(); print('SQLite initialized.')"
} finally {
  Pop-Location
}
