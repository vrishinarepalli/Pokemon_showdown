"""Analyze battle logs to identify decision patterns and problematic switches."""

import json
import sys
from collections import defaultdict
from typing import Optional


def analyze_logs(log_file: str = "./battle_logs.json", show_switches: bool = True, show_turns: Optional[int] = None):
    """Analyze battle logs for decision patterns.

    Args:
        log_file: Path to battle_logs.json
        show_switches: Print details of suboptimal switches
        show_turns: If set, show this many turns of detail from each battle
    """
    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except FileNotFoundError:
        print(f"Log file not found: {log_file}")
        return

    if not logs:
        print("No battles logged.")
        return

    total = len(logs)
    wins = sum(1 for log in logs if log["winner"] == "us")
    losses = sum(1 for log in logs if log["winner"] == "them")
    winrate = (wins / total * 100) if total else 0.0

    print(f"\n{'='*70}")
    print(f"BATTLE SUMMARY: {wins}/{total} wins ({winrate:.1f}%)")
    print(f"{'='*70}\n")

    # Analyze switches
    problematic_switches = []
    total_switches = 0
    overvalued_switches = 0

    for log in logs:
        for turn in log["turns"]:
            switches = [d for d in turn["decisions"] if d["type"] == "switch"]
            if not switches:
                continue

            total_switches += len(switches)
            moves = [d for d in turn["decisions"] if d["type"] == "move" and d["score"] != -999.0]

            # Find chosen switch
            chosen_switch = next((d for d in switches if d["chosen"]), None)
            if not chosen_switch:
                continue

            # Compare switch score to best move score
            best_move_score = max([d["score"] for d in moves]) if moves else -999.0
            switch_score = chosen_switch["score"]

            # Flag if switch was chosen despite worse score than available moves
            if switch_score < best_move_score - 0.05:
                overvalued_switches += 1
                problematic_switches.append({
                    "battle": log["battle_id"],
                    "turn": turn["turn"],
                    "switched_to": chosen_switch["name"],
                    "switch_score": switch_score,
                    "best_move": [d for d in moves if abs(d["score"] - best_move_score) < 0.01][0],
                    "our_pokemon": turn["our_pokemon"],
                    "opp_pokemon": turn["opp_pokemon"],
                    "our_hp": turn["our_hp"],
                    "opp_hp": turn["opp_hp"],
                    "outcome": log["winner"],
                })

    if show_switches:
        # Show problematic switches
        if problematic_switches:
            print(f"\nPROBLEMATIC SWITCHES ({overvalued_switches}/{total_switches} total switches):")
            print(f"{'='*70}\n")

            # Group by outcome
            by_outcome = defaultdict(list)
            for ps in problematic_switches:
                by_outcome[ps["outcome"]].append(ps)

            for outcome in ["them", "us", None]:
                switches = by_outcome.get(outcome, [])
                if not switches:
                    continue

                outcome_name = "LOSSES" if outcome == "them" else "WINS" if outcome == "us" else "INCOMPLETE"
                print(f"\n{outcome_name}: {len(switches)} questionable switches\n")

                for ps in switches[:5]:  # Show first 5
                    print(f"  Battle {ps['battle']} Turn {ps['turn']}:")
                    print(f"    In:   {ps['our_pokemon']} (HP: {ps['our_hp']:.1%})")
                    print(f"    Out:  {ps['opp_pokemon']} (HP: {ps['opp_hp']:.1%})")
                    print(f"    -> Switched to {ps['switched_to']} (score: {ps['switch_score']:.3f})")
                    print(f"    vs. Best move {ps['best_move']['name']} (score: {ps['best_move']['score']:.3f})")
                    print()

        # Show ALL decisions (moves and switches) for detailed analysis
        print(f"\nDETAILED DECISION LOG (all battles, all turns):")
        print(f"{'='*70}\n")

        for log in logs:
            print(f"\nBattle {log['battle_id']} - Result: {('WIN' if log['winner']=='us' else 'LOSS' if log['winner']=='them' else '??')}:")
            for turn in log["turns"]:
                print(f"\n  Turn {turn['turn']}: {turn['our_pokemon']} (HP {turn['our_hp']:.0%}) vs {turn['opp_pokemon']} (HP {turn['opp_hp']:.0%})")

                # Show what opponent did last turn (visible at start of this turn)
                opp_last_action = turn.get("opp_last_action")
                opp_last_move = turn.get("opp_last_move")
                opp_prev_pokemon = turn.get("opp_prev_pokemon")
                if opp_last_action == "switch" and opp_prev_pokemon:
                    print(f"    [Opp last turn: SWITCHED from {opp_prev_pokemon} to {turn['opp_pokemon']}]")
                elif opp_last_move:
                    print(f"    [Opp last turn: used {opp_last_move}]")

                # Group decisions
                moves = [d for d in turn["decisions"] if d["type"] == "move"]
                switches = [d for d in turn["decisions"] if d["type"] == "switch"]

                # Show chosen decision
                chosen = next((d for d in turn["decisions"] if d["chosen"]), None)
                if chosen:
                    print(f"    ✓ CHOSEN: {chosen['type'].upper()} {chosen['name']} (score: {chosen['score']:.3f})")

                # Show top moves
                if moves:
                    top_moves = sorted(moves, key=lambda x: x["score"], reverse=True)[:3]
                    for m in top_moves:
                        print(f"      Move: {m['name']:20} score: {m['score']:7.3f}")

                # Show top switches
                if switches:
                    top_switches = sorted(switches, key=lambda x: x["score"], reverse=True)[:3]
                    for s in top_switches:
                        print(f"      Switch: {s['name']:20} score: {s['score']:7.3f}")

    # Analyze early game aggression
    print(f"\n{'='*70}")
    print("EARLY GAME PATTERNS (Turn 1-2):")
    print(f"{'='*70}\n")

    early_game_stats = {"switches": 0, "moves": 0}
    for log in logs:
        for turn in log["turns"][:2]:
            decisions = [d for d in turn["decisions"] if d["chosen"]]
            if decisions:
                if decisions[0]["type"] == "switch":
                    early_game_stats["switches"] += 1
                else:
                    early_game_stats["moves"] += 1

    total_early = early_game_stats["switches"] + early_game_stats["moves"]
    if total_early > 0:
        switch_pct = (early_game_stats["switches"] / total_early * 100)
        print(f"  Switch rate in first 2 turns: {switch_pct:.1f}%")
        print(f"  ({early_game_stats['switches']}/{total_early} decisions were switches)\n")

    # Analyze team coverage
    print(f"\n{'='*70}")
    print("TEAM COMPOSITION (first battle):")
    print(f"{'='*70}\n")

    if logs:
        our_team = logs[0]["our_team"]
        opp_team = logs[0]["opp_team"]
        print("Our team:")
        for species, info in our_team.items():
            print(f"  - {species.capitalize()} (L{info['level']})")
        print(f"\nOpponent team (observed):")
        for species, info in opp_team.items():
            print(f"  - {species.capitalize()} (L{info['level']})")


def analyze_single_battle(battle_id: Optional[str] = None, log_file: str = "./battle_logs.json"):
    """Show every turn of a single battle, end-to-end.

    If battle_id is None, picks the longest LOSS (most decision points to learn from).
    """
    with open(log_file) as f:
        logs = json.load(f)

    if battle_id:
        target = next((l for l in logs if l["battle_id"] == battle_id), None)
        if target is None:
            print(f"Battle {battle_id} not found")
            return
    else:
        # Pick longest loss
        losses = [l for l in logs if l["winner"] == "them"]
        if not losses:
            print("No losses to analyze")
            return
        target = max(losses, key=lambda l: len(l["turns"]))

    print(f"\n{'='*70}")
    print(f"BATTLE: {target['battle_id']}")
    result = "WIN" if target["winner"] == "us" else "LOSS" if target["winner"] == "them" else "??"
    print(f"RESULT: {result} ({len(target['turns'])} turns)")
    print(f"{'='*70}\n")

    print("OUR TEAM:")
    for species, info in target["our_team"].items():
        print(f"  - {species.capitalize()} (L{info['level']})")
    print("\nOPP TEAM (revealed by end):")
    for species, info in target["opp_team"].items():
        print(f"  - {species.capitalize()} (L{info['level']})")
    print()

    for turn in target["turns"]:
        print(f"\n{'─'*70}")
        print(f"Turn {turn['turn']}: {turn['our_pokemon']} (HP {turn['our_hp']:.0%}) vs {turn['opp_pokemon']} (HP {turn['opp_hp']:.0%})")

        opp_last_action = turn.get("opp_last_action")
        opp_last_move = turn.get("opp_last_move")
        opp_prev_pokemon = turn.get("opp_prev_pokemon")
        if opp_last_action == "switch" and opp_prev_pokemon:
            print(f"  [Opp last turn: SWITCHED from {opp_prev_pokemon} to {turn['opp_pokemon']}]")
        elif opp_last_move:
            print(f"  [Opp last turn: used {opp_last_move}]")

        chosen = next((d for d in turn["decisions"] if d["chosen"]), None)
        if chosen:
            print(f"  ✓ CHOSEN: {chosen['type'].upper()} {chosen['name']} (score: {chosen['score']:.3f})")

        moves = sorted([d for d in turn["decisions"] if d["type"] == "move"], key=lambda x: -x["score"])
        switches = sorted([d for d in turn["decisions"] if d["type"] == "switch"], key=lambda x: -x["score"])

        for m in moves:
            marker = " <- CHOSEN" if m["chosen"] else ""
            print(f"    Move:   {m['name']:22} {m['score']:7.3f}{marker}")
        for s in switches:
            marker = " <- CHOSEN" if s["chosen"] else ""
            print(f"    Switch: {s['name']:22} {s['score']:7.3f}{marker}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        battle_id = sys.argv[2] if len(sys.argv) > 2 else None
        analyze_single_battle(battle_id)
    else:
        log_file = sys.argv[1] if len(sys.argv) > 1 else "./battle_logs.json"
        analyze_logs(log_file)
