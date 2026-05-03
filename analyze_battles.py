#!/usr/bin/env python3
"""Analyze battle logs to find decision-making mistakes."""

import json
import sys
from pathlib import Path

def analyze_first_n_turns(log_file: str, n: int = 20) -> None:
    """Print first N turns with decision analysis."""
    with open(log_file) as f:
        data = json.load(f)

    # Handle both single log dict and list of logs
    logs = data if isinstance(data, list) else [data]

    for log_idx, log in enumerate(logs, 1):
        print(f"\n{'='*80}")
        print(f"Battle {log_idx}: {log['our_name']} vs {log['opp_name']}")
        print(f"Winner: {log['winner']} | Turns: {len(log['turns'])}")
        print(f"{'='*80}")

        for turn in log['turns'][:n]:
            t = turn['turn']
            our_mon = turn['our_pokemon']
            opp_mon = turn['opp_pokemon']
            threat = turn.get('active_threat', 0.0)

            # Find best and chosen decisions
            decisions = turn['decisions']
            if not decisions:
                continue

            best = max(decisions, key=lambda d: d['score'])
            chosen = next((d for d in decisions if d['chosen']), best)

            print(f"\nT{t}: {our_mon}({turn['our_hp']:.2f}) vs {opp_mon}({turn['opp_hp']:.2f})")
            print(f"  Threat: {threat:.2f} | State: {turn['strategic_state']}")
            print(f"  Chosen: {chosen['type']} {chosen['name']} (score={chosen['score']:.2f})")

            if chosen != best:
                print(f"  ⚠️  Best was: {best['type']} {best['name']} (score={best['score']:.2f})")
                print(f"      Diff: {best['score'] - chosen['score']:.4f}")

            # Show reasoning if available
            if chosen.get('reasoning'):
                print(f"      Reason: {chosen['reasoning']}")

def print_usage():
    print("""Usage: python analyze_battles.py [--log-file FILE] [--turns N]

Examples:
    python analyze_battles.py
    python analyze_battles.py --log-file ./battle_logs.json --turns 30
    python analyze_battles.py --turns 10  # Show first 10 turns
""")

if __name__ == "__main__":
    log_file = "./battle_logs.json"
    n_turns = 20

    # Parse args
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--log-file" and i < len(sys.argv) - 1:
            log_file = sys.argv[i + 1]
        elif arg == "--turns" and i < len(sys.argv) - 1:
            n_turns = int(sys.argv[i + 1])
        elif arg in ["--help", "-h"]:
            print_usage()
            sys.exit(0)

    if not Path(log_file).exists():
        print(f"❌ Log file not found: {log_file}")
        print_usage()
        sys.exit(1)

    analyze_first_n_turns(log_file, n_turns)
