$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot\.."
Push-Location (Join-Path $root "frontend")
try {
  $npm = "npm.cmd"
  if (-not (Test-Path "node_modules")) {
    & $npm install
  }
  & $npm run dev
} finally {
  Pop-Location
}
