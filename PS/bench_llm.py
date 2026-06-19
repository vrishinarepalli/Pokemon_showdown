#!/usr/bin/env python3
"""M5 eval: LLMAgent (Groq) vs M4 (ExpectimaxAgent).

Usage (PS server running on :8000):
    python bench_llm.py --n-battles 5
    PS_LLM_OFF=1 python bench_llm.py --n-battles 20   # heuristic-only (no API calls)
"""

import argparse
import asyncio
import time

from poke_env import AccountConfiguration, LocalhostServerConfiguration

from bot.agents.expectimax import ExpectimaxAgent
from bot.agents.llm_agent import LLMAgent

FORMAT = "gen9randombattle"


async def run(n: int) -> None:
    llm = LLMAgent(
        account_configuration=AccountConfiguration("LLM-M5", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=FORMAT,
    )
    m4 = ExpectimaxAgent(
        account_configuration=AccountConfiguration("ExpecM4b", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=FORMAT,
    )

    print(f"LLMAgent vs M4 (Expectimax) — {n} battles")
    start = time.time()
    for i in range(n):
        try:
            await llm.battle_against(m4, n_battles=1)
        except Exception as e:
            print(f"  [skip] battle {i} errored: {type(e).__name__}: {e}")
            continue
        w, t = llm.n_won_battles, llm.n_finished_battles
        print(f"  {t}/{n}  wins={w} ({(w/t*100 if t else 0):.0f}%)  "
              f"[llm={llm.n_llm} gate={llm.n_gate} fast={llm.n_fastpath} fallback={llm.n_fallback}]")

    elapsed = time.time() - start
    w, t = llm.n_won_battles, llm.n_finished_battles
    print(f"\nResult: {w}/{t} = {(w/t*100 if t else 0):.1f}%   ({elapsed:.0f}s, {elapsed/max(t,1):.1f}s/battle)")
    print(f"LLM(fork) calls: {llm.n_llm}  gated-heuristic: {llm.n_gate}  "
          f"fast-path: {llm.n_fastpath}  fallback: {llm.n_fallback}")
    if llm._client:
        c = llm._client
        print(f"Groq: {c.n_calls} calls, avg {c.total_latency/max(c.n_calls,1):.2f}s, "
              f"{c.total_tokens} tokens ({c.total_tokens/max(c.n_calls,1):.0f}/call), model {c.model}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-battles", type=int, default=5)
    args = ap.parse_args()
    asyncio.run(run(args.n_battles))


if __name__ == "__main__":
    main()
