# Phase 17: Demo Trading Validation - Context

**Gathered:** 2026-05-28
**Status:** Ready for execution (plans already exist)
**Mode:** Auto-generated (discuss skipped — prior PLAN.md + RESEARCH.md already capture decisions)

<domain>
## Phase Boundary

Bot runs profitably on demo account, proving the system works. Demo stability hardening: broker keepalive, heartbeat logging, signal reasoning, trade auditability.

Requirements: DEMO-01, DEMO-02, DEMO-03, DEMO-04 (see REQUIREMENTS.md).
</domain>

<decisions>
## Implementation Decisions

All decisions captured in `17-01-PLAN.md`, `17-02-PLAN.md`, `17-03-PLAN.md`. Plans originally drafted as Phase 15 in earlier roadmap and renumbered to Phase 17 (frontmatter updated).

### Claude's Discretion
Implementation specifics within plan boundaries at Claude's discretion within acceptance criteria.
</decisions>

<canonical_refs>
## Canonical References

### Phase plans
- `.planning/phases/17-demo-trading-validation/17-01-PLAN.md`
- `.planning/phases/17-demo-trading-validation/17-02-PLAN.md`
- `.planning/phases/17-demo-trading-validation/17-03-PLAN.md`
- `.planning/phases/17-demo-trading-validation/17-RESEARCH.md`

### Project specs
- `.planning/REQUIREMENTS.md` — DEMO-01..DEMO-04
- `.planning/ROADMAP.md` — Phase 17 section
</canonical_refs>

<code_context>
## Existing Code Insights

- Integration points: `trading/trading_loop.py`, `trading/signal_generator.py`, `trading/monitors.py`
- Persistence: `database/models.py`, `database/repositories/stats_repo.py`
- Tests: `tests/test_demo_stability.py`
</code_context>

<specifics>
## Specific Ideas

Detailed in plan files. Key items: broker keepalive, heartbeat logging, signal reasoning dict (never None), continuous uptime proof.
</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped, prior plans + research are authoritative.
</deferred>

---

*Phase: 17-demo-trading-validation*
*Context gathered: 2026-05-28*
