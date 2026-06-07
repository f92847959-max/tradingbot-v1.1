"""Tests for the Dow Theory signal filter (Phase 14.1, Task 3).

Pure verdict core covered branch-by-branch; ``apply_dow_filter`` verified with
``evaluate_dow_buy_filter`` monkeypatched so gating/veto/annotation are
deterministic without invoking the Dow engine.
"""

from __future__ import annotations

import pandas as pd

import trading.signal_generator as sg
from trading.signal_generator import (
    _decide_from_dow_trend,
    apply_dow_filter,
    evaluate_dow_buy_filter,
)


# --- pure decision core ----------------------------------------------------


def test_down_trend_vetoes():
    decision, reason = _decide_from_dow_trend(0)
    assert decision == "veto"
    assert "DOWN" in reason


def test_up_trend_supports():
    assert _decide_from_dow_trend(2)[0] == "support"


def test_range_is_neutral():
    assert _decide_from_dow_trend(1)[0] == "neutral"


# --- apply_dow_filter gating / application ----------------------------------


def test_disabled_passes_through():
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_dow_filter(sig, pd.DataFrame(), enabled=False)
    assert out["action"] == "BUY"
    assert "dow_filter" not in out


def test_non_buy_passes_through():
    sig = {"action": "SELL", "confidence": 0.7}
    out = apply_dow_filter(sig, pd.DataFrame(), enabled=True)
    assert out["action"] == "SELL"
    assert "dow_filter" not in out


def test_none_signal_passes_through():
    assert apply_dow_filter(None, pd.DataFrame(), enabled=True) is None


def test_veto_converts_buy_to_hold(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_dow_buy_filter", lambda df: ("veto", "down trend"))
    sig = {"action": "BUY", "confidence": 0.7, "reasoning": "base"}
    out = apply_dow_filter(sig, pd.DataFrame(), enabled=True)
    assert out["action"] == "HOLD"
    assert out["dow_vetoed_action"] == "BUY"
    assert out["dow_filter"]["decision"] == "veto"
    assert "Dow veto" in out["reasoning"]
    assert sig["action"] == "BUY"  # original not mutated
    assert "dow_filter" not in sig


def test_support_keeps_buy(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_dow_buy_filter", lambda df: ("support", "up trend"))
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_dow_filter(sig, pd.DataFrame(), enabled=True)
    assert out["action"] == "BUY"
    assert out["dow_filter"]["decision"] == "support"
    assert "Dow support" in out["reasoning"]


def test_neutral_keeps_buy_without_note(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_dow_buy_filter", lambda df: ("neutral", "range"))
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_dow_filter(sig, pd.DataFrame(), enabled=True)
    assert out["action"] == "BUY"
    assert out["dow_filter"]["decision"] == "neutral"
    assert "reasoning" not in out


# --- real detection path smoke test ----------------------------------------


def test_evaluate_is_graceful_on_degenerate_data():
    decision, _reason = evaluate_dow_buy_filter(pd.DataFrame({"close": [1.0, 2.0, 3.0]}))
    assert decision in ("neutral", "support", "veto")
