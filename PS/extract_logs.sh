#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: ./extract_logs.sh <turn_number>"
  echo "Example: ./extract_logs.sh 7"
  exit 1
fi

TURN=$1
START_TURN=$(( TURN - 2 ))
if [ $START_TURN -lt 1 ]; then
  START_TURN=1
fi
END_TURN=$(( TURN + 2 ))

python3 << EOF
import json

with open('battle_logs.json', 'r') as f:
    logs = json.load(f)

latest_battle = logs[-1] if logs else None
if not latest_battle:
    print("No battles logged")
    exit()

relevant_turns = [t for t in latest_battle.get('turns', []) if $START_TURN <= t.get('turn', 0) <= $END_TURN]

print(json.dumps(relevant_turns, indent=2))
EOF
