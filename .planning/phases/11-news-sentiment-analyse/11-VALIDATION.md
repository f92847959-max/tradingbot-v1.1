---
phase: 11
slug: news-sentiment-analyse
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-16
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/sentiment/ -x --tb=short -q` |
| **Full suite command** | `pytest tests/sentiment/ --cov=sentiment --cov-report=term-missing` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/sentiment/ -x --tb=short -q`
- **After every plan wave:** Run `pytest tests/sentiment/ --cov=sentiment --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-02-01 | 11-02 | 2 | SENT-01 | unit | `python -m pytest tests/sentiment/test_news_fetcher.py -q` | yes | green |
| 11-02-02 | 11-02 | 2 | SENT-02 | unit | `python -m pytest tests/sentiment/test_sentiment_analyzer.py -q` | yes | green |
| 11-02-03 | 11-02 | 2 | SENT-03 | unit | `python -m pytest tests/sentiment/test_sentiment_aggregator.py -q` | yes | green |
| 11-02-04 | 11-02 | 2 | SENT-05 | integration | `python -m pytest tests/sentiment/test_sentiment_repository.py -q` | yes | green |
| 11-03-01 | 11-03 | 3 | SENT-04 | unit | `python -m pytest tests/sentiment/test_sentiment_features.py -q` | yes | green |
| 11-03-02 | 11-03 | 3 | SENT-04 | integration | `python -m pytest tests/sentiment/test_feature_engineer_sentiment.py -q` | yes | green |
| 11-03-03 | 11-03 | 3 | SENT-01 | integration | `python -m pytest tests/sentiment/test_sentiment_service.py -q` | yes | green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — populated by gsd-planner during planning.*

---

## Wave 0 Requirements

- [x] `tests/sentiment/__init__.py` — package marker
- [x] `tests/sentiment/conftest.py` — shared fixtures (mock RSS feeds, sample news items, fixture sentiment data)
- [x] `tests/sentiment/fixtures/` — sample RSS XML, sample articles for deterministic NLP tests
- [x] `feedparser` / `vaderSentiment` declared in requirements; deterministic fallbacks keep tests runnable when not installed

*Planner expands this list with concrete stub files per SENT requirement.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live RSS feed reachability | SENT-01 | External network dependency, flaky in CI | Run `python -m sentiment.feeds.fetch_all --once` and inspect logs for HTTP 200 from each source |
| Sentiment-Score plausibility on real news | SENT-03 | Subjective semantic check | Spot-check 10 recent gold news headlines, verify scores match human intuition (-1.0 to +1.0) |

---

## Validation Sign-Off

- [x] All tasks have automated verification
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 placeholders replaced by executable tests
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete
