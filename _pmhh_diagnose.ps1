# Diagnose-Script — auf pmhh ausfuehren.
# Findet alle tradingbot-Repos auf der Maschine und protokolliert deren Stand.
# Output landet in derselben OneDrive-Datei _pmhh_diagnose_output.txt
# und kommt damit automatisch auf dem anderen PC an.

$ErrorActionPreference = 'Continue'
$out = "C:\Users\fuhhe\OneDrive\Desktop\ai\ai\tradingbot v1\_pmhh_diagnose_output.txt"

# Output-Datei zuruecksetzen
"=== pmhh Diagnose - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $out -Encoding utf8

function Log($msg) { $msg | Out-File $out -Append -Encoding utf8 }
function LogCmd($label, $script) {
    Log ""
    Log "----- $label -----"
    try {
        $result = & $script 2>&1
        $result | Out-File $out -Append -Encoding utf8
    } catch {
        "ERROR: $_" | Out-File $out -Append -Encoding utf8
    }
}

Log "Hostname: $env:COMPUTERNAME"
Log "User: $env:USERNAME"
Log ""

# --- Schritt 1: Alle Ordner finden, die nach dem Repo aussehen ---
Log "=== Schritt 1: Suche tradingbot-Repos auf pmhh ==="
$searchRoots = @(
    "$env:USERPROFILE\OneDrive\Desktop",
    "$env:USERPROFILE\Desktop",
    "$env:USERPROFILE\Documents",
    "$env:USERPROFILE\Documents\GitHub",
    "$env:USERPROFILE\source",
    "$env:USERPROFILE\source\repos",
    "C:\dev",
    "C:\repos",
    "C:\projects"
)

$candidates = @()
foreach ($root in $searchRoots) {
    if (Test-Path $root) {
        try {
            $found = Get-ChildItem -Path $root -Directory -Recurse -Depth 5 -ErrorAction SilentlyContinue |
                     Where-Object {
                         ($_.Name -match 'tradingbot|gold' -or
                          (Test-Path "$($_.FullName)\start_ai_training.py")) -and
                         (Test-Path "$($_.FullName)\.git")
                     }
            $candidates += $found
        } catch {}
    }
}
$candidates = $candidates | Sort-Object FullName -Unique
Log "Gefundene Repos: $($candidates.Count)"
foreach ($c in $candidates) { Log "  $($c.FullName)" }

# --- Schritt 2: Pro Repo Detail-Diagnose ---
foreach ($repo in $candidates) {
    Log ""
    Log "================================================================"
    Log "REPO: $($repo.FullName)"
    Log "================================================================"

    Push-Location $repo.FullName
    try {
        LogCmd "Letzte Aenderung des Ordners" {
            Get-Item $repo.FullName | Select-Object LastWriteTime
        }
        LogCmd "git remote -v" { git remote -v }
        LogCmd "git branch -a" { git branch -a }
        LogCmd "git status" { git status }
        LogCmd "git log --oneline -10 (HEAD)" { git log --oneline -10 }
        LogCmd "git log --oneline origin/master..HEAD (UNGEPUSHTE Commits)" {
            git log --oneline origin/master..HEAD 2>$null
            if ($LASTEXITCODE -ne 0) { git log --oneline origin/main..HEAD 2>$null }
        }
        LogCmd "git stash list" { git stash list }
        LogCmd "Heute geaenderte Files (seit 2026-04-30 00:00)" {
            Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.LastWriteTime -ge [datetime]'2026-04-30' -and
                    $_.FullName -notmatch '\\\.git\\' -and
                    $_.FullName -notmatch '\\__pycache__\\' -and
                    $_.FullName -notmatch '\\\.venv\\' -and
                    $_.FullName -notmatch '\\saved_models\\' -and
                    $_.FullName -notmatch '\\logs\\'
                } |
                Select-Object @{N='Time';E={$_.LastWriteTime.ToString('HH:mm')}}, @{N='Path';E={$_.FullName.Replace($repo.FullName,'.')}} |
                Sort-Object Time -Descending |
                Select-Object -First 50 |
                Format-Table -AutoSize | Out-String
        }
    } finally {
        Pop-Location
    }
}

Log ""
Log "=== Diagnose fertig ==="
Write-Host "Fertig. Output: $out"
Write-Host "Diese Datei wird via OneDrive automatisch zum anderen PC synchronisiert."
