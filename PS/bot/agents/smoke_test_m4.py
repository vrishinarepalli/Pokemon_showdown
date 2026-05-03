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


async def run(n_battles: int, save_replays: bool = False, save_logs: bool = True) -> None:
    replay_dir = "./replays" if save_replays else None
    expectimax = ExpectimaxAgent(
        account_configuration=AccountConfiguration("ExpecM4", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format=BATTLE_FORMAT,
        save_replays=replay_dir,
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
        battles_before = len(expectimax._battle_logs)

        await expectimax.battle_against(heuristic, n_battles=1)

        # Finalize any newly completed battles that don't have logs yet
        for battle_tag, battle in expectimax.battles.items():
            if not battle.finished:
                continue
            # Check if we already logged this battle
            if any(log.battle_id == battle_tag for log in expectimax._battle_logs):
                continue
            expectimax.finalize_battle_log(battle)

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

    # Save battle logs for analysis
    if save_logs:
        log_file = "./battle_logs.json"
        expectimax.save_battle_logs(log_file)
        print(f"\nBattle logs saved to {log_file}")

        # Print summary of problematic switches
        from bot.agents.battle_logger import BattleLogCollector
        collector = BattleLogCollector()
        for log in expectimax.get_battle_logs():
            collector.add_log(log)


def main() -> None:
    parser = argparse.ArgumentParser(description="M4 expectimax smoke test")
    parser.add_argument(
        "--n-battles",
        type=int,
        default=DEFAULT_BATTLES,
        help=f"number of battles to play (default: {DEFAULT_BATTLES})",
    )
    parser.add_argument(
        "--save-replays",
        action="store_true",
        help="save battle replays to ./replays/ (HTML files, show both teams)",
    )
    parser.add_argument(
        "--no-logs",
        action="store_true",
        help="disable battle log collection and saving",
    )
    args = parser.parse_args()
    asyncio.run(run(args.n_battles, save_replays=args.save_replays, save_logs=not args.no_logs))


if __name__ == "__main__":
    main()
