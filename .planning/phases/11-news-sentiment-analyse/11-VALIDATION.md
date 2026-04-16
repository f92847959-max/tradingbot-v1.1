---
phase: 11
slug: news-sentiment-analyse
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| TBD     | TBD  | TBD  | SENT-01..05 | unit/integration | `pytest tests/sentiment/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — populated by gsd-planner during planning.*

---

## Wave 0 Requirements

- [ ] `tests/sentiment/__init__.py` — package marker
- [ ] `tests/sentiment/conftest.py` — shared fixtures (mock RSS feeds, sample news items, fixture sentiment models)
- [ ] `tests/sentiment/fixtures/` — sample RSS XML, sample articles for deterministic NLP tests
- [ ] `pip install feedparser transformers torch vaderSentiment` — if not in requirements.txt

*Planner expands this list with concrete stub files per SENT requirement.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live RSS feed reachability | SENT-01 | External network dependency, flaky in CI | Run `python -m sentiment.feeds.fetch_all --once` and inspect logs for HTTP 200 from each source |
| Sentiment-Score plausibility on real news | SENT-03 | Subjective semantic check | Spot-check 10 recent gold news headlines, verify scores match human intuition (-1.0 to +1.0) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
