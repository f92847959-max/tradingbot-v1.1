"""Tests for the Elliott Wave signal filter (Phase 14-03, EWT-04).

The decision core (``_decide_from_wave_context``) is pure and covered branch by
branch.  ``apply_ew_filter`` is tested with ``evaluate_ew_buy_filter``
monkeypatched so the gating/veto/annotation behaviour is verified
deterministically without invoking the Elliott Wave engine.  A final smoke test
exercises the real detection path on degenerate data (must stay graceful).
"""

from __future__ import annotations

import pandas as pd

import trading.signal_generator as sg
from trading.signal_generator import (
    _decide_from_wave_context,
    apply_ew_filter,
    evaluate_ew_buy_filter,
)

VETO_AT = 0.8


# --- pure decision core ----------------------------------------------------


def test_no_count_is_neutral():
    assert _decide_from_wave_context("NONE", False, 0, 0.0, VETO_AT)[0] == "neutral"


def test_motive_wave3_high_completion_vetoes():
    decision, reason = _decide_from_wave_context("IMPULSE", True, 3, 0.9, VETO_AT)
    assert decision == "veto"
    assert "W4" in reason


def test_motive_wave3_low_completion_is_neutral():
    assert _decide_from_wave_context("IMPULSE", True, 3, 0.5, VETO_AT)[0] == "neutral"


def test_motive_wave5_high_completion_vetoes():
    assert _decide_from_wave_context("IMPULSE", True, 5, 0.95, VETO_AT)[0] == "veto"


def test_motive_wave2_supports():
    assert _decide_from_wave_context("IMPULSE", True, 2, 0.0, VETO_AT)[0] == "support"


def test_motive_wave4_supports_diagonal():
    assert _decide_from_wave_context("DIAGONAL", True, 4, 0.1, VETO_AT)[0] == "support"


def test_corrective_wave_a_vetoes():
    assert _decide_from_wave_context("ZIGZAG", False, 1, 0.0, VETO_AT)[0] == "veto"


def test_corrective_wave_c_is_neutral():
    assert _decide_from_wave_context("FLAT", False, 3, 0.0, VETO_AT)[0] == "neutral"


# --- apply_ew_filter gating / application ----------------------------------


def test_disabled_passes_through_untouched():
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_ew_filter(sig, pd.DataFrame(), enabled=False, veto_completion=VETO_AT)
    assert out["action"] == "BUY"
    assert "ew_filter" not in out


def test_non_buy_passes_through():
    sig = {"action": "SELL", "confidence": 0.7}
    out = apply_ew_filter(sig, pd.DataFrame(), enabled=True, veto_completion=VETO_AT)
    assert out["action"] == "SELL"
    assert "ew_filter" not in out


def test_none_signal_passes_through():
    assert apply_ew_filter(None, pd.DataFrame(), enabled=True, veto_completion=VETO_AT) is None


def test_veto_converts_buy_to_hold(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_ew_buy_filter", lambda df, vc: ("veto", "test reason"))
    sig = {"action": "BUY", "confidence": 0.7, "reasoning": "base"}
    out = apply_ew_filter(sig, pd.DataFrame(), enabled=True, veto_completion=VETO_AT)
    assert out["action"] == "HOLD"
    assert out["ew_vetoed_action"] == "BUY"
    assert out["ew_filter"]["decision"] == "veto"
    assert "EW veto" in out["reasoning"]
    # original signal must not be mutated
    assert sig["action"] == "BUY"
    assert "ew_filter" not in sig


def test_support_keeps_buy(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_ew_buy_filter", lambda df, vc: ("support", "W3 starting"))
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_ew_filter(sig, pd.DataFrame(), enabled=True, veto_completion=VETO_AT)
    assert out["action"] == "BUY"
    assert out["ew_filter"]["decision"] == "support"
    assert "EW support" in out["reasoning"]


def test_neutral_keeps_buy_without_reasoning_note(monkeypatch):
    monkeypatch.setattr(sg, "evaluate_ew_buy_filter", lambda df, vc: ("neutral", "no count"))
    sig = {"action": "BUY", "confidence": 0.7}
    out = apply_ew_filter(sig, pd.DataFrame(), enabled=True, veto_completion=VETO_AT)
    assert out["action"] == "BUY"
    assert out["ew_filter"]["decision"] == "neutral"
    assert "reasoning" not in out


# --- real detection path smoke test ----------------------------------------


def test_evaluate_is_graceful_on_degenerate_data():
    # Too few rows -> extractor returns zeros -> NONE -> neutral, never raises.
    decision, _reason = evaluate_ew_buy_filter(pd.DataFrame({"close": [1.0, 2.0, 3.0]}), VETO_AT)
    assert decision in ("neutral", "support", "veto")
