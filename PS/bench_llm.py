#!/usr/bin/env python3
"""M5 eval: LLMAgent (Groq) vs a configurable opponent.

Opponents: m4 = ExpectimaxAgent (the ~52% formula bot); simple = poke-env's
SimpleHeuristicsPlayer (a competent built-in bot that switches/uses hazards —
a fairer yardstick than max-damage M3/M4 for the LLM's strategic edge).

Usage (PS server running on :8000):
    python bench_llm.py --n-battles 40 --opponent simple
    PS_LLM_OFF=1 python bench_llm.py --n-battles 50 --opponent simple   # floor, no API calls
"""

import argparse
import asyncio
import time

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from poke_env.player import SimpleHeuristicsPlayer

from bot.agents.expectimax import ExpectimaxAgent
from bot.agents.llm_agent import LLMAgent

FORMAT = "gen9randombattle"

# opponent key -> (Player class, account name)
OPPONENTS = {
    "m4": (ExpectimaxAgent, "ExpecM4b"),
    "simple": (SimpleHeuristicsPlayer, "SimpleHeur"),
}


async def run(n: int, opponent: str) -> None:
    llm = LLMAgent(
        account_configuration=AccountConfiguration("LLM-M5", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=FORMAT,
    )
    opp_cls, opp_name = OPPONENTS[opponent]
    foe = opp_cls(
        account_configuration=AccountConfiguration(opp_name, None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=FORMAT,
    )

    print(f"LLMAgent vs {opp_name} ({opponent}) — {n} battles")
    start = time.time()
    for i in range(n):
        try:
            await llm.battle_against(foe, n_battles=1)
        except Exception as e:
            print(f"  [skip] battle {i} errored: {type(e).__name__}: {e}")
            continue
        w, t = llm.n_won_battles, llm.n_finished_battles
        print(f"  {t}/{n}  wins={w} ({(w/t*100 if t else 0):.0f}%)  "
              f"[llm={llm.n_llm} cache={llm.n_cache} gate={llm.n_gate} fast={llm.n_fastpath} fallback={llm.n_fallback}]")

    elapsed = time.time() - start
    w, t = llm.n_won_battles, llm.n_finished_battles
    print(f"\nResult: {w}/{t} = {(w/t*100 if t else 0):.1f}%   ({elapsed:.0f}s, {elapsed/max(t,1):.1f}s/battle)")
    forks = llm.n_llm + llm.n_cache + llm.n_fallback
    hit_rate = (llm.n_cache / forks * 100) if forks else 0
    print(f"LLM(fork) calls: {llm.n_llm}  cache hits: {llm.n_cache} ({hit_rate:.0f}% of {forks} forks)  "
          f"gated-heuristic: {llm.n_gate}  fast-path: {llm.n_fastpath}  fallback: {llm.n_fallback}")
    if llm._cache is not None:
        print(f"Decision cache: {len(llm._cache)} entries at {llm._cache.path}")
    if llm._client:
        c = llm._client
        print(f"Groq: {c.n_calls} calls, avg {c.total_latency/max(c.n_calls,1):.2f}s, "
              f"{c.total_tokens} tokens ({c.total_tokens/max(c.n_calls,1):.0f}/call), model {c.model}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-battles", type=int, default=5)
    ap.add_argument("--opponent", choices=list(OPPONENTS), default="m4")
    args = ap.parse_args()
    asyncio.run(run(args.n_battles, args.opponent))


if __name__ == "__main__":
    main()
