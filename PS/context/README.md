# Context Index (read this first)

Conversation context snapshots, one topic per file. Read this TOC, then open
only the file(s) you need. Keep these updated as decisions change — they are
the durable memory of *why*, not just *what* (the code is the *what*).

Last updated: 2026-06-21

| File | What's in it |
|------|--------------|
| [01-project-status.md](01-project-status.md) | Where the bot is now: M4 closed ~52%, M5 LLM-agentic, yardstick = SimpleHeuristicsPlayer, the "sign flip" win. |
| [02-m5-architecture.md](02-m5-architecture.md) | How the M5 LLM agent decides a move: floor → fast-path → fork gate → anchor → strategy-only override. Fork types. |
| [03-decision-cache.md](03-decision-cache.md) | The token-saving cache we built: design, signature scheme, measured ~40% fork-call cut, env flags. |
| [04-gflownets-assessment.md](04-gflownets-assessment.md) | The GFlowNet opponent-modeling idea and why we said *don't* — use BC/clustering instead. |
| [05-human-training-and-data.md](05-human-training-and-data.md) | "Train vs humans" split into eval vs data; scrape replays, don't ladder for data. |
| [06-eval-and-tooling.md](06-eval-and-tooling.md) | bench_llm.py, opponents, Groq config, PS server command, win-rate variance rules. |
| [07-decisions-and-open-questions.md](07-decisions-and-open-questions.md) | Rejected ideas (evo workflow), deferred (local model, archetype bots), pending tasks. |
| [08-conventions.md](08-conventions.md) | Working rules: ponytail-default, archive-not-delete, no-delete, commit-only-when-asked. |

## Roadmap shorthand
- **M3/M4** — formula bots (max-damage / expectimax). M4 capped ~52% vs M3.
- **M5** — LLM-with-tools agentic (current). Groq-backed, heuristic-anchored.
- **M6** — vs real humans + opponent archetype adaptation (next).
