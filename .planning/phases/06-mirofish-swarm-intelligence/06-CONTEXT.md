# Phase 6: MiroFish Swarm Intelligence Integration - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate MiroFish (github.com/666ghj/MiroFish) multi-agent prediction engine as an additional signal source alongside the existing XGBoost/LightGBM ensemble. MiroFish provides a "swarm intelligence" perspective on gold markets by simulating economic/macro experts who discuss and reach consensus.

**What exists:**
- XGBoost + LightGBM ensemble in `ai_engine/prediction/ensemble.py` (weighted voting)
- Signal generation in `trading/signal_generator.py` via `AIPredictor`
- Signal dict: `{action, confidence, trade_score, entry_price, stop_loss, take_profit, reasoning}`
- Existing MiroFish Git repo with a working version

**What this phase adds:**
- MiroFish cloned and running locally (Flask backend on :5001)
- Ollama as local LLM (no OpenAI API — open-source only)
- Zep Cloud for knowledge graph
- MiroFish client integrated into signal pipeline as veto/supplementary signal
- 10 economic agents simulating gold market scenarios
- API cost limiter replaced by Ollama resource management

</domain>

<decisions>
## Implementation Decisions

### Agent Profile Design
- **D-01:** 10 agents, all focused on economics/macro — NO technical analysis (ML ensemble covers that)
- **D-02:** Agents discuss sequentially — each reacts to what previous agents said (multi-round simulation)
- **D-03:** Discussion runs until consensus is reached (not fixed number of rounds)
- **D-04:** Agent roles: Claude's discretion — pick 10 optimal economic/macro perspectives for gold trading (e.g., Fed analyst, inflation expert, dollar analyst, geopolitics, commodities, bond market, emerging markets, central bank policy, energy/oil correlation, macro sentiment)
- **D-05:** Agents discuss in German

### Ensemble Integration Strategy
- **D-06:** MiroFish has **veto power** — can block a trade signal if swarm disagrees, but cannot initiate trades on its own
- **D-07:** MiroFish is a **secondary signal** (Nebensignal) — ML ensemble remains dominant (70-80%)
- **D-08:** If MiroFish agrees with ML signal → trade proceeds normally
- **D-09:** If MiroFish vetoes → trade is blocked, logged with reason

### Simulation Trigger & Timing
- **D-10:** MiroFish runs **in parallel** with ML ensemble but on a **less frequent schedule** (e.g., every 5 minutes)
- **D-11:** Results are **cached** — when ML ensemble produces a signal, the latest MiroFish assessment is used for veto check
- **D-12:** **No OpenAI API costs** — runs entirely on Ollama with local open-source model (hardware: GTX 1650 4GB VRAM, 16GB RAM)

### LLM Configuration
- **D-13:** Use **Ollama** as local LLM provider (not OpenAI API)
- **D-14:** Model selection: Claude's discretion — pick best model that fits GTX 1650 4GB VRAM (e.g., gemma3:4b, phi-4-mini, or similar)
- **D-15:** Original MIRO-06 cost limiter adapts to Ollama resource management (GPU/RAM limits instead of token budget)

### Fallback Behavior
- **D-16:** If MiroFish unavailable (Ollama down, Flask crashed, timeout) → **trade without it** — ML ensemble continues normally
- **D-17:** **One warning notification** when MiroFish goes offline, no repeated warnings per tick
- **D-18:** Graceful degradation — bot never stops trading because MiroFish is down

### Claude's Discretion
- Specific 10 agent role names and personas
- Ollama model choice for 4GB VRAM constraint
- MiroFish cache TTL (how long a simulation result stays valid)
- Simulation timeout thresholds
- How veto decision is logged and displayed
- MiroFish Flask backend startup integration

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### MiroFish
- `https://github.com/666ghj/MiroFish` — MiroFish repo (to be cloned), contains Flask backend, agent simulation framework

### Existing Signal Pipeline
- `trading/signal_generator.py` — Where MiroFish veto integrates
- `ai_engine/prediction/ensemble.py` — Existing ML ensemble (weighted voting)
- `ai_engine/prediction/predictor.py` — AIPredictor that orchestrates prediction

### Configuration
- `.env` — Will need: ZEP_API_KEY, OLLAMA_BASE_URL, MIROFISH_ENABLED
- `config/settings.py` — Trading settings, will need MiroFish toggle

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `EnsemblePredictor` in `ensemble.py`: Has weighted voting, timeframe weights, ACTION_MAP — MiroFish score fits as additional input
- `SignalGeneratorMixin._generate_signal()`: Clean entry point for adding MiroFish veto check after ML signal
- `shared/exceptions.py`: Error classification framework — can classify MiroFish errors
- Notification system: `notifications/` module already handles warnings

### Established Patterns
- Lazy loading: `AIPredictor` is lazily imported — MiroFish client should follow same pattern
- Async everywhere: Trading loop is async — MiroFish client must be async
- Settings-driven: Features toggled via `config/settings.py` — MiroFish needs an enable/disable toggle

### Integration Points
- `signal_generator.py:41-45`: After `self._ai_predictor.predict()` returns, add MiroFish veto check
- `trading_loop.py:113-115`: Signal filtering — MiroFish veto could happen here or in signal_generator
- `config/settings.py`: Add MiroFish-related settings (enabled, Ollama URL, cache TTL)

</code_context>

<specifics>
## Specific Ideas

- MiroFish already has a working Git repo — clone and adapt, don't rebuild from scratch
- User cannot program — all setup/configuration must be automated or scripted
- Agents must focus purely on economic/fundamental factors (inflation, central banks, geopolitics, dollar strength, bond yields, commodities, sentiment) — technical analysis is handled by ML
- Sequential discussion with reactions creates richer analysis than parallel independent opinions
- Running until consensus means variable-length simulations — need timeout as safety net

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---
*Phase: 06-mirofish-swarm-intelligence*
*Context gathered: 2026-03-24 via discuss-phase*
