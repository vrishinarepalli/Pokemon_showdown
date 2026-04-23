"""M4 smoke test: ExpectimaxAgent vs HeuristicAgent on a local server.

A short run (default 20 games) to verify the agent is wired up.
The formal acceptance criterion is 500 games at >=60% winrate.

Run a local server first (from a separate shell):

    node pokemon-showdown start --no-security

Then from the PS/ directory:

    python -m bot.agents.smoke_test_m4
    python -m bot.agents.smoke_test_m4 --n-battles 500
"""

import argparse
import asyncio
import time
from tqdm import tqdm

from poke_env import AccountConfiguration, LocalhostServerConfiguration

from bot.agents import HeuristicAgent
from bot.agents.expectimax import ExpectimaxAgent


BATTLE_FORMAT = "gen9randombattle"
DEFAULT_BATTLES = 20


async def run(n_battles: int) -> None:
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

    pbar = tqdm(total=n_battles, desc="Battles", unit="battle")
    start_time = time.time()
    last_count = 0

    for _ in range(n_battles):
        await expectimax.battle_against(heuristic, n_battles=1)
        current_count = expectimax.n_finished_battles
        wins = expectimax.n_won_battles
        winrate = (wins / current_count * 100) if current_count else 0.0
        pbar.update(current_count - last_count)
        pbar.set_postfix({"wins": f"{wins}/{current_count} ({winrate:.1f}%)"})
        last_count = current_count

    pbar.close()
    elapsed = time.time() - start_time

    wins = expectimax.n_won_battles
    total = expectimax.n_finished_battles
    winrate = (wins / total * 100) if total else 0.0
    print(f"\nexpectimax vs heuristic: {wins} / {total} wins ({winrate:.1f}%)")
    print(f"Time elapsed: {elapsed:.1f}s ({elapsed/total:.1f}s per battle)")
    if total >= 100 and winrate < 60.0:
        print("WARNING: below M4 acceptance threshold (>=60%).")


def main() -> None:
    parser = argparse.ArgumentParser(description="M4 expectimax smoke test")
    parser.add_argument(
        "--n-battles",
        type=int,
        default=DEFAULT_BATTLES,
        help=f"number of battles to play (default: {DEFAULT_BATTLES})",
    )
    args = parser.parse_args()
    asyncio.run(run(args.n_battles))


if __name__ == "__main__":
    main()
