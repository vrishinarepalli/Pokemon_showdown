"""M1 smoke test: two RandomPlayer agents battling on a local server.

Confirms the harness is wired up end-to-end:
  - poke-env installed and importable
  - local pokemon-showdown server reachable on ws://localhost:8000
  - a gen9randombattle can start, run, and finish

Run a local server first (from a separate shell):

    node pokemon-showdown start --no-security

Then from the repository root:

    python -m bot.client.smoke_test

Expected output: a single line reporting wins / battles for player 1.
"""

import asyncio

from poke_env import AccountConfiguration, LocalhostServerConfiguration, RandomPlayer


BATTLE_FORMAT = "gen9randombattle"
N_BATTLES = 1


async def main() -> None:
    player_1 = RandomPlayer(
        account_configuration=AccountConfiguration("BotSmoke1", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )
    player_2 = RandomPlayer(
        account_configuration=AccountConfiguration("BotSmoke2", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
    )

    await player_1.battle_against(player_2, n_battles=N_BATTLES)

    print(
        f"player_1 won {player_1.n_won_battles} / "
        f"{player_1.n_finished_battles} battles"
    )


if __name__ == "__main__":
    asyncio.run(main())
