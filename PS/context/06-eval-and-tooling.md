# 06 — Eval & Tooling

## PS server (must be running on :8000)
From the repo root:
```
node node_modules/pokemon-showdown/pokemon-showdown start --no-security
```
(Already running in normal sessions; returns HTTP 200.)

## Benchmark: `bench_llm.py`
```
python bench_llm.py --n-battles 40 --opponent simple
PS_LLM_OFF=1 python bench_llm.py --n-battles 50 --opponent simple   # floor, no API
PS_CACHE_OFF=1 python bench_llm.py --n-battles 50 --opponent simple  # cache A/B baseline
```
- Opponents: `m4` = `ExpectimaxAgent` (old ~52% formula bot), `simple` =
  poke-env `SimpleHeuristicsPlayer` (the current, fairer yardstick).
- Prints per-battle counters and a summary: winrate, fork cache hit-rate,
  cache entry count, and Groq call/latency/token stats.

## Groq config
- OpenAI-compatible API. Models: `llama-3.1-8b-instant` (default),
  `llama-3.3-70b-versatile` (~100K tokens/**day** free).
- ~2–2.6s/call, ~275–293 tokens/call.
- Key lives in **gitignored `.env`**, never in code.
  ⚠️ The key was exposed in plaintext chat earlier — **regenerate it.**

## Win-rate variance rules
- 47–53% swing at N=2000–3000. **Gaps <3pp = noise.**
- N=40 → ±~8% CI. Small-N winrates are directional only.

## poke-env baselines available
`RandomPlayer`, `MaxBasePowerPlayer`, `SimpleHeuristicsPlayer` (311-line
competent bot; plain `Player` kwargs work — no custom `__init__`).
