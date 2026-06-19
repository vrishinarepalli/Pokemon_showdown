# Project Status — Pokémon Showdown Bot

_Last updated: 2026-06-19_

## TL;DR
- **M4 (formula bot) is closed at ~52% vs M3.** The ≥60% target is not reachable by
  this architecture — proven by ~30 high-N A/B runs.
- **M5 pivoted to an LLM-with-tools agentic bot (Groq).** The infrastructure works
  (fast, cheap, grounded), but **LLM strategic deviation does not beat M4** — the
  heuristic floor (~50%) beats every LLM variant tested so far.
- Key insight: M4 (an expectimax) *punishes* the switches/setups the LLM adds. The
  LLM's edge is for opponents that *reward* strategy (humans → M6), not M4.

---

## M4 — ExpectimaxAgent vs HeuristicAgent (M3) — CLOSED
Depth-1 expectimax + hand-crafted value function vs a max-damage heuristic (M3).

| Lever tried this cycle | Result vs M3 (N≥3000) |
|---|---|
| Tuned baseline | **52.0%** |
| Accurate damage model (honest rolls, roll-based KO prob, multi-hit, fixed-damage) | 51.9% (neutral) |
| Deeper 2-ply lookahead (0.6) | 47.1% (regressed) |
| Wall-mode status/stall exploit | 52.7% (neutral) |

**Conclusion:** the ~52% ceiling is the *decision policy* (myopic value function),
not damage accuracy or search depth. The accurate damage model was kept (it's correct
and is the substrate for M5's tools); the other levers are env-gated and default-off.
Note: `src/damage_calculator.py` + `DataManager` are dead code (empty data files,
nothing calls them); the live engine is `bot/agents/expectimax.py:_damage_fraction`.

---

## M5 — LLM-with-tools agentic bot (IN PROGRESS)
**Goal:** beat M4 (the ~52% ExpectimaxAgent). **Provider:** Groq (free tier).
**Design principle (user-driven):** *code does the heavy lifting; the LLM only judges.*

### Architecture
1. **Heuristic owns all attack selection** (max KO-chance, then damage) → ~50% floor.
2. **Obvious-KO fast-path:** if a move KOs (≥0.9) and we move first → take it, no LLM.
3. **Strategic-fork gate:** call the LLM *only* on (1) danger + a safe switch,
   (2) a safe setup window, (3) a walled/weak-damage matchup, (4) a stall window.
   Fires on ~16–23% of turns.
4. **Anchor:** the prompt tells the LLM the max-damage pick; deviate only if clearly better.
5. **Strategy-only override:** the LLM may only pull us toward a *switch / setup / status*;
   if it picks a different plain attack, we defer to the damage-maximizer.

### Results vs M4
| Config | Win rate | Notes |
|---|---|---|
| Heuristic only (`PS_LLM_OFF=1`) | **50%** (N=20) | tools/harness validated; the floor |
| Per-turn 8B LLM (every turn) | ~20–30% | LLM underperforms a damage-maximizer |
| Gated + strategy-only, **8B** on forks | 42.5% (N=40) | below floor |
| Gated + strategy-only, **70B** on forks | **30%** (N=40) | *worse* — bigger model deviates more |

**Finding:** LLM strategic deviation is net-negative *against M4*, and more capability
makes it worse. M4 punishes tempo loss (switches/setups), so the situations where the
LLM wants to deviate are exactly where deviating loses. This says little about M6 (human
opponents *do* reward strategy) — it says M4 is the wrong yardstick for the LLM's edge.

### Cost / performance (Groq, gated)
- ~4.5–12s/battle, ~290 tokens/call, ~940 tokens/battle, 0 fallbacks.
- Free-tier token/day caps mean **no 500-game LLM eval/day**; iterate at N=40–50.
- 70B free tier ≈ 100K tokens/day (~10 full-LLM battles, or ~50 gated). 8B much higher.

### Files (M5)
- `bot/llm/client.py` — Groq client (auto-loads `.env`, tracks tokens/latency).
- `bot/llm/tools.py` — `analyze_move` / `analyze_switch` / `battle_summary` (wrap the engine).
- `bot/agents/llm_agent.py` — `LLMAgent` (gate + anchor + override + fast-path).
- `bench_llm.py` — eval harness (`python bench_llm.py --n-battles N`; `PS_LLM_OFF=1` = heuristic only).
- `.env` (gitignored) holds `GROQ_API_KEY` + `GROQ_MODEL`.

---

## Open questions / next steps
- **Re-evaluate the M5 yardstick.** Beating M4 may be the wrong goal: M4 doesn't reward
  the strategy the LLM adds. Consider evaluating vs opponents that reward strategy, or
  vs scripted archetype bots (stall / hyper-offense / setup-sweep) that are more human-like.
- **LLM-as-strategic-director** (deferred option): engine plays every turn; LLM sets a
  game-plan (archetype + win condition) every few turns rather than picking moves.
- **M6:** vs real humans on the Showdown ladder; study strategy *archetypes* (not individuals),
  seed standard strategies, refine archetype priors from observed play (noise-robust by aggregation).
- Scripted archetype bots for diverse training/eval data (M3/M4 only play smart-max-damage).

## How to run
```bash
# Start the PS server (separate terminal, from repo root):
node node_modules/pokemon-showdown/pokemon-showdown start --no-security
# M4 benchmark (formula bot vs M3):
python benchmark.py --n-battles 500 --no-logs
# M5 eval (LLM vs M4); needs GROQ_API_KEY in .env:
python bench_llm.py --n-battles 40
PS_LLM_OFF=1 python bench_llm.py --n-battles 40   # heuristic-only baseline
```
