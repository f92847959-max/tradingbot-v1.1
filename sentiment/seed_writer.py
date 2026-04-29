"""Write MiroFish seed context from recent sentiment records."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_sentiment_seed(
    records: list[Any],
    path: str | Path = "mirofish_seeds/news_sentiment.md",
    now: datetime | None = None,
) -> None:
    """Write a compact Markdown seed for MiroFish market context."""
    now = now or datetime.now(timezone.utc)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Sentiment-Ueberblick",
        "",
        f"Aktualisiert: {now.astimezone(timezone.utc).isoformat()}",
        "",
        "## Marktlage",
    ]

    if not records:
        lines.append("Keine aktuellen Gold-News im Sentiment-Fenster.")
    else:
        avg = sum(float(_field(r, "sentiment_score", 0.0) or 0.0) for r in records) / len(records)
        bias = "positiv" if avg > 0.1 else "negativ" if avg < -0.1 else "neutral"
        lines.append(f"Der aktuelle News-Bias ist {bias} ({avg:.3f}) aus {len(records)} Artikeln.")
        lines.extend(["", "## Relevante Schlagzeilen"])
        for record in records[:10]:
            score = float(_field(record, "sentiment_score", 0.0) or 0.0)
            source = _field(record, "source", "unknown")
            headline = _field(record, "headline", "")
            lines.append(f"- [{source}] {headline} ({score:+.3f})")

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)
