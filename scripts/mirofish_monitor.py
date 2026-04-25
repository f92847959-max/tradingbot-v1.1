"""MiroFish Live-Monitor: Zeigt den aktuellen Status der Pipeline."""

import time
import json
import urllib.request
import urllib.error

BASE = "http://localhost:5001"
REFRESH = 2  # Sekunden


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def clear():
    # Cursor nach oben bewegen statt Screen loeschen - kein Flackern
    print("\033[H", end="", flush=True)


def bar(pct, width=30):
    filled = int(width * pct / 100)
    return f"[{'#' * filled}{'-' * (width - filled)}] {pct:3d}%"


def out(text=""):
    """Print mit Zeilenrest loeschen - verhindert Artefakte."""
    print(f"{text}\033[K", flush=True)


def main():
    steps = [
        "1. Ontologie generieren (LLM analysiert Seeds)",
        "2. Knowledge Graph aufbauen (Zep)",
        "3. Agenten-Profile erstellen (LLM)",
        "4. Simulation laeuft (Agenten diskutieren)",
        "5. Report generieren (LLM)",
    ]

    # Einmal Screen leeren, danach nur Cursor zuruecksetzen
    print("\033[2J\033[H", end="", flush=True)
    while True:
        clear()
        out("=" * 56)
        out("   MIROFISH SWARM INTELLIGENCE - LIVE MONITOR")
        out("=" * 56)
        out()

        # Backend check
        health = fetch(f"{BASE}/health")
        if not health:
            out("  Backend: OFFLINE")
            out()
            out("  Warte auf MiroFish Backend ...")
            time.sleep(REFRESH)
            continue

        out("  Backend: ONLINE (localhost:5001)")
        out("  LLM:     Qwen2.5:7b via Ollama (lokal)")
        out()

        # Projekte checken
        projects = fetch(f"{BASE}/api/graph/project/list")
        if not projects or not projects.get("data"):
            out("  Status: Warte auf Projektstart ...")
            for i, s in enumerate(steps):
                out(f"    {'>' if i == 0 else ' '} {s}  {bar(0) if i == 0 else ''}")
            time.sleep(REFRESH)
            continue

        proj = projects["data"][-1]  # neuestes Projekt
        proj_id = proj.get("project_id", "?")
        proj_status = proj.get("status", "unknown")
        proj_name = proj.get("name", "?")

        out(f"  Projekt: {proj_name}")
        out(f"  ID:      {proj_id}")
        out()

        # Status mapping
        step_progress = [0, 0, 0, 0, 0]
        current_step = 0
        detail = ""

        if proj_status == "created":
            step_progress[0] = 10
            current_step = 0
            detail = "Projekt erstellt, warte auf Ontologie ..."

        elif proj_status == "ontology_generated":
            step_progress[0] = 100
            current_step = 1
            detail = "Ontologie fertig! Graph wird vorbereitet ..."

            # Check ob Graph-Build laeuft
            task_id = proj.get("graph_build_task_id")
            if task_id:
                task = fetch(f"{BASE}/api/graph/task/{task_id}")
                if task and task.get("data"):
                    td = task["data"]
                    step_progress[1] = td.get("progress", 0)
                    detail = td.get("message", "Graph wird gebaut ...")
                    if td.get("status") == "completed":
                        step_progress[1] = 100
                        current_step = 2

        elif proj_status == "graph_building":
            step_progress[0] = 100
            current_step = 1
            task_id = proj.get("graph_build_task_id")
            if task_id:
                task = fetch(f"{BASE}/api/graph/task/{task_id}")
                if task and task.get("data"):
                    td = task["data"]
                    step_progress[1] = td.get("progress", 5)
                    detail = td.get("message", "Graph wird gebaut ...")

        elif proj_status == "graph_completed":
            step_progress[0] = 100
            step_progress[1] = 100
            current_step = 2
            detail = "Graph fertig! Simulation wird vorbereitet ..."

        elif proj_status == "failed":
            detail = f"FEHLER: {proj.get('error', 'unbekannt')}"

        # Simulationen checken
        sims = fetch(f"{BASE}/api/simulation/list?project_id={proj_id}")
        if sims and sims.get("data"):
            sim = sims["data"][-1]
            sim_id = sim.get("simulation_id", "")
            sim_status = sim.get("status", "")

            if sim_status in ("created", "preparing_profiles"):
                step_progress[0] = 100
                step_progress[1] = 100
                step_progress[2] = 30
                current_step = 2
                detail = "Agenten-Profile werden generiert ..."

            elif sim_status == "preparing_config":
                step_progress[0] = 100
                step_progress[1] = 100
                step_progress[2] = 70
                current_step = 2
                detail = "Simulations-Konfiguration wird erstellt ..."

            elif sim_status == "ready":
                step_progress[0] = 100
                step_progress[1] = 100
                step_progress[2] = 100
                current_step = 3
                detail = "Bereit! Simulation startet gleich ..."

            elif sim_status == "running":
                step_progress[0] = 100
                step_progress[1] = 100
                step_progress[2] = 100
                current_step = 3

                # Run-Status holen
                rs = fetch(f"{BASE}/api/simulation/{sim_id}/run-status")
                if rs and rs.get("data"):
                    rd = rs["data"]
                    cur = rd.get("current_round", 0)
                    total = rd.get("total_rounds", 10)
                    pct = int(cur / max(total, 1) * 100)
                    step_progress[3] = pct
                    detail = f"Runde {cur}/{total} - Agenten diskutieren ..."

            elif sim_status == "completed":
                step_progress[0] = 100
                step_progress[1] = 100
                step_progress[2] = 100
                step_progress[3] = 100
                current_step = 4
                detail = "Simulation fertig! Report wird generiert ..."

                # Report checken
                rep = fetch(f"{BASE}/api/report/list?simulation_id={sim_id}")
                if rep and rep.get("data"):
                    rep_status = rep["data"][-1].get("status", "")
                    if rep_status == "completed":
                        step_progress[4] = 100
                        current_step = 5
                        detail = "FERTIG! Report liegt vor."
                    elif rep_status == "generating":
                        step_progress[4] = 50
                        detail = "Report wird geschrieben ..."

        # Anzeige
        out("  FORTSCHRITT:")
        out()
        total_pct = sum(step_progress) // 5

        for i, s in enumerate(steps):
            marker = ">>>" if i == current_step else "   "
            check = "OK" if step_progress[i] >= 100 else "  "
            out(f"  {marker} [{check}] {s}")
            if i == current_step:
                out(f"         {bar(step_progress[i])}")
                if detail:
                    out(f"         {detail}")
            out()

        out("-" * 56)
        out(f"  GESAMT: {bar(total_pct, 40)}")
        out()
        out("  Strg+C zum Beenden")

        time.sleep(REFRESH)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor beendet.")
