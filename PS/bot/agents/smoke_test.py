"""M3 smoke test: HeuristicAgent vs RandomPlayer on a local server.

A short run (20 games) to verify the agent is wired up and beating
random convincingly. The formal acceptance criterion is 500 games at
>=95% winrate; pass --n-battles 500 when running the real thing.

Run a local server first (from a separate shell):

    node pokemon-showdown start --no-security

Then from the PS/ directory:

    python -m bot.agents.smoke_test
    python -m bot.agents.smoke_test --n-battles 500
"""

import argparse
import asyncio

from poke_env import AccountConfiguration, LocalhostServerConfiguration, RandomPlayer

from bot.agents import HeuristicAgent


BATTLE_FORMAT = "gen9randombattle"
DEFAULT_BATTLES = 20


async def run(n_battles: int) -> None:
    heuristic = HeuristicAgent(
        account_configuration=AccountConfiguration("HeurM3", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )
    random_agent = RandomPlayer(
        account_configuration=AccountConfiguration("RandM3", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )

    await heuristic.battle_against(random_agent, n_battles=n_battles)

    wins = heuristic.n_won_battles
    total = heuristic.n_finished_battles
    winrate = (wins / total * 100) if total else 0.0
    print(
        f"heuristic vs random: {wins} / {total} wins ({winrate:.1f}%)"
    )
    if total >= 100 and winrate < 95.0:
        print("WARNING: below M3 acceptance threshold (>=95%).")


def main() -> None:
    parser = argparse.ArgumentParser(description="M3 heuristic smoke test")
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
