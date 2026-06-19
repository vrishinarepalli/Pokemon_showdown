#!/usr/bin/env python3
"""Branch benchmark: run N battles on the current git branch and report win rate.

Usage (from PS/ directory, with PS server already running):
    python benchmark.py                     # 100 battles
    python benchmark.py --n-battles 50      # faster smoke check
    python benchmark.py --label main        # tag output with branch name

Start the server first (separate terminal, from repo root):
    node node_modules/pokemon-showdown/pokemon-showdown start --no-security
"""

import argparse
import asyncio
import subprocess
import time

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from bot.agents import HeuristicAgent
from bot.agents.expectimax import ExpectimaxAgent

BATTLE_FORMAT = "gen9randombattle"


async def run_benchmark(n_battles: int, label: str, save_logs: bool = False) -> dict:
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
    ).strip()
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], text=True
    ).strip()
    tag = label or branch

    print(f"\n{'='*60}")
    print(f"Branch : {branch}  ({commit})")
    print(f"Label  : {tag}")
    print(f"Battles: {n_battles}")
    print(f"{'='*60}")

    expectimax = ExpectimaxAgent(
        account_configuration=AccountConfiguration("ExpecM4", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )
    heuristic = HeuristicAgent(
        account_configuration=AccountConfiguration("HeurM4", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )

    try:
        from tqdm import tqdm
        pbar = tqdm(total=n_battles, desc="Battles", unit="battle")
        use_pbar = True
    except ImportError:
        pbar = None
        use_pbar = False

    start = time.time()
    last_count = 0

    for _ in range(n_battles):
        try:
            await expectimax.battle_against(heuristic, n_battles=1)
        except Exception as e:
            # poke-env occasionally raises a transient state-desync error
            # ("Message thinks X is active, but it's not."). Over thousands of
            # battles this would otherwise abort the whole run. Skip and continue;
            # the won/finished counters are cumulative so the sample just shrinks
            # by one battle.
            print(f"\n[skip] battle errored: {type(e).__name__}: {e}")
            continue

        for battle_tag, battle in expectimax.battles.items():
            if not battle.finished:
                continue
            if any(log.battle_id == battle_tag for log in expectimax._battle_logs):
                continue
            expectimax.finalize_battle_log(battle)

        current = expectimax.n_finished_battles
        wins = expectimax.n_won_battles
        pct = wins / current * 100 if current else 0.0

        if use_pbar:
            pbar.update(current - last_count)
            pbar.set_postfix({"wins": f"{wins}/{current} ({pct:.1f}%)"})
        else:
            if current % 10 == 0:
                print(f"  {current}/{n_battles}  wins={wins} ({pct:.1f}%)")
        last_count = current

    if use_pbar:
        pbar.close()

    elapsed = time.time() - start
    wins = expectimax.n_won_battles
    total = expectimax.n_finished_battles
    pct = wins / total * 100 if total else 0.0

    print(f"\nResult [{tag}]: {wins}/{total} wins  ({pct:.1f}%)")
    print(f"Time  : {elapsed:.0f}s  ({elapsed/total:.1f}s per battle)")
    threshold_ok = pct >= 60.0
    print(f"M4 target (>=60%): {'PASS' if threshold_ok else 'FAIL'}")

    return {"branch": branch, "commit": commit, "label": tag,
            "wins": wins, "total": total, "pct": pct, "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Branch win-rate benchmark")
    parser.add_argument("--n-battles", type=int, default=100)
    parser.add_argument("--label", type=str, default="")
    parser.add_argument("--no-logs", action="store_true", help="skip saving battle logs")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args.n_battles, args.label, save_logs=not args.no_logs))


if __name__ == "__main__":
    main()
