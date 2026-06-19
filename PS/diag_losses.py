#!/usr/bin/env python3
"""Print turn-by-turn chosen actions for a few LOST battles, flagging likely blunders."""
import asyncio, sys
from poke_env import AccountConfiguration, LocalhostServerConfiguration
from bot.agents import HeuristicAgent
from bot.agents.expectimax import ExpectimaxAgent

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
SHOW = int(sys.argv[2]) if len(sys.argv) > 2 else 3

async def main():
    exp = ExpectimaxAgent(account_configuration=AccountConfiguration("ExpLoss", None),
                          server_configuration=LocalhostServerConfiguration, battle_format="gen9randombattle")
    heur = HeuristicAgent(account_configuration=AccountConfiguration("HeurLoss", None),
                          server_configuration=LocalhostServerConfiguration, battle_format="gen9randombattle")
    for _ in range(N):
        await exp.battle_against(heur, n_battles=1)
        for tag, b in exp.battles.items():
            if b.finished and not any(l.battle_id == tag for l in exp._battle_logs):
                exp.finalize_battle_log(b)
    losses = [l for l in exp._battle_logs if l.winner == "them"]
    losses.sort(key=lambda l: len(l.turns))  # shortest losses = clearest blunders
    print(f"{len(losses)} losses / {len(exp._battle_logs)} battles")
    for log in losses[:SHOW]:
        print("\n" + "="*72)
        print(f"LOSS {log.battle_id}  ({len(log.turns)} turns)")
        print(f"  our team: {list(log.our_team.keys())}")
        print(f"  opp team: {list(log.opp_team.keys())}")
        for t in log.turns:
            ch = next((d for d in t.decisions if d.chosen), None)
            if ch is None: continue
            kind = "SWITCH" if ch.action_type=="switch" else ("SETUP" if ch.is_setup else ("HAZ" if ch.is_hazard else "move"))
            flag = ""
            # flags for suspicious decisions
            atk = [d.score for d in t.decisions if d.action_type=="move" and d.score>-900]
            if ch.action_type=="switch" and atk and (ch.score - max(atk)) < 0.10:
                flag += " [THIN-SWITCH]"
            if ch.is_setup and t.strategic_state=="DANGER":
                flag += " [SETUP-IN-DANGER]"
            if ch.action_type=="switch" and ch.expected_hp_after is not None and ch.expected_hp_after<=0.02 and atk:
                flag += " [SWITCH-INTO-KO]"
            print(f"  T{t.turn:2d} {t.our_pokemon:>14}({t.our_hp:.2f}) vs {t.opp_pokemon:>14}({t.opp_hp:.2f}) "
                  f"[{t.strategic_state:8}] -> {kind:6} {ch.action_name:14} sc={ch.score:+.2f}{flag}")

asyncio.run(main())
