# 03 — Decision Cache

File: `bot/llm/decision_cache.py` (~80 lines, stdlib only). Wired into
`LLMAgent`. Status: **built, tested, working. Uncommitted** (pending go-ahead).

## Why
The LLM kept re-answering the *same abstracted situation* across battles, burning
tokens and context on questions it had already answered. The cache makes a
recurring fork a dict lookup instead of an API call.

## The key safety idea
We do **not** cache "pick candidate #3" (battle-specific). We cache the
**abstract action** the LLM effectively took (`anchor`/`switch`/`setup`/`stall`),
keyed on a **coarse fork signature**, then *re-resolve* that action to a concrete
move in the current battle. If the cached action isn't available now, it falls
through to the LLM. A cache hit replays the LLM's *own policy*, memoized — it
can't introduce a decision the LLM wouldn't have made.

## Signature scheme (`_fork_signature`)
Coarse, bucketed, deterministic so it recurs:
`f{fork}|ko{opp_can_ko}|fst{we_move_first}|ob{our_best bucket}|oh{opp_hit bucket}
|sw{safe_switch}|set{has_setup}|stl{has_stall}|hp{our}{opp}|t{team_lead}`
Buckets: `our_best`(25,45,70,100), `opp_hit`(25,30,35,60), hp%(33,66), team =
sign(our_remaining − opp_remaining). Bounded space → hit rate climbs toward the
recurrence ceiling as it saturates.

## Storage
Flat JSON `{signature: action}`, atomic write (tempfile + `os.replace`), flush
every 25 new entries + one `atexit` flush. Process-wide singleton
`shared_cache()` so multiple agents in a benchmark share one cache/flush.

## Measured (M5 8B vs SimpleHeuristics)
| Run | Forks | LLM calls | Cache hits | Groq tokens |
|-----|-------|-----------|------------|-------------|
| Cold (empty) | 122 | 70 | 52 (**43%**) | 21.5k |
| Warm (110 entries) | 45 | 28 | 17 (**38%**) | 9.5k |

~40% of fork turns now cost **zero tokens**, cold and warm. 0 fallbacks/errors.
Winrate at low N is noise — parity vs a no-cache run needs a high-N `PS_CACHE_OFF=1`
A/B (blocked on cheap eval).

## Controls
- `PS_CACHE_OFF=1` — disable (clean A/B baseline).
- `PS_CACHE_PATH=/path.json` — relocate.
- File `bot/data/decision_cache.json` is **gitignored** (churns during A/B;
  promote a seeded copy to tracked later). It's also the **seed of the M6
  archetype knowledge store**.
