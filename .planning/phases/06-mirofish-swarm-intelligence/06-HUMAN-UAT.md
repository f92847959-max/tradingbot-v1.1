---
status: partial
phase: 06-mirofish-swarm-intelligence
source: [06-VERIFICATION.md]
started: "2026-03-26T22:10:00.000Z"
updated: "2026-03-26T22:10:00.000Z"
---

## Current Test

[awaiting human testing]

## Tests

### 1. MiroFish Backend startup
expected: `python scripts/start_mirofish.py start` launches Flask on localhost:5001 with health-check success
result: [pending]

### 2. Zep Cloud connectivity
expected: ZEP_API_KEY connects to Zep Cloud, graph creation succeeds with gold market ontology
result: [pending]

### 3. OpenAI API integration
expected: gpt-4o-mini simulation runs via MiroFish, returns SwarmAssessment with direction/confidence/reasoning
result: [pending]

### 4. Cost tracking accuracy
expected: After 2-3 simulations, daily cost JSON file updates correctly with token counts
result: [pending]

### 5. RAM usage during simulation
expected: Memory stays under 4 GB during MiroFish simulation (16 GB system total)
result: [pending]

### 6. End-to-end signal flow with MiroFish
expected: With mirofish_enabled=True, trading signal generation includes MiroFish veto check
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
