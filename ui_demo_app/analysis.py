"""Optional Gemini analysis client for the UI demo."""

from __future__ import annotations

import json
import urllib.request

from .config import DemoConfig
from .simulator import TrainingStats


SUMMARY_MARKER = "---ZUSAMMENFASSUNG---"


class GeminiAnalysisClient:
    def __init__(self, config: DemoConfig) -> None:
        self.config = config

    def analyze(self, stats: TrainingStats) -> str:
        if not self.config.llm_enabled:
            return "[dim]LLM-Analyse deaktiviert.[/dim]"
        if not self.config.gemini_api_key:
            return (
                "[yellow]GEMINI_API_KEY fehlt.[/yellow]\n"
                "Setze den Key als Umgebungsvariable, wenn die Demo eine "
                "KI-Auswertung erzeugen soll."
            )

        prompt = build_analysis_prompt(stats)
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 8192,
            },
        }
        headers = {"Content-Type": "application/json"}
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent?key={self.config.gemini_api_key}"
        )

        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(request, timeout=self.config.llm_timeout_sec) as response:
                result = json.loads(response.read().decode("utf-8"))
            full_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            self._write_report(full_text)
            summary = extract_summary(full_text)
            return (
                summary
                + f"\n\n[dim italic]Komplett-Analyse gespeichert: "
                f"{self.config.report_path}[/dim italic]"
            )
        except Exception as exc:  # pragma: no cover - network and provider dependent
            return f"[red]Fehler bei der Verbindung zu Google Gemini: {exc}[/red]"

    def _write_report(self, full_text: str) -> None:
        self.config.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.report_path.write_text(full_text, encoding="utf-8")


def build_analysis_prompt(stats: TrainingStats) -> str:
    return f"""
Du bist ein quantitativer Trading-KI Experte. Analysiere folgende Trainings-Metriken
eines Trading-Bots.
- Epochen: {stats.epochs}
- Win Rate: {stats.final_acc * 100:.1f}% (Best: {stats.best_acc * 100:.1f}%)
- Val Loss: {stats.final_loss:.4f} (Best: {stats.min_loss:.4f})
- Equity: Start 1000$, Ende ${stats.final_eq:.2f} (Peak: ${stats.best_eq:.2f})

AUFGABE:
1. Schreibe eine detaillierte Analyse wie ein Senior Quant Researcher.
2. Analysiere Architektur, Overfitting-Risiken, Drawdowns und konkrete naechste
   Experimente.
3. Trenne deine lange Analyse am Ende exakt mit dem Keyword
   "{SUMMARY_MARKER}" ab.
4. Schreibe unter das Keyword eine praegnante Zusammenfassung mit maximal
   vier Saetzen, die im UI angezeigt wird.
Antworte komplett auf Deutsch.
""".strip()


def extract_summary(full_text: str, max_chars: int = 500) -> str:
    if SUMMARY_MARKER in full_text:
        return full_text.split(SUMMARY_MARKER, 1)[1].strip()
    if len(full_text) <= max_chars:
        return full_text
    return full_text[:max_chars].rstrip() + "..."
