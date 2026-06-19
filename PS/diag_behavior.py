#!/usr/bin/env python3
"""Behavioral diagnostic: run N battles, then quantify what the bot actually does,
split by wins vs losses. Tests the over-switching / bad-setup hypotheses.

Usage: python diag_behavior.py [N]
"""
import asyncio
import sys
from collections import Counter, defaultdict

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from bot.agents import HeuristicAgent
from bot.agents.expectimax import ExpectimaxAgent

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def classify(decision):
    if decision.action_type == "switch":
        return "switch"
    if decision.is_setup:
        return "setup"
    if decision.is_hazard:
        return "hazard"
    if decision.move_category == "status":
        return "status_or_other"
    return "attack"


async def main():
    exp = ExpectimaxAgent(
        account_configuration=AccountConfiguration("ExpDiag", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format="gen9randombattle",
    )
    heur = HeuristicAgent(
        account_configuration=AccountConfiguration("HeurDiag", None),
        server_configuration=LocalhostServerConfiguration,
        battle_format="gen9randombattle",
    )
    for _ in range(N):
        await exp.battle_against(heur, n_battles=1)
        for tag, b in exp.battles.items():
            if b.finished and not any(l.battle_id == tag for l in exp._battle_logs):
                exp.finalize_battle_log(b)

    logs = exp._battle_logs
    wins = [l for l in logs if l.winner == "us"]
    losses = [l for l in logs if l.winner == "them"]
    print(f"\n{'='*64}")
    print(f"Battles: {len(logs)}  Wins: {len(wins)}  Losses: {len(losses)}  "
          f"({len(wins)/max(1,len(logs))*100:.1f}%)")
    print(f"{'='*64}")

    def summarize(group, name):
        dec_mix = Counter()
        state_mix = Counter()
        n_turns = 0
        voluntary_switch = 0   # switch chosen WHILE attacks were available
        forced_switch = 0      # switch chosen with NO attack option (post-faint / trapped)
        margins = []           # (switch_score - best_attack_score) on voluntary switches
        thin_switches = 0      # voluntary switches winning by < 0.10
        setup_count = 0
        avg_len = 0
        for log in group:
            avg_len += len(log.turns)
            for t in log.turns:
                chosen = next((d for d in t.decisions if d.chosen), None)
                if chosen is None:
                    continue
                n_turns += 1
                kind = classify(chosen)
                dec_mix[kind] += 1
                state_mix[t.strategic_state or "?"] += 1
                if kind == "setup":
                    setup_count += 1
                if kind == "switch":
                    attack_scores = [d.score for d in t.decisions
                                     if d.action_type == "move" and d.score > -900]
                    if not attack_scores:
                        forced_switch += 1
                    else:
                        voluntary_switch += 1
                        margin = chosen.score - max(attack_scores)
                        margins.append(margin)
                        if margin < 0.10:
                            thin_switches += 1
        margins.sort()
        med = margins[len(margins)//2] if margins else 0.0
        print(f"\n--- {name} ({len(group)} battles, avg {avg_len/max(1,len(group)):.1f} turns) ---")
        print(f"  decisions: {n_turns}  | mix: " +
              ", ".join(f"{k}={v} ({v/max(1,n_turns)*100:.0f}%)" for k, v in dec_mix.most_common()))
        print(f"  strategic_state: " +
              ", ".join(f"{k}={v} ({v/max(1,n_turns)*100:.0f}%)" for k, v in state_mix.most_common()))
        print(f"  switches: voluntary={voluntary_switch}, forced(post-faint)={forced_switch}")
        print(f"  voluntary-switch margin over best attack: median={med:+.3f}, "
              f"thin(<0.10)={thin_switches} ({thin_switches/max(1,voluntary_switch)*100:.0f}% of voluntary)")
        print(f"  setup moves used: {setup_count}")
        return dec_mix, n_turns

    summarize(wins, "WINS")
    summarize(losses, "LOSSES")


if __name__ == "__main__":
    asyncio.run(main())
