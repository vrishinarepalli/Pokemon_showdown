# Setting Up Claude Code for ExpecM4 Work

## Quick Start

### 1. In Terminal 1 - Start Pokémon Showdown Server
```bash
cd /home/user/Pokemon_showdown
node pokemon-showdown start --no-security
```
Wait until you see: `Server listening on port 8000`

### 2. In Terminal 2 - Start Claude Code CLI with Context
```bash
cd /home/user/Pokemon_showdown
claude
```

Then paste this at the start:
```
# Pokemon Showdown Battle AI (ExpecM4) - Complete Context

## Current Task
Analyze lost battles to find and fix AI decision-making bugs. Goal: increase win rate from 38% → 60%+.

## Branch & Files
- **Branch**: claude/analyze-repo-structure-jJblQ
- **Main Agent**: PS/bot/agents/expectimax.py (~1900 lines)
- **Database**: PS/bot/data/sets_db.py (threat prediction from randbat movesets)
- **Logger**: PS/bot/agents/battle_logger.py (turn-by-turn decision logging)

## Recent Fixes
1. Sets DB path resolution (repo-relative with fallbacks)
2. Setup move validation (reject if weak to opponent type)
3. Opponent stat boosts in threat prediction
4. Ability-status interactions (Guts, Toxic Boost, Flare Boost)
5. Switch offensive pivot scoring (speed + damage)

## Current Win Rate
~43.6% (target: 60%+)

## Workflow
1. Run battle: `python -m bot.agents.smoke_test_m4 --n-battles 1`
2. Analyze logs: `python analyze_battles.py --turns 20`
3. Identify pattern in logs
4. Fix in expectimax.py
5. Test: `python -m bot.agents.smoke_test_m4 --n-battles 100`
6. Commit: `git add -A && git commit -m "Fix: [description]"` + `git push -u origin claude/analyze-repo-structure-jJblQ`

## Key Files to Watch
- expectimax.py - Lines 540-615 (_eval_move), 631-662 (_eval_setup_move), 1002-1115 (_eval_switch)
- battle_logger.py - Understand log structure before analyzing

## Last Known Issues
- Look at first 20 turns of lost battles for patterns
- Check for: negative-score switches, threat miscalculations, bad type matchups
- Use `python analyze_battles.py` to quickly view decision data
```

### 3. Run Your First Test Battle
```bash
# From PS/ directory
python -m bot.agents.smoke_test_m4 --n-battles 1
```

### 4. Analyze the Logs
```bash
python analyze_battles.py --turns 20
```
This shows first 20 turns with decision scores and reasoning.

## Common Issues & Solutions

### ❌ ConnectionRefusedError: Connect call failed ('127.0.0.1', 8000)
**Solution**: Pokémon Showdown server not running. Start it in a separate terminal:
```bash
node pokemon-showdown start --no-security
```

### ❌ ModuleNotFoundError in expectimax.py
**Solution**: Verify sets database loads correctly:
```bash
python -c "from PS.bot.data.sets_db import get_movepool; print(len(get_movepool('Pikachu'))) > 0"
# Should print: True
```

### ❌ Can't find battle_logs.json
**Solution**: Logs are only created after a successful battle run. Make sure server is running and at least 1 battle completes.

## File Locations (Quick Reference)
```
/home/user/Pokemon_showdown/
├── PS/
│   ├── bot/
│   │   ├── agents/
│   │   │   ├── expectimax.py          # MAIN AGENT (edit here for fixes)
│   │   │   ├── battle_logger.py       # Log structure
│   │   │   └── smoke_test_m4.py       # Battle runner
│   │   └── data/
│   │       ├── sets_db.py             # Sets database loader
│   │       └── gen9_randbat_sets.json # Bundled sets (259KB)
│   └── battle_logs.json               # Generated after each run
├── analyze_battles.py                 # Helper script (in root)
└── SETUP_CLAUDE_CLI.md               # This file
```

## Development Loop
```
1. Identify issue in logs
   ↓
2. Find root cause in expectimax.py code
   ↓
3. Implement fix (test locally with 1 battle)
   ↓
4. Run full test suite (100+ battles)
   ↓
5. Measure win rate improvement
   ↓
6. If >1% improvement: commit and push
   ↓
7. If <1% improvement: revert and try different fix
```

## Tips for Analysis
- **Negative score switches** = forced or miscalculated threat
- **Threat numbers too high/low** = damage calc or movepool prediction is wrong
- **Type matchup mistakes** = AI not considering type weakness
- **Setup moves when in danger** = validation logic needs improvement
- **Bad pivots** = switch evaluation missing something (speed, damage, matchup)

---
**Goal**: Each bug fix should improve win rate by 1-5%. Keep iterating until we hit 60%+.
