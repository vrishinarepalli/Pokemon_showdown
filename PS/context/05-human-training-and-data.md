# 05 — Training vs Humans & Data Sourcing

"Train against humans instead of M4" splits into two very different things.

## 1. Humans as the *yardstick* (evaluation) — ✅ yes
Ladder the M5 bot vs real players to measure winrate. This is the only true test
(M6). poke-env can connect to the official server (swap
`LocalhostServerConfiguration` for the real ws config + a registered account).
- **Keep N small (50–100 games)** — this is measurement, not training.
- Watch-outs: Showdown bot policy (random battles tolerates bots — read the
  rules), rate limits, and **every game still burns Groq tokens**. This is exactly
  where the daily limit bites.

## 2. Humans as *training data* — ✅ goal, ❌ don't ladder for it
Three killers if you try to generate data by laddering:
- **Throughput:** human games run at human speed and can't be parallelized (one
  human = one slow game). 5k laddered games = weeks of wall-clock.
- **Tokens:** 5k games × ~15 LLM forks = far past any free tier.
- **Sample efficiency:** RL-training the *policy* on win/loss = 1 bit/game over a
  huge state space; 5k games learns almost nothing, and the LLM is *already* the
  policy. Not worth it.

## The actual move: scrape replays, don't ladder for data
Showdown publishes finished games:
- List: `https://replay.pokemonshowdown.com/search.json?format=gen9randombattle`
- Each replay has a downloadable `.log` / `.json`.

Gets thousands of **real human gen9randombattle games — free, offline, no
laddering, no tokens, no ToS risk.** Then offline: featurize opponent behavior
(switch rate, setup/hazard/status usage, aggression) and **cluster into
archetypes**, or behavioral-clone next-move prediction.

## Bottom line
- Ladder vs humans → **scoring only, small N.**
- Learn from humans → **scrape replays, not ladder.** Skip RL-on-5k.

## Offered next step (not yet built)
A ~30-line stdlib (`urllib` + `json`) replay scraper that banks human games into
a folder. Zero tokens to run. Unblocks all downstream opponent-modeling work.
