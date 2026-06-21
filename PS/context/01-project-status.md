# 01 — Project Status

## Where we are
- **M4 (formula/expectimax bot)** capped at **~52% vs M3**. Three tuning levers
  all came out neutral — the formula approach is tapped out.
- **M5 (current): LLM-with-tools agentic bot.** An LLM (Groq) is consulted only
  on strategic forks; a heuristic engine handles everything else and anchors the
  LLM so it can't blunder. See [02-m5-architecture.md](02-m5-architecture.md).
- **M6 (next):** play real humans + adapt to opponent archetypes.

## The yardstick change (important)
We stopped benchmarking against M4 and switched to **poke-env's
`SimpleHeuristicsPlayer`** — a competent built-in bot that switches and uses
hazards. M4 is basically a max-damage bot; it doesn't reward strategy, so it was
the wrong ruler for an agent whose whole edge *is* strategy.

## The "sign flip" win
- **vs M4:** the LLM was *below* the heuristic floor (strategy wasn't rewarded).
- **vs SimpleHeuristics:** floor **51.7%** (N=60) vs LLM **55.0%** (N=40) — the
  first time the LLM beat its own floor. This is the core evidence that the LLM's
  strategic edge is real and only visible against an opponent that punishes bad
  positioning.

## Variance discipline
- Win-rate swings 47–53% at N=2000–3000. **Treat any gap <3pp as noise.**
- N=40 → roughly ±8% CI. The "sign flip" is suggestive, not yet confirmed at high
  N — confirming it cheaply is the motivation for the local-model question (see
  [07-decisions-and-open-questions.md](07-decisions-and-open-questions.md)).

## Honest caveats
- Self-play vs M4/scripted bots has **zero archetype diversity** (all play
  smart-max-damage). Any opponent model trained on that data just learns M4.
  Real archetype data needs humans — see
  [05-human-training-and-data.md](05-human-training-and-data.md).
