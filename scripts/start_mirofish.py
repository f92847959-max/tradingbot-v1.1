"""MiroFish Setup- und Startskript.

Automatisiert die vollstaendige MiroFish-Einrichtung:
  - Git-Klon (falls noch nicht vorhanden)
  - Abhaengigkeiten installieren via uv sync (Python 3.11 venv)
  - .env-Datei erstellen (Ollama als LLM-Backend, ZEP_API_KEY)
  - Flask-Backend starten

Verwendung:
  python scripts/start_mirofish.py            # Setup + Start
  python scripts/start_mirofish.py setup      # Nur Setup (Klon + Install + .env)
  python scripts/start_mirofish.py start      # Nur Backend starten
  python scripts/start_mirofish.py status     # Nur Health-Check
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
MIROFISH_REPO_URL = "https://github.com/666ghj/MiroFish.git"
MIROFISH_DIR = "mirofish"
BACKEND_SUBDIR = "backend"
FLASK_PORT = 5001
HEALTH_CHECK_HOST = "localhost:5001"
HEALTH_CHECK_URL = f"http://{HEALTH_CHECK_HOST}/health"
HEALTH_CHECK_TIMEOUT_SECONDS = 15
LLM_MODEL_NAME = "qwen2.5:7b"
LLM_BASE_URL = "http://localhost:11434/v1"  # Ollama OpenAI-kompatibel
# Windows-spezifischer Python-Pfad in der uv-erstellten venv
# Vollstaendiger Pfad: .venv/Scripts/python.exe (relativ zu mirofish/backend/)
VENV_PYTHON_WIN = Path(".venv") / "Scripts" / "python.exe"


def get_project_root() -> Path:
    """Gibt das Stammverzeichnis des Host-Projekts zurueck."""
    return Path(__file__).parent.parent.resolve()


def get_mirofish_dir(project_root: Path) -> Path:
    """Gibt das MiroFish-Verzeichnis zurueck."""
    return project_root / MIROFISH_DIR


def get_backend_dir(project_root: Path) -> Path:
    """Gibt das MiroFish-Backend-Verzeichnis zurueck."""
    return get_mirofish_dir(project_root) / BACKEND_SUBDIR


def read_host_env(project_root: Path) -> dict:
    """Liest die Host-.env-Datei und gibt ein Dict zurueck.

    Nutzt python-dotenv falls verfuegbar, sonst einfaches Parsing.
    """
    env_file = project_root / ".env"
    env_vars: dict = {}

    if not env_file.exists():
        return env_vars

    try:
        from dotenv import dotenv_values
        env_vars = dict(dotenv_values(env_file))
    except ImportError:
        # Einfaches Fallback-Parsing
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip().strip('"').strip("'")

    return env_vars


def cmd_clone(project_root: Path) -> bool:
    """Klont das MiroFish-Repository, falls nicht vorhanden.

    Gibt True zurueck wenn erfolgreich (oder bereits vorhanden).
    """
    mirofish_dir = get_mirofish_dir(project_root)

    if mirofish_dir.exists():
        print(f"[MiroFish] Verzeichnis bereits vorhanden: {mirofish_dir}")
        return True

    print(f"[MiroFish] Klone Repository von {MIROFISH_REPO_URL} ...")
    result = subprocess.run(
        ["git", "clone", MIROFISH_REPO_URL, str(mirofish_dir)],
        cwd=str(project_root),
        capture_output=False,
    )

    if result.returncode != 0:
        print(f"[MiroFish] FEHLER: Git-Klon fehlgeschlagen (Exit-Code {result.returncode})")
        return False

    print("[MiroFish] Repository erfolgreich geklont.")
    return True


def cmd_install(project_root: Path) -> bool:
    """Installiert MiroFish-Abhaengigkeiten via uv sync.

    Erstellt eine isolierte Python-3.11-Umgebung in mirofish/backend/.venv/
    Gibt True zurueck wenn erfolgreich (oder bereits installiert).
    """
    backend_dir = get_backend_dir(project_root)

    if not backend_dir.exists():
        print(f"[MiroFish] FEHLER: Backend-Verzeichnis nicht gefunden: {backend_dir}")
        print("[MiroFish] Bitte zuerst 'setup' ausfuehren um das Repository zu klonen.")
        return False

    venv_dir = backend_dir / ".venv"
    if venv_dir.exists():
        print(f"[MiroFish] Virtuelle Umgebung bereits vorhanden: {venv_dir}")
        return True

    # Pruefen ob uv verfuegbar ist
    print("[MiroFish] Pruefe ob uv verfuegbar ist ...")
    result = subprocess.run(
        ["uv", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("[MiroFish] FEHLER: 'uv' nicht gefunden. Bitte installieren: https://docs.astral.sh/uv/")
        return False

    print(f"[MiroFish] uv gefunden: {result.stdout.strip()}")
    print("[MiroFish] Installiere Abhaengigkeiten via 'uv sync' (Python 3.11 wird automatisch heruntergeladen) ...")

    result = subprocess.run(
        ["uv", "sync"],
        cwd=str(backend_dir),
        capture_output=False,
    )

    if result.returncode != 0:
        print(f"[MiroFish] FEHLER: 'uv sync' fehlgeschlagen (Exit-Code {result.returncode})")
        return False

    print("[MiroFish] Abhaengigkeiten erfolgreich installiert.")
    return True


def cmd_check_ollama() -> bool:
    """Prueft ob Ollama laeuft und das Modell verfuegbar ist."""
    import urllib.request
    import urllib.error

    print("[MiroFish] Pruefe Ollama-Verbindung ...")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as response:
            if response.status == 200:
                import json
                data = json.loads(response.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                if any(LLM_MODEL_NAME in m for m in models):
                    print(f"[MiroFish] Ollama laeuft, Modell '{LLM_MODEL_NAME}' verfuegbar.")
                    return True
                else:
                    print(f"[MiroFish] FEHLER: Modell '{LLM_MODEL_NAME}' nicht gefunden.")
                    print(f"[MiroFish] Installiere mit: ollama pull {LLM_MODEL_NAME}")
                    return False
    except (urllib.error.URLError, OSError):
        print("[MiroFish] FEHLER: Ollama antwortet nicht auf localhost:11434")
        print("[MiroFish] Bitte Ollama starten (ollama serve) oder installieren: https://ollama.com")
        return False


def cmd_configure(project_root: Path) -> bool:
    """Erstellt die MiroFish .env-Datei, falls nicht vorhanden.

    Verwendet Ollama als LLM-Backend (kostenlos, lokal).
    ZEP_API_KEY wird aus der Host-.env gelesen oder beim Benutzer abgefragt.
    Gibt True zurueck wenn erfolgreich (oder bereits vorhanden).
    """
    backend_dir = get_backend_dir(project_root)

    if not backend_dir.exists():
        print(f"[MiroFish] FEHLER: Backend-Verzeichnis nicht gefunden: {backend_dir}")
        return False

    env_file = backend_dir / ".env"
    if env_file.exists():
        print(f"[MiroFish] .env bereits vorhanden: {env_file}")
        return True

    print("[MiroFish] Erstelle MiroFish .env-Datei (Ollama-Modus) ...")

    # Ollama braucht keinen echten API-Key, aber manche Clients erwarten einen nicht-leeren Wert
    llm_api_key = "ollama"

    # SECURITY: Dieses Verzeichnis liegt in OneDrive (wird in die MS-Cloud gesynct).
    # ZEP_API_KEY deshalb NICHT mehr interaktiv abfragen und in die .env schreiben.
    # Wer Zep-Memory braucht, setzt die Windows-Umgebungsvariable ZEP_API_KEY
    # (setx ZEP_API_KEY <key>) oder traegt den Key manuell in
    # ~/secrets/ai-trading-gold/mirofish.env ein und sourced das vor dem Start.
    zep_api_key = os.environ.get("ZEP_API_KEY", "").strip()

    # .env-Inhalt schreiben (ohne Secrets -- nur nicht-sensible Ollama-Config).
    # ZEP_API_KEY wird NUR geschrieben wenn die Umgebungsvariable einen echten
    # Wert enthaelt. Ein leerer Eintrag wuerde sonst in die OneDrive-gesyncte
    # Datei landen und spaeter den Eindruck erwecken, ein Key sei konfiguriert.
    env_lines = [
        "# MiroFish Konfiguration -- automatisch erstellt von scripts/start_mirofish.py",
        "# Ollama als LLM-Backend (kostenlos, lokal auf GPU)",
        "# KEINE Secrets hier speichern -- das Verzeichnis wird ueber OneDrive gesynct!",
        f"LLM_API_KEY={llm_api_key}",
        f"LLM_BASE_URL={LLM_BASE_URL}",
        f"LLM_MODEL_NAME={LLM_MODEL_NAME}",
    ]
    if zep_api_key:
        env_lines.append(f"ZEP_API_KEY={zep_api_key}")
    env_lines.append(f"FLASK_PORT={FLASK_PORT}")
    env_content = "\n".join(env_lines) + "\n"
    env_file.write_text(env_content, encoding="utf-8")
    print(f"[MiroFish] .env erstellt: {env_file}")

    if not zep_api_key:
        print("[MiroFish] WARNUNG: ZEP_API_KEY leer -- nicht in .env geschrieben (OneDrive-Sync).")
        print("[MiroFish]          Zep-Memory deaktiviert. Key manuell setzen:")
        print("[MiroFish]          setx ZEP_API_KEY <key>  (dann neu starten)")

    return True


def cmd_start(project_root: Path) -> subprocess.Popen | None:
    """Startet den MiroFish Flask-Backend-Prozess.

    Gibt das Popen-Objekt zurueck wenn erfolgreich, sonst None.
    """
    backend_dir = get_backend_dir(project_root)

    if not backend_dir.exists():
        print(f"[MiroFish] FEHLER: Backend-Verzeichnis nicht gefunden: {backend_dir}")
        print("[MiroFish] Bitte zuerst 'setup' ausfuehren.")
        return None

    # Python-Executable aus der uv-venv bestimmen
    python_exe = backend_dir / VENV_PYTHON_WIN
    if not python_exe.exists():
        print(f"[MiroFish] FEHLER: Python-Executable nicht gefunden: {python_exe}")
        print("[MiroFish] Bitte zuerst 'setup' ausfuehren um Abhaengigkeiten zu installieren.")
        return None

    run_py = backend_dir / "run.py"
    if not run_py.exists():
        print(f"[MiroFish] FEHLER: run.py nicht gefunden: {run_py}")
        return None

    print(f"[MiroFish] Starte Flask-Backend auf Port {FLASK_PORT} ...")
    process = subprocess.Popen(
        [str(python_exe), "run.py"],
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Auf Health-Check warten
    print(f"[MiroFish] Warte auf Health-Check ({HEALTH_CHECK_TIMEOUT_SECONDS}s) ...")
    started = _wait_for_health(timeout=HEALTH_CHECK_TIMEOUT_SECONDS)

    if started:
        print(f"[MiroFish] Backend erfolgreich gestartet. URL: {HEALTH_CHECK_URL}")
        return process
    else:
        print(f"[MiroFish] FEHLER: Backend antwortet nicht nach {HEALTH_CHECK_TIMEOUT_SECONDS}s.")
        print(f"[MiroFish] Pruefen Sie die Logs in {backend_dir}")
        process.terminate()
        return None


def cmd_status() -> bool:
    """Fuehrt nur den Health-Check durch.

    Gibt True zurueck wenn Backend erreichbar.
    """
    import urllib.request
    import urllib.error

    try:
        with urllib.request.urlopen(HEALTH_CHECK_URL, timeout=5) as response:
            if response.status == 200:
                print(f"[MiroFish] Status: ONLINE ({HEALTH_CHECK_URL})")
                return True
            else:
                print(f"[MiroFish] Status: FEHLER (HTTP {response.status})")
                return False
    except (urllib.error.URLError, OSError) as e:
        print(f"[MiroFish] Status: OFFLINE ({e})")
        return False


def _wait_for_health(timeout: int) -> bool:
    """Wartet bis der Health-Endpoint antwortet oder Timeout erreicht wird."""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_CHECK_URL, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)

    return False


def main() -> int:
    """Einstiegspunkt mit argparse-CLI."""
    parser = argparse.ArgumentParser(
        description="MiroFish Setup- und Startskript fuer den GoldBot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Unterbefehle:
  setup   -- Klont Repository, installiert Abhaengigkeiten, erstellt .env
  start   -- Startet das Flask-Backend (setzt Setup voraus)
  status  -- Prueft ob das Backend laeuft (Health-Check)
  (kein)  -- Fuehrt Setup + Start aus

Beispiele:
  python scripts/start_mirofish.py
  python scripts/start_mirofish.py setup
  python scripts/start_mirofish.py start
  python scripts/start_mirofish.py status
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["setup", "start", "status"],
        default=None,
        help="Befehl (setup/start/status). Ohne Angabe: setup + start.",
    )
    args = parser.parse_args()

    project_root = get_project_root()
    command = args.command

    # -----------------------------------------------------------------------
    # Status-Befehl
    # -----------------------------------------------------------------------
    if command == "status":
        return 0 if cmd_status() else 1

    # -----------------------------------------------------------------------
    # Setup-Schritte (fuer 'setup' oder kein Befehl)
    # -----------------------------------------------------------------------
    if command in (None, "setup"):
        print("[MiroFish] === Schritt 0/4: Ollama pruefen ===")
        if not cmd_check_ollama():
            return 1

        print("\n[MiroFish] === Schritt 1/3: Repository klonen ===")
        if not cmd_clone(project_root):
            return 1

        print("\n[MiroFish] === Schritt 2/3: Abhaengigkeiten installieren ===")
        if not cmd_install(project_root):
            return 1

        print("\n[MiroFish] === Schritt 3/3: .env konfigurieren ===")
        if not cmd_configure(project_root):
            return 1

        if command == "setup":
            print("\n[MiroFish] Setup abgeschlossen.")
            print("[MiroFish] Backend starten mit: python scripts/start_mirofish.py start")
            return 0

    # -----------------------------------------------------------------------
    # Start-Befehl (fuer 'start' oder kein Befehl nach Setup)
    # -----------------------------------------------------------------------
    if command in (None, "start"):
        print("\n[MiroFish] === Backend starten ===")
        process = cmd_start(project_root)
        if process is None:
            return 1

        print("[MiroFish] Backend laeuft. Prozess-ID:", process.pid)
        print(f"[MiroFish] Dashboard: http://localhost:{FLASK_PORT}")
        print("[MiroFish] Mit Strg+C beenden.")

        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n[MiroFish] Wird beendet ...")
            process.terminate()

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
