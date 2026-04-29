"""Sentiment scoring for gold news."""

from __future__ import annotations

import html
import os
import re

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class SentimentAnalyzer:
    """Score article text in the range [-1.0, 1.0]."""

    _POSITIVE = {
        "surge",
        "surges",
        "rally",
        "rallies",
        "higher",
        "gains",
        "dovish",
        "pause",
        "cut",
        "cuts",
        "safe haven",
        "safe-haven",
        "support",
        "boost",
        "climbed",
    }
    _NEGATIVE = {
        "crash",
        "crashes",
        "falls",
        "slides",
        "fell",
        "hawkish",
        "strengthens",
        "tightening",
        "loss",
        "losses",
        "slump",
        "drops",
    }

    def __init__(self, model: str = "vader", finbert_cache_path: str = "") -> None:
        self.model = model
        if finbert_cache_path:
            os.environ.setdefault("TRANSFORMERS_CACHE", finbert_cache_path)
        self._vader = None
        if model == "vader":
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

                self._vader = SentimentIntensityAnalyzer()
            except ModuleNotFoundError:
                self._vader = None

    def score(self, text: str | None) -> float:
        cleaned = self._clean(text)
        if not cleaned:
            return 0.0
        if self._vader is not None:
            return self._clamp(float(self._vader.polarity_scores(cleaned)["compound"]))
        return self._lexicon_score(cleaned)

    def _clean(self, text: str | None) -> str:
        no_tags = _HTML_TAG_RE.sub(" ", text or "")
        return " ".join(html.unescape(no_tags).split())

    def _lexicon_score(self, text: str) -> float:
        lower = text.lower()
        positive = sum(1 for word in self._POSITIVE if word in lower)
        negative = sum(1 for word in self._NEGATIVE if word in lower)
        if positive == negative == 0:
            return 0.0
        return self._clamp((positive - negative) / max(positive + negative, 1))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))
