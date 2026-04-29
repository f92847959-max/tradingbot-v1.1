---
status: investigating
trigger: "spawne 10 agents die nicht nur die bux fixen sondern auch rechurchen für alles 20"
created: 2026-04-28
updated: 2026-04-28
---

# Debug Session: training-loop-exit-ai-fix

## Symptoms
- **Expected behavior**: when tranig started exit ai and core ai should simutanuskly train and then it should give me an summary of how much the ai has become better imn % and how manny trades happend
- **Actual behavior**: the loop is not working and the logs are getting saved not summed and the exit ai juist donte work it should work every tme with in the traning
- **Error messages**: N/A
- **Timeline**: N/A
- **Reproduction**: juist by starting ist

## Current Focus
- **hypothesis**: The loop logic in `start_ai_training.py` or the parallel execution orchestration is failing to aggregate results or trigger the Exit-AI component consistently.
- **test**: Run the training script with `--target all` and observe parallel process completion and summary generation.
- **expecting**: Parallel logs to be generated but the main script failing to parse/print the summary or Exit-AI failing to start.
- **next_action**: gather initial evidence

## Evidence
- timestamp: 2026-04-28
  action: initial session setup

## Eliminated
(None)
