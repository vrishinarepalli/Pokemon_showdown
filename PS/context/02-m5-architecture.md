# 02 — M5 LLM Agent Architecture

File: `bot/agents/llm_agent.py`. The design principle: **the LLM never picks raw
moves; it only nudges an already-safe heuristic decision.** This keeps blunders
impossible and tokens low.

## Decision pipeline (per turn, in order)
1. **Heuristic floor** — a competent rules engine can always answer alone. With
   `PS_LLM_OFF=1` the agent runs floor-only (no API calls) — this is the baseline
   we benchmark against.
2. **Obvious-KO fast-path** — if we can KO and move first, just do it. No LLM.
3. **Strategic-fork gate** — only positions that are genuinely a *fork* go to the
   LLM. Non-forks return the heuristic choice. `_fork_type()` classifies:
   - `1` flee danger — opp can KO us **and** we have a safe switch
   - `2` setup window — we have setup **and** opp barely hits us (`opp_hit<25`) **and** no strong attack (`our_best<70`)
   - `3` walled — we can't hit hard (`our_best<25`) **and** (safe switch or stall available)
   - `4` stall window — we have stall **and** opp hits softly (`opp_hit<30`) **and** weak attack (`our_best<45`)
4. **Heuristic anchor** — the heuristic's preferred move is computed and passed to
   the LLM as the default.
5. **Strategy-only override** — the LLM's answer is accepted **only** if it pulls
   toward `switch` / `setup` / `stall`. If it picks a different *attack* than the
   anchor, we reject it and keep the anchor (the LLM doesn't get to second-guess
   damage math — that's what the heuristic is for).

## Abstract actions
After the override, the LLM's effective decision collapses to one of four
abstract actions: **`anchor` / `switch` / `setup` / `stall`**. This abstraction
is what the decision cache memoizes — see [03-decision-cache.md](03-decision-cache.md).

## Counters (exposed for benchmarking)
`n_llm` (LLM forks), `n_cache` (cache hits), `n_gate` (gated to heuristic),
`n_fastpath` (obvious KO), `n_fallback` (LLM errored/invalid → heuristic).

## Candidate structure
`choose_move` builds `candidates` = list of `{kind: "move"|"switch", order, info}`.
`battle_summary(...)` produces the state dict the LLM and signature read from
(our/opp active hp%, remaining counts, who-moves-first, etc.).
