"""
MiroFish Dashboard (Tkinter) - Streaming Edition
GUI fuer Live-Debugging der Agenten-Simulation mit gpt-oss:20b (MoE).
Streamt Tokens live und trennt Thinking-Phase von finaler Antwort.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import scrolledtext

# Projektpfad
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine.mirofish_client import parse_swarm_direction

# ----- Config --------------------------------------------------------------
OLLAMA_CHAT = "http://localhost:11434/v1/chat/completions"
OLLAMA_TAGS = "http://localhost:11434/api/tags"
MODEL = "gpt-oss:20b"
TIMEOUT = 600  # MoE kann beim ersten Lauf langsam sein

# ----- Farben (Dark Theme) -------------------------------------------------
BG       = "#1e1e1e"
PANEL    = "#252526"
DEEP     = "#0f0f0f"
FG       = "#d4d4d4"
GOLD     = "#ffb700"
GREEN    = "#4ec9b0"
RED      = "#f48771"
YELLOW   = "#dcdcaa"
BLUE     = "#569cd6"
GREY     = "#808080"
MAGENTA  = "#c586c0"
THINK_BG = "#1a1a2e"
FINAL_BG = "#0f1f0f"

# ----- Agenten -------------------------------------------------------------
AGENTS = [
    {
        "name": "ZENTRALBANKER",
        "role": "Institutioneller Goldinvestor",
        "system": (
            "Du bist ein erfahrener Zentralbanker, der ueber Goldreserven entscheidet. "
            "Du analysierst Zinsen, Inflation und geopolitische Risiken. "
            "Antworte auf Deutsch in 4-6 Saetzen. "
            "Nenne klar: KAUFSIGNAL, VERKAUFSSIGNAL oder NEUTRAL."
        ),
        "user": (
            "Marktlage XAUUSD: Spot 2287, Fed 5.25%, CPI 3.2%, DXY 104.1 (-0.3%), "
            "Geopolitik Ukraine/Taiwan. Was ist deine Empfehlung?"
        ),
    },
    {
        "name": "MAKRO-ANALYST",
        "role": "Volkswirt / Edelmetalle",
        "system": (
            "Du bist Volkswirt mit Spezialisierung auf Edelmetalle. "
            "Du nutzt Korrelationen (Dollar, Realzinsen). Antworte auf Deutsch 4-6 Saetze. "
            "Nenne klar: KAUFSIGNAL, VERKAUFSSIGNAL oder NEUTRAL."
        ),
        "user": (
            "XAUUSD 2287, DXY -0.3%, Rate-Cut-Wahrscheinlichkeit 65% in 3 Monaten, "
            "Realzinsen 10J +1.8%. Wie ist deine Prognose?"
        ),
    },
    {
        "name": "TECHNIKER",
        "role": "Charttechniker",
        "system": (
            "Du bist Charttechniker (Trends, RSI, Volume). "
            "Antworte auf Deutsch 4-6 Saetze. "
            "Nenne klar: KAUFSIGNAL, VERKAUFSSIGNAL oder NEUTRAL."
        ),
        "user": (
            "XAUUSD: Spot 2287, 20-EMA 2285, RSI(14)=58, bullisches Doji, "
            "Widerstand 2300/2310, Stuetzung 2270-2280. Was siehst du?"
        ),
    },
    {
        "name": "ROHSTOFF-TRADER",
        "role": "Spotmarkt-Haendler",
        "system": (
            "Du bist Rohstoffhaendler am Goldmarkt (Angebot, Nachfrage, COT). "
            "Antworte auf Deutsch 4-6 Saetze. "
            "Nenne klar: KAUFSIGNAL, VERKAUFSSIGNAL oder NEUTRAL."
        ),
        "user": (
            "Asien: physische Nachfrage hoch (Indien-Hochzeiten), COT Commercials "
            "netto long +15.000, leichte Backwardation, WTI +2%. Wie positionierst du dich?"
        ),
    },
]


# ----- Ollama-Helfer -------------------------------------------------------

def check_ollama() -> tuple[bool, list[str]]:
    """True wenn Ollama erreichbar; gibt Modell-Liste zurueck."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=5) as resp:
            data = json.loads(resp.read())
            return True, [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return False, []


def stream_ollama(system: str, user: str, on_think, on_final, on_meta):
    """
    Streamt eine Antwort von Ollama via OpenAI-kompatible API.
    Trennt thinking (delta.reasoning_content + <think>-Tags) von final content.

    on_think(text): Token-Callback fuer Thinking-Phase
    on_final(text): Token-Callback fuer Final-Phase
    on_meta(dict):  Wird am Ende mit elapsed/tokens/etc. aufgerufen
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "temperature": 0.7,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT, data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    t0 = time.time()
    in_think_tag = False
    full_think = ""
    full_final = ""
    chunks = 0

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload_str = line[5:].strip()
                if payload_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                chunks += 1
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                # 1) Reasoning content (gpt-oss harmony channel)
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    full_think += reasoning
                    on_think(reasoning)

                # 2) Normal content - check fuer <think>-Tags (deepseek-r1, qwen3)
                content = delta.get("content")
                if content:
                    # Tag-basierter Reasoning-Modus
                    remaining = content
                    while remaining:
                        if in_think_tag:
                            end_idx = remaining.find("</think>")
                            if end_idx == -1:
                                full_think += remaining
                                on_think(remaining)
                                remaining = ""
                            else:
                                full_think += remaining[:end_idx]
                                on_think(remaining[:end_idx])
                                remaining = remaining[end_idx + 8:]
                                in_think_tag = False
                        else:
                            start_idx = remaining.find("<think>")
                            if start_idx == -1:
                                full_final += remaining
                                on_final(remaining)
                                remaining = ""
                            else:
                                if start_idx > 0:
                                    full_final += remaining[:start_idx]
                                    on_final(remaining[:start_idx])
                                remaining = remaining[start_idx + 7:]
                                in_think_tag = True

        elapsed = time.time() - t0
        on_meta({
            "elapsed": elapsed,
            "chunks": chunks,
            "think_chars": len(full_think),
            "final_chars": len(full_final),
        })
        return full_think, full_final

    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        on_meta({"error": f"HTTP {e.code}: {body_err[:200]}"})
        return "", ""
    except Exception as e:
        on_meta({"error": f"{type(e).__name__}: {e}"})
        return "", ""


# ----- GUI -----------------------------------------------------------------

class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MiroFish Dashboard - Streaming Edition")
        self.geometry("1280x860")
        self.configure(bg=BG)
        self.running = False
        self.current_agent_idx = 0

        self._build_ui()
        self._check_status()

    # ----- UI Aufbau -------------------------------------------------------

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(
            header, text="MIROFISH STREAMING DASHBOARD",
            bg=BG, fg=GOLD, font=("Consolas", 16, "bold")
        ).pack(side="left")

        tk.Label(
            header, text=f"  Modell: {MODEL}  (MoE)",
            bg=BG, fg=GREY, font=("Consolas", 10)
        ).pack(side="left", padx=(20, 0))

        self.status_lbl = tk.Label(
            header, text="  Status: pruefe...",
            bg=BG, fg=YELLOW, font=("Consolas", 10)
        )
        self.status_lbl.pack(side="left", padx=(20, 0))

        # Buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.run_btn = tk.Button(
            btn_frame, text="START SCHWARM-LAUF",
            bg=GOLD, fg=BG, font=("Consolas", 11, "bold"),
            relief="flat", padx=20, pady=6,
            command=self._start_run, cursor="hand2",
            activebackground=YELLOW,
        )
        self.run_btn.pack(side="left")

        tk.Button(
            btn_frame, text="ALLES LEEREN",
            bg=PANEL, fg=FG, font=("Consolas", 10),
            relief="flat", padx=14, pady=6,
            command=self._clear_all, cursor="hand2",
            activebackground="#3e3e42",
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_frame, text="STATUS-CHECK",
            bg=PANEL, fg=FG, font=("Consolas", 10),
            relief="flat", padx=14, pady=6,
            command=self._check_status, cursor="hand2",
            activebackground="#3e3e42",
        ).pack(side="left", padx=(8, 0))

        self.agent_progress_lbl = tk.Label(
            btn_frame, text="",
            bg=BG, fg=MAGENTA, font=("Consolas", 10, "bold")
        )
        self.agent_progress_lbl.pack(side="left", padx=(20, 0))

        # Hauptbereich - 3 Spalten
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # === Spalte 1: Thinking + Final + Log ===
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Thinking-Box
        tk.Label(
            left, text="  THINKING (Reasoning - laeuft live)",
            bg=BG, fg=MAGENTA, font=("Consolas", 9, "bold"),
            anchor="w"
        ).pack(fill="x")

        self.think_txt = scrolledtext.ScrolledText(
            left, bg=THINK_BG, fg="#a0a0c0",
            font=("Consolas", 9), relief="flat",
            padx=10, pady=8, wrap="word", height=11,
            insertbackground=FG,
        )
        self.think_txt.pack(fill="both", expand=False, pady=(2, 6))

        # Final-Box
        tk.Label(
            left, text="  FINAL (friert ein wenn fertig)",
            bg=BG, fg=GREEN, font=("Consolas", 9, "bold"),
            anchor="w"
        ).pack(fill="x")

        self.final_txt = scrolledtext.ScrolledText(
            left, bg=FINAL_BG, fg=FG,
            font=("Consolas", 10), relief="flat",
            padx=10, pady=8, wrap="word", height=10,
            insertbackground=FG,
        )
        self.final_txt.pack(fill="both", expand=False, pady=(2, 6))

        # Log-Box
        tk.Label(
            left, text="  EVENT-LOG",
            bg=BG, fg=GOLD, font=("Consolas", 9, "bold"),
            anchor="w"
        ).pack(fill="x")

        self.log_txt = scrolledtext.ScrolledText(
            left, bg=DEEP, fg=GREY,
            font=("Consolas", 8), relief="flat",
            padx=10, pady=6, wrap="word", height=8,
            insertbackground=FG,
        )
        self.log_txt.pack(fill="both", expand=True, pady=(2, 0))
        self.log_txt.tag_config("gold",  foreground=GOLD,  font=("Consolas", 8, "bold"))
        self.log_txt.tag_config("green", foreground=GREEN)
        self.log_txt.tag_config("red",   foreground=RED)
        self.log_txt.tag_config("blue",  foreground=BLUE)
        self.log_txt.tag_config("grey",  foreground=GREY)
        self.log_txt.tag_config("magenta", foreground=MAGENTA)

        # === Spalte 2: Ergebnis-Karte ===
        right = tk.Frame(main, bg=PANEL, width=380)
        right.pack(side="right", fill="y", padx=(6, 0))
        right.pack_propagate(False)

        tk.Label(
            right, text="  SCHWARM-ERGEBNIS",
            bg=PANEL, fg=GOLD, font=("Consolas", 10, "bold"),
            anchor="w"
        ).pack(fill="x", padx=4, pady=(8, 4))

        rf = tk.Frame(right, bg=PANEL, padx=14, pady=14)
        rf.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.direction_lbl = tk.Label(
            rf, text="-", bg=PANEL, fg=GREY,
            font=("Consolas", 32, "bold")
        )
        self.direction_lbl.pack(pady=(10, 6))

        self.confidence_lbl = tk.Label(
            rf, text="Konfidenz: -", bg=PANEL, fg=GREY,
            font=("Consolas", 13)
        )
        self.confidence_lbl.pack(pady=(0, 12))

        self.bar_canvas = tk.Canvas(
            rf, height=14, bg=DEEP, highlightthickness=0
        )
        self.bar_canvas.pack(fill="x", pady=(0, 14))
        self.bar_canvas.create_rectangle(0, 0, 0, 14, fill=GREY, outline="", tags="bar")

        tk.Label(
            rf, text="Reasoning-Zusammenfassung:",
            bg=PANEL, fg=GOLD, font=("Consolas", 9, "bold"), anchor="w"
        ).pack(fill="x")
        self.reason_box = tk.Text(
            rf, bg=DEEP, fg=FG, font=("Consolas", 9), relief="flat",
            height=4, padx=8, pady=8, wrap="word"
        )
        self.reason_box.pack(fill="x", pady=(2, 12))

        tk.Label(
            rf, text="Veto-Check (vs ML-Signal):",
            bg=PANEL, fg=GOLD, font=("Consolas", 9, "bold"), anchor="w"
        ).pack(fill="x")
        veto_frame = tk.Frame(rf, bg=PANEL)
        veto_frame.pack(fill="x", pady=(2, 12))
        self.veto_lbls = {}
        for action in ["BUY", "SELL", "HOLD"]:
            row = tk.Frame(veto_frame, bg=PANEL)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=f"ML={action:<5}",
                bg=PANEL, fg=FG, font=("Consolas", 9), width=10, anchor="w"
            ).pack(side="left")
            lbl = tk.Label(
                row, text="-", bg=PANEL, fg=GREY,
                font=("Consolas", 9, "bold"), anchor="w"
            )
            lbl.pack(side="left")
            self.veto_lbls[action] = lbl

        tk.Label(
            rf, text="Statistik:",
            bg=PANEL, fg=GOLD, font=("Consolas", 9, "bold"), anchor="w"
        ).pack(fill="x")
        self.stats_lbl = tk.Label(
            rf, text="-", bg=PANEL, fg=FG, font=("Consolas", 9),
            justify="left", anchor="w"
        )
        self.stats_lbl.pack(fill="x", pady=(2, 0))

    # ----- Helfer ---------------------------------------------------------

    def log(self, text: str, tag: str = ""):
        self.log_txt.insert("end", text, tag)
        self.log_txt.see("end")

    def think_append(self, text: str):
        self.think_txt.insert("end", text)
        self.think_txt.see("end")

    def final_append(self, text: str):
        self.final_txt.insert("end", text)
        self.final_txt.see("end")

    def _clear_all(self):
        self.think_txt.delete("1.0", "end")
        self.final_txt.delete("1.0", "end")
        self.log_txt.delete("1.0", "end")
        self._reset_result()
        self.agent_progress_lbl.config(text="")

    def _reset_result(self):
        self.direction_lbl.config(text="-", fg=GREY)
        self.confidence_lbl.config(text="Konfidenz: -", fg=GREY)
        self._draw_bar(0, GREY)
        self.reason_box.delete("1.0", "end")
        for lbl in self.veto_lbls.values():
            lbl.config(text="-", fg=GREY)
        self.stats_lbl.config(text="-")

    def _draw_bar(self, ratio: float, color: str):
        self.bar_canvas.update_idletasks()
        w = self.bar_canvas.winfo_width()
        self.bar_canvas.delete("bar")
        self.bar_canvas.create_rectangle(
            0, 0, int(w * ratio), 14, fill=color, outline="", tags="bar"
        )

    def _check_status(self):
        ok, models = check_ollama()
        if not ok:
            self.status_lbl.config(
                text="  Ollama OFFLINE - 'ollama serve' starten",
                fg=RED
            )
            return
        if any(MODEL in m for m in models):
            self.status_lbl.config(
                text=f"  Ollama OK, {MODEL} bereit",
                fg=GREEN
            )
        else:
            self.status_lbl.config(
                text=f"  Ollama OK, {MODEL} fehlt - 'ollama pull {MODEL}' laeuft?",
                fg=YELLOW
            )

    # ----- Run-Logik ------------------------------------------------------

    def _start_run(self):
        if self.running:
            return
        self.running = True
        self.run_btn.config(state="disabled", text="LAEUFT...", bg=GREY)
        self._clear_all()
        threading.Thread(target=self._run_swarm, daemon=True).start()

    def _ui(self, fn, *args):
        """Thread-safe UI-Update."""
        self.after(0, lambda: fn(*args))

    def _run_swarm(self):
        try:
            self._ui(self.log, "=" * 60 + "\n", "gold")
            self._ui(self.log, f"SCHWARM-LAUF gestartet  ({MODEL})\n", "gold")
            self._ui(self.log, "=" * 60 + "\n\n", "gold")

            ok, models = check_ollama()
            if not ok:
                self._ui(self.log, "FEHLER: Ollama nicht erreichbar.\n", "red")
                return
            if not any(MODEL in m for m in models):
                self._ui(self.log, f"FEHLER: {MODEL} nicht installiert.\n", "red")
                self._ui(self.log, f"Pulle mit:  ollama pull {MODEL}\n", "red")
                return

            responses = []
            timings = []

            for i, agent in enumerate(AGENTS, 1):
                self._ui(
                    self.agent_progress_lbl.config,
                    {"text": f"Agent {i}/{len(AGENTS)}: {agent['name']}"}
                )
                self._ui(self.log, f"\n--- Agent {i}/{len(AGENTS)}: {agent['name']} ---\n", "magenta")
                self._ui(self.log, f"    {agent['role']}\n", "grey")

                # Boxen vor jedem Agent leeren mit Header
                self._ui(self._add_agent_separator, agent["name"])

                meta_holder = {}

                def on_think(t):
                    self._ui(self.think_append, t)

                def on_final(t):
                    self._ui(self.final_append, t)

                def on_meta(m):
                    meta_holder.update(m)

                think_full, final_full = stream_ollama(
                    agent["system"], agent["user"],
                    on_think, on_final, on_meta
                )

                if "error" in meta_holder:
                    self._ui(self.log, f"  FEHLER: {meta_holder['error']}\n", "red")
                else:
                    elapsed = meta_holder.get("elapsed", 0)
                    chunks = meta_holder.get("chunks", 0)
                    tc = meta_holder.get("think_chars", 0)
                    fc = meta_holder.get("final_chars", 0)
                    timings.append(elapsed)
                    self._ui(
                        self.log,
                        f"  fertig in {elapsed:.1f}s  "
                        f"[chunks={chunks}, think={tc}c, final={fc}c]\n",
                        "blue"
                    )

                responses.append((agent["name"], final_full or think_full))
                self._ui(self.final_append, "\n\n")
                self._ui(self.think_append, "\n\n")

            # ----- Aggregation -----
            self._ui(self.log, "\n" + "=" * 60 + "\n", "gold")
            self._ui(self.log, "AGGREGATION & PARSER\n", "gold")
            self._ui(self.log, "=" * 60 + "\n", "gold")

            aggregated = "# XAUUSD Swarm Report\n\n"
            for name, text in responses:
                aggregated += f"## {name}\n{text}\n\n"

            direction, confidence, reasoning = parse_swarm_direction(aggregated)
            self._ui(self.log, f"\nDirection : {direction}\n", "blue")
            self._ui(self.log, f"Confidence: {confidence*100:.1f}%\n", "blue")

            self._ui(self._update_result, direction, confidence, reasoning, responses, timings)

        finally:
            self.running = False
            self._ui(
                self.run_btn.config,
                {"state": "normal", "text": "START SCHWARM-LAUF", "bg": GOLD}
            )
            self._ui(self.agent_progress_lbl.config, {"text": "fertig"})

    def _add_agent_separator(self, name: str):
        self.think_txt.insert("end", f"\n>>> {name} <<<\n", )
        self.final_txt.insert("end", f"\n>>> {name} <<<\n", )

    def _update_result(self, direction, confidence, reasoning, responses, timings):
        if direction == "BUY":
            arrow, color = "^ LONG", GREEN
        elif direction == "SELL":
            arrow, color = "v SHORT", RED
        else:
            arrow, color = "= NEUTRAL", YELLOW

        self.direction_lbl.config(text=arrow, fg=color)
        self.confidence_lbl.config(text=f"Konfidenz: {confidence*100:.1f}%", fg=color)
        self._draw_bar(confidence, color)

        self.reason_box.delete("1.0", "end")
        self.reason_box.insert("1.0", reasoning)

        for action, lbl in self.veto_lbls.items():
            if action == "HOLD":
                lbl.config(text="durchgewunken", fg=GREY)
            elif (action == "BUY" and direction == "SELL") or \
                 (action == "SELL" and direction == "BUY"):
                lbl.config(text="VETOED -> HOLD", fg=RED)
            else:
                lbl.config(text=f"BESTAETIGT ({direction})", fg=GREEN)

        success = sum(1 for _, t in responses if t)
        avg = sum(timings) / len(timings) if timings else 0
        total = sum(timings)
        chars = sum(len(t) for _, t in responses)
        stats = (
            f"Agenten erfolgreich : {success}/{len(responses)}\n"
            f"Avg Antwortzeit     : {avg:.1f}s\n"
            f"Gesamt LLM-Zeit     : {total:.1f}s\n"
            f"Antwort-Laenge      : {chars} Zeichen"
        )
        self.stats_lbl.config(text=stats)


# ----- tk-config workaround -----
def _config_kwargs(target, kwargs_dict):
    target.config(**kwargs_dict)


if __name__ == "__main__":
    Dashboard().mainloop()
