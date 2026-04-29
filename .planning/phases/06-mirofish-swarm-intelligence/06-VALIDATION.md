---
phase: 6
slug: mirofish-swarm-intelligence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/test_mirofish_client.py -x --tb=short` |
| **Full suite command** | `python -m pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_mirofish_client.py -x --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -x --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | MIRO-01 | integration (skipif) | `pytest tests/test_mirofish_client.py::test_health_check -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | MIRO-02 | integration (skipif) | `pytest tests/test_mirofish_client.py::test_graph_state_persistence -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | MIRO-03 | unit | `pytest tests/test_mirofish_client.py::test_env_config -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | MIRO-04 | integration (skipif) | `pytest tests/test_mirofish_client.py::test_simulation_produces_report -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | MIRO-05 | unit | `pytest tests/test_mirofish_client.py::test_veto_buy_blocked_by_sell -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | MIRO-05 | unit | `pytest tests/test_mirofish_client.py::test_veto_sell_blocked_by_buy -x` | ❌ W0 | ⬜ pending |
| 06-03-03 | 03 | 2 | MIRO-05 | unit | `pytest tests/test_mirofish_client.py::test_veto_neutral_passthrough -x` | ❌ W0 | ⬜ pending |
| 06-03-04 | 03 | 2 | MIRO-05 | unit | `pytest tests/test_mirofish_client.py::test_disabled_passthrough -x` | ❌ W0 | ⬜ pending |
| 06-03-05 | 03 | 2 | MIRO-05 | unit | `pytest tests/test_mirofish_client.py::test_no_cache_passthrough -x` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 2 | MIRO-06 | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_max_sims -x` | ❌ W0 | ⬜ pending |
| 06-04-02 | 04 | 2 | MIRO-06 | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_token_budget -x` | ❌ W0 | ⬜ pending |
| 06-04-03 | 04 | 2 | MIRO-06 | unit | `pytest tests/test_mirofish_client.py::test_cost_limiter_daily_reset -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_mirofish_client.py` — stubs for MIRO-01 through MIRO-06
- [ ] Fixture: mock httpx responses for unit tests (use `respx` or `pytest-httpx`)
- [ ] Integration tests decorated with `@pytest.mark.skipif(not MIROFISH_AVAILABLE, reason="MiroFish not running")`
- [ ] Fixture: temporary `logs/mirofish_cost.json` for cost limiter tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MiroFish Flask starts on :5001 | MIRO-01 | Requires cloned repo + uv sync | `cd mirofish/backend && uv run python run.py`, verify http://localhost:5001/health returns 200 |
| Zep Cloud graph builds from seeds | MIRO-02 | Requires Zep Cloud API key | POST /api/graph/ontology/generate with seed files, verify graph_id returned |
| Full simulation with 10 agents | MIRO-04 | Requires MiroFish + OpenAI API + Zep | Trigger full simulation, verify report contains agent discussion output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
