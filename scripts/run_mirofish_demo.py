"""MiroFish Swarm-Demo: Zeigt die 10 Gold-Agenten live beim Diskutieren.

Fuehrt die komplette Pipeline aus:
  1. Seed-Dateien hochladen + Ontologie generieren (LLM analysiert Goldmarkt-Daten)
  2. Zep Knowledge Graph aufbauen
  3. Simulation starten (10 Agenten diskutieren ueber XAUUSD)
  4. Report generieren und anzeigen
"""

import httpx
import time
import sys
from pathlib import Path

BASE = "http://localhost:5001"
SEED_DIR = Path(__file__).parent.parent / "mirofish_seeds"
MAX_ROUNDS = 10
POLL_INTERVAL = 3


def log(msg: str) -> None:
    print(f"[MiroFish] {msg}", flush=True)


def poll_task(task_id: str, label: str, client: httpx.Client) -> dict:
    """Pollt einen Task bis er fertig ist."""
    while True:
        r = client.get(f"{BASE}/api/graph/task/{task_id}")
        data = r.json().get("data", {})
        status = data.get("status", "unknown")
        msg = data.get("message", "")
        progress = data.get("progress", 0)
        print(f"  [{label}] {progress}% - {msg}", flush=True)
        if status in ("completed", "failed"):
            return data
        time.sleep(POLL_INTERVAL)


def main() -> int:
    client = httpx.Client(timeout=600)  # 10 min - Qwen2.5:7b auf GTX 1650 braucht Zeit

    # Health check
    log("Pruefe Backend ...")
    try:
        r = client.get(f"{BASE}/health")
        if r.status_code != 200:
            log("FEHLER: Backend antwortet nicht!")
            return 1
    except Exception as e:
        log(f"FEHLER: {e}")
        return 1
    log("Backend ONLINE\n")

    # ===== SCHRITT 1: Ontologie generieren =====
    log("=" * 60)
    log("SCHRITT 1: Seed-Dateien hochladen + Ontologie generieren")
    log("=" * 60)

    seed_files = sorted(SEED_DIR.glob("*.md"))
    if not seed_files:
        log(f"FEHLER: Keine Seed-Dateien in {SEED_DIR}")
        return 1

    for f in seed_files:
        log(f"  Datei: {f.name}")

    files = []
    for f in seed_files:
        files.append(("files", (f.name, f.read_bytes(), "text/markdown")))

    log("Sende an LLM zur Analyse (Qwen2.5:7b via Ollama) ...")
    r = client.post(
        f"{BASE}/api/graph/ontology/generate",
        files=files,
        data={
            "simulation_requirement": (
                "Simuliere eine Diskussion von 10 Wirtschaftsexperten ueber den XAUUSD-Goldmarkt. "
                "Die Agenten sollen verschiedene Perspektiven vertreten: Zentralbankpolitik, "
                "Inflation, Dollar-Staerke, Geopolitik, Anleihenmaerkte, Rohstoffe, Hedgefonds, "
                "Schwellenlaender. Diskussion auf Deutsch. Ziel: Konsens-Einschaetzung ob "
                "Gold steigt oder faellt."
            ),
            "project_name": "GoldBot XAUUSD Swarm Analysis",
        },
    )

    if r.status_code != 200:
        log(f"FEHLER ({r.status_code}): {r.text[:500]}")
        return 1

    result = r.json()
    project_id = result["data"]["project_id"]
    ontology = result["data"].get("ontology", {})
    entity_types = ontology.get("entity_types", [])
    edge_types = ontology.get("edge_types", [])

    log(f"\nProjekt erstellt: {project_id}")
    log(f"Ontologie: {len(entity_types)} Entitaetstypen, {len(edge_types)} Beziehungstypen")
    for et in entity_types:
        name = et.get("name", et) if isinstance(et, dict) else et
        log(f"  Agent-Typ: {name}")
    print()

    # ===== SCHRITT 2: Knowledge Graph aufbauen =====
    log("=" * 60)
    log("SCHRITT 2: Zep Knowledge Graph aufbauen")
    log("=" * 60)

    r = client.post(
        f"{BASE}/api/graph/build",
        json={"project_id": project_id},
    )

    if r.status_code != 200:
        log(f"FEHLER ({r.status_code}): {r.text[:500]}")
        return 1

    task_id = r.json()["data"]["task_id"]
    log(f"Graph-Build gestartet (Task: {task_id})")

    task_result = poll_task(task_id, "Graph", client)
    if task_result.get("status") == "failed":
        log(f"FEHLER: {task_result.get('message', 'unbekannt')}")
        return 1

    graph_id = task_result.get("result", {}).get("graph_id", "")
    node_count = task_result.get("result", {}).get("node_count", 0)
    edge_count_graph = task_result.get("result", {}).get("edge_count", 0)
    log(f"\nGraph fertig: {node_count} Knoten, {edge_count_graph} Kanten")
    log(f"Graph ID: {graph_id}\n")

    # ===== SCHRITT 3: Simulation erstellen + vorbereiten =====
    log("=" * 60)
    log("SCHRITT 3: Agenten-Simulation vorbereiten")
    log("=" * 60)

    r = client.post(
        f"{BASE}/api/simulation/create",
        json={"project_id": project_id, "graph_id": graph_id},
    )
    if r.status_code != 200:
        log(f"FEHLER ({r.status_code}): {r.text[:500]}")
        return 1

    sim_data = r.json().get("data", {})
    simulation_id = sim_data.get("simulation_id", "")
    log(f"Simulation erstellt: {simulation_id}")

    # Profile vorbereiten
    log("Generiere Agenten-Profile (LLM erstellt Persoenlichkeiten) ...")
    r = client.post(
        f"{BASE}/api/simulation/prepare",
        json={"simulation_id": simulation_id, "type": "profiles"},
    )
    if r.status_code != 200:
        log(f"FEHLER Profile ({r.status_code}): {r.text[:500]}")
        return 1

    # Poll prepare status
    while True:
        r = client.post(f"{BASE}/api/simulation/prepare/status", json={"simulation_id": simulation_id})
        status_data = r.json().get("data", {})
        profiles_ready = status_data.get("profiles_ready", False)
        log(f"  Profile: {'FERTIG' if profiles_ready else 'wird generiert ...'}")
        if profiles_ready:
            break
        time.sleep(POLL_INTERVAL)

    # Config vorbereiten
    log("Generiere Simulations-Konfiguration ...")
    r = client.post(
        f"{BASE}/api/simulation/prepare",
        json={"simulation_id": simulation_id, "type": "config"},
    )
    if r.status_code != 200:
        log(f"FEHLER Config ({r.status_code}): {r.text[:500]}")
        return 1

    while True:
        r = client.post(f"{BASE}/api/simulation/prepare/status", json={"simulation_id": simulation_id})
        status_data = r.json().get("data", {})
        config_ready = status_data.get("config_ready", False)
        log(f"  Config: {'FERTIG' if config_ready else 'wird generiert ...'}")
        if config_ready:
            break
        time.sleep(POLL_INTERVAL)

    print()

    # ===== SCHRITT 4: Simulation starten =====
    log("=" * 60)
    log(f"SCHRITT 4: SIMULATION STARTEN ({MAX_ROUNDS} Runden)")
    log("=" * 60)
    log("Die Agenten diskutieren jetzt ueber den Goldmarkt ...\n")

    r = client.post(
        f"{BASE}/api/simulation/start",
        json={
            "simulation_id": simulation_id,
            "platform": "parallel",
            "max_rounds": MAX_ROUNDS,
            "enable_graph_memory_update": False,
        },
    )
    if r.status_code != 200:
        log(f"FEHLER Start ({r.status_code}): {r.text[:500]}")
        return 1

    # Poll simulation
    last_round = -1
    while True:
        r = client.get(f"{BASE}/api/simulation/{simulation_id}/run-status")
        run_data = r.json().get("data", {})
        status = run_data.get("status", "unknown")
        current_round = run_data.get("current_round", 0)
        total_rounds = run_data.get("total_rounds", MAX_ROUNDS)
        messages = run_data.get("recent_messages", [])

        if current_round != last_round:
            log(f"--- Runde {current_round}/{total_rounds} ---")
            last_round = current_round

        for msg in messages:
            agent = msg.get("agent_name", msg.get("sender", "?"))
            content = msg.get("content", msg.get("message", ""))[:200]
            print(f"  [{agent}]: {content}", flush=True)

        if status in ("completed", "failed"):
            break
        time.sleep(POLL_INTERVAL)

    if status == "failed":
        log("Simulation FEHLGESCHLAGEN")
        return 1

    log("\nSimulation ABGESCHLOSSEN\n")

    # ===== SCHRITT 5: Report generieren =====
    log("=" * 60)
    log("SCHRITT 5: Analyse-Report generieren")
    log("=" * 60)

    r = client.post(
        f"{BASE}/api/report/generate",
        json={"simulation_id": simulation_id},
    )
    if r.status_code != 200:
        log(f"FEHLER Report ({r.status_code}): {r.text[:500]}")
        return 1

    # Poll report
    report_id = None
    while True:
        r = client.post(f"{BASE}/api/report/generate/status", json={"simulation_id": simulation_id})
        rep_data = r.json().get("data", {})
        rep_status = rep_data.get("status", "unknown")
        log(f"  Report: {rep_status}")
        if rep_status == "completed":
            report_id = rep_data.get("report_id", "")
            break
        if rep_status == "failed":
            log("Report-Generierung fehlgeschlagen")
            return 1
        time.sleep(POLL_INTERVAL)

    # Report abrufen
    r = client.get(f"{BASE}/api/report/{report_id}")
    report_content = r.json().get("data", {}).get("content", "Kein Inhalt")

    print()
    log("=" * 60)
    log("ERGEBNIS: Schwarm-Analyse XAUUSD Gold")
    log("=" * 60)
    print()
    print(report_content)
    print()

    # Richtung parsen
    text_lower = report_content.lower()
    bullish = sum(1 for kw in ["aufwaertstrend", "steigende preise", "bullish", "kaufsignal", "inflationsdruck", "dollar schwaecht"] if kw in text_lower)
    bearish = sum(1 for kw in ["abwaertstrend", "fallende preise", "bearish", "verkaufssignal", "dollar staerkt", "zinsanstieg"] if kw in text_lower)

    if bullish > bearish:
        log(f"SIGNAL: BUY (bullish: {bullish}, bearish: {bearish})")
    elif bearish > bullish:
        log(f"SIGNAL: SELL (bullish: {bullish}, bearish: {bearish})")
    else:
        log(f"SIGNAL: NEUTRAL (bullish: {bullish}, bearish: {bearish})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
