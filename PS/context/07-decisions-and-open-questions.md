# 07 — Decisions & Open Questions

## 2026-06-21 — PIVOT: LLM shelved → ML (BC on replays)
Groq's daily token cap makes the M5 LLM path impossible to iterate on consistently,
so we SHELVED it (kept in repo, not deleted) and committed to local ML.
- **Chosen:** behavioral cloning on scraped human replays → a learned value function
  that drops into expectimax (replaces `handcrafted.py`). Hits the proven ceiling (the
  decision policy), runs locally with no token cap, and the replays supply the
  playstyle diversity self-play vs M4 never had. Prior art: metamon.
- **GFlowNets reconsidered and rejected again** — still the wrong shape (see 04).
- **Done:** `scrape_replays.py` (data step). **Next:** logs→(state,action) pairs → train.

## Rejected
- **Genetic/beam-search multi-agent workflow** (Opus orchestrator + analyzer/
  implementer/checker subagents spawning & pruning branches in waves).
  **Not viable here:** win-rate fitness is too noisy (±8% at N=40) and too
  token-expensive to rank variants; the search space is nearly empty (the tuning
  levers were already disproven); the real blocker is **evaluation** (wrong
  yardstick), not lack of code variants. Lean alternative if ever needed: cheap
  deterministic opponents + one human-in-loop 3-wide wave.
- **GFlowNets for opponent modeling** — wrong tool; use BC/clustering. See
  [04-gflownets-assessment.md](04-gflownets-assessment.md).
- **RL-train the policy on ~5k games** — sample efficiency makes it pointless.

## Deferred (revisit later)
- **Local model (Ollama)** to dodge Groq's daily token limit. Motivation: run the
  high-N A/B needed to confirm the +3.3pp SimpleHeuristics "sign flip" and the
  cache's winrate parity. Tradeoff: local 8B quality/latency vs Groq. Not yet done.
- **Scripted archetype opponents** (stall / hyper-offense / setup-sweep) as thin
  `SimpleHeuristicsPlayer` subclasses — build only if needed; pre-made ones may
  exist online.
- **Promote a seeded `decision_cache.json` to tracked** once it stabilizes.

## Pending tasks
- **Regenerate the Groq API key** (was exposed in plaintext chat).
- **Commit the decision-cache work** when the user gives the go-ahead (4 modified
  files + `bot/llm/decision_cache.py`).
- **Replay scraper** — offered, awaiting go-ahead (see
  [05-human-training-and-data.md](05-human-training-and-data.md)).

## Key facts to not re-derive
- `.git` is at the **parent** dir `/Users/vrishinarepalli/Desktop/Projects/Pokemon_showdown`,
  not `PS/`. Branch `feature/team-value-eval`. Remote
  github.com/vrishinarepalli/Pokemon_showdown.
- Removed dead code lives on `archive/pre-ponytail-cleanup` (53 files / ~15k
  lines), pushed — referenceable forever, never hard-deleted.
- macOS: `.venv/bin/pip` launcher is blocked → use `.venv/bin/python -m pip`.
- zsh eats unquoted `--include=*.py` globs → quote them.
