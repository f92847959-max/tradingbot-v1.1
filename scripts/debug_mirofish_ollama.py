"""
MiroFish Debug-Skript mit echtem Ollama-Backend (qwen2.5:7b).

Ruft Ollama direkt auf (OpenAI-kompatible API), zeigt LLM-Antworten live,
parst sie durch parse_swarm_direction() und prueft Veto-Logik.

Voraussetzung:
  ollama serve
  ollama pull qwen2.5:7b
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

# Projektpfad
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.mirofish_client import parse_swarm_direction

# ANSI-Farben
os.system("")
GOLD = "\033[33m"
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BLUE = "\033[94m"
GREY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
MODEL = "qwen2.5:7b"
TIMEOUT = 180  # 7b braucht laenger

# ----- Agenten-Definitionen -----------------------------------------------

AGENTS = [
    {
        "name": "ZENTRALBANKER",
        "role": "Institutioneller Goldinvestor (Zentralbank)",
        "system": (
            "Du bist ein erfahrener Zentralbanker, der ueber Goldreserven entscheidet. "
            "Du analysierst makrooekonomische Faktoren wie Zinsen, Inflation und "
            "geopolitische Risiken. Antworte auf Deutsch in 4-6 Saetzen."
        ),
        "user": (
            "Aktuelle Marktlage XAUUSD (Gold/USD):\n"
            "- Spot: 2287 $/oz\n"
            "- Fed Funds Rate: 5.25%\n"
            "- US CPI YoY: 3.2%\n"
            "- DXY: 104.1 (-0.3% heute)\n"
            "- Geopolitik: Ukraine, Taiwan-Spannungen\n\n"
            "Soll deine Zentralbank Gold KAUFEN, VERKAUFEN oder HALTEN? "
            "Begruende kurz mit makro-oekonomischer Analyse."
        ),
    },
    {
        "name": "MAKRO-ANALYST",
        "role": "Volkswirtschaftlicher Analyst",
        "system": (
            "Du bist ein Volkswirtschaftler mit Spezialisierung auf Edelmetalle. "
            "Du nutzt Korrelationsanalysen (Dollar, Realzinsen, Inflation). "
            "Antworte auf Deutsch in 4-6 Saetzen."
        ),
        "user": (
            "XAUUSD steht bei 2287 $/oz. DXY hat 0.3% verloren. Die Markterwartung "
            "preist eine Rate-Cut-Wahrscheinlichkeit von 65% in 3 Monaten. "
            "Realzinsen 10J: +1.8%. Was ist deine Richtungsprognose? "
            "Kaufsignal, Verkaufsignal oder neutral?"
        ),
    },
    {
        "name": "TECHNIKER",
        "role": "Technischer Analyst",
        "system": (
            "Du bist Charttechniker. Du beurteilst Trends, RSI, Moving Averages und "
            "Volume-Profile. Antworte auf Deutsch in 4-6 Saetzen."
        ),
        "user": (
            "XAUUSD Tageschart:\n"
            "- Spot 2287, 20-EMA bei 2285 (Preis darueber)\n"
            "- RSI(14) = 58\n"
            "- Letzte Kerze: bullisches Doji\n"
            "- Widerstand: 2300, 2310 (Fib 61.8%)\n"
            "- Stuetzung: 2270-2280 Volume-Profile\n\n"
            "Wie ist deine technische Einschaetzung? Kaufsignal oder Verkaufssignal?"
        ),
    },
    {
        "name": "ROHSTOFF-TRADER",
        "role": "Spotmarkt-Haendler",
        "system": (
            "Du bist Rohstoffhaendler am Goldmarkt. Du beurteilst Angebot, Nachfrage, "
            "COT-Daten und physische Marktstrukturen. Antworte auf Deutsch in 4-6 Saetzen."
        ),
        "user": (
            "Aktueller Markt:\n"
            "- Asien: physische Goldnachfrage saisonal hoch (Hochzeiten Indien)\n"
            "- COT: Commercials netto long +15.000 Kontrakte\n"
            "- Terminstruktur: leichte Backwardation\n"
            "- Energiepreise: WTI +2% diese Woche\n\n"
            "Wie positionierst du dich? Long, Short oder neutral?"
        ),
    },
]

# ----- Ollama-Helfer -------------------------------------------------------


def check_ollama():
    """Prueft ob Ollama laeuft und Modell vorhanden ist."""
    print(f"{CYAN}[1/3] Pruefe Ollama-Verbindung ...{RESET}")
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            print(f"  {GREEN}OK{RESET} Ollama laeuft auf localhost:11434")
            print(f"  {GREY}Verfuegbare Modelle: {len(models)}{RESET}")
            for m in models:
                marker = f"{GREEN}*{RESET}" if MODEL in m else " "
                print(f"   {marker} {m}")
            if not any(MODEL in m for m in models):
                print(f"\n{RED}FEHLER: Modell '{MODEL}' nicht gefunden.{RESET}")
                print(f"{YELLOW}Installiere mit:  ollama pull {MODEL}{RESET}")
                return False
            return True
    except Exception as e:
        print(f"{RED}FEHLER: Ollama nicht erreichbar.{RESET}")
        print(f"{GREY}Detail: {type(e).__name__}: {e}{RESET}")
        print(f"\n{YELLOW}Starte Ollama mit:  ollama serve{RESET}")
        return False


def call_ollama(system: str, user: str, agent_name: str) -> str:
    """Ruft Ollama via OpenAI-kompatible API auf, streamt Token live."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": 0.7,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.time()
    print(f"{GREY}  → POST {OLLAMA_URL}  ({len(body)} bytes){RESET}")
    print(f"{GREY}  → model={MODEL}, temp=0.7{RESET}")
    print(f"{GREY}  → warte auf Antwort (kann 30-90s dauern bei 7b) ...{RESET}")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            elapsed = time.time() - t0
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", "?")
            tokens_out = usage.get("completion_tokens", "?")

            print(f"{GREY}  ← antwort in {elapsed:.1f}s  "
                  f"[in:{tokens_in} out:{tokens_out} tok]{RESET}")
            return text
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"{RED}  ← HTTP {e.code}: {body[:300]}{RESET}")
        return ""
    except Exception as e:
        print(f"{RED}  ← Fehler: {type(e).__name__}: {e}{RESET}")
        return ""


# ----- Hauptlauf -----------------------------------------------------------


def banner():
    print(f"""
{GOLD}{BOLD}╔══════════════════════════════════════════════════════════════════╗
║   MIROFISH DEBUG-LAUF — Ollama qwen2.5:7b — Echte LLM-Aufrufe   ║
║   Modell: {MODEL:<54} ║
║   Endpunkt: {OLLAMA_URL:<52} ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
""")


def print_agent_response(name: str, role: str, text: str):
    print(f"\n{BLUE}{BOLD}[{name}]{RESET} {GREY}{role}{RESET}")
    print(f"{GREY}{'─'*66}{RESET}")
    if not text:
        print(f"  {RED}<keine Antwort>{RESET}")
        return
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            print(f"  {line}")


def main():
    banner()

    if not check_ollama():
        sys.exit(1)

    print(f"\n{CYAN}[2/3] Sende Prompts an {len(AGENTS)} Gold-Agenten ...{RESET}\n")

    all_responses = []
    for i, agent in enumerate(AGENTS, 1):
        print(f"\n{MAGENTA}{BOLD}━━━ Agent {i}/{len(AGENTS)}: {agent['name']} ━━━{RESET}")
        response = call_ollama(agent["system"], agent["user"], agent["name"])
        print_agent_response(agent["name"], agent["role"], response)
        all_responses.append((agent["name"], response))

    # ----- Aggregation zu pseudo-MiroFish-Report ---------------------------
    print(f"\n{CYAN}[3/3] Aggregiere zu Schwarm-Report ...{RESET}")
    aggregated = "# XAUUSD Schwarm-Intelligence Report\n\n"
    for name, text in all_responses:
        aggregated += f"## {name}\n{text}\n\n"

    direction, confidence, reasoning = parse_swarm_direction(aggregated)

    color = GREEN if direction == "BUY" else RED if direction == "SELL" else YELLOW
    arrow = "▲ LONG (BUY)" if direction == "BUY" else "▼ SHORT (SELL)" if direction == "SELL" else "◆ NEUTRAL"

    print(f"\n{color}{BOLD}{'='*66}")
    print(f"  SCHWARM-RICHTUNG : {arrow}")
    print(f"  KONFIDENZ        : {confidence*100:.1f}%")
    print(f"  REASONING        : {reasoning[:120]}")
    print(f"{'='*66}{RESET}")

    # ----- Veto-Test -------------------------------------------------------
    print(f"\n{CYAN}Veto-Logik gegen ML-Signale:{RESET}\n")

    for ml_action in ["BUY", "SELL", "HOLD"]:
        if ml_action == "HOLD":
            outcome = f"{GREY}durchgewunken (HOLD = kein Veto){RESET}"
        elif (ml_action == "BUY" and direction == "SELL") or \
             (ml_action == "SELL" and direction == "BUY"):
            outcome = f"{RED}VETOED → HOLD{RESET}"
        else:
            outcome = f"{GREEN}BESTAETIGT (mirofish_direction={direction}){RESET}"
        print(f"  ML={ml_action:<5} → {outcome}")

    # ----- Debug-Statistik -------------------------------------------------
    print(f"\n{GOLD}{'─'*66}")
    print("  Debug-Statistik")
    print(f"{'─'*66}{RESET}")
    print(f"  Modell:           {MODEL}")
    print(f"  Agenten gerufen:  {len(AGENTS)}")
    erfolgreich = sum(1 for _, t in all_responses if t)
    print(f"  Erfolgreich:      {erfolgreich}/{len(AGENTS)}")
    print(f"  Aggregierte Laenge: {len(aggregated)} Zeichen")
    print("  Bullische Keywords gefunden im Report (siehe parser-output)")

    print(f"\n{GREEN}{BOLD}Debug-Lauf abgeschlossen.{RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[Abgebrochen durch Benutzer]{RESET}")
        sys.exit(130)
