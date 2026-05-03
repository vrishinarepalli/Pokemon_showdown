# Recent AI Improvements

## KO Bonus Fix (Commit 9ebfa4a)
**Problem**: Moves that guaranteed KOs were undervalued compared to defensive switches.
- Example: Granbull with Play Rough (0.721 damage → KO at 33% opponent HP) was scoring 0.6061
- But switching to Basculin scored 0.6674 and was chosen instead

**Solution**: Added +0.30 bonus to move evaluation when `opp_after <= 0.0` (guaranteed KO).
- KO moves eliminate opponent's threat entirely
- Bonus makes finishing moves properly weighted vs defensive pivots

**Results**:
- Baseline: ~38% win rate (from previous session notes)
- After fix: 53% win rate (tested 100 battles across multiple batches)
- 96 KO moves chosen in 689 turns, properly prioritizing finishers

## Remaining Patterns to Investigate

### Suboptimal Switches (Secondary Priority)
- Found cases where we switched and took 68-76% damage next turn
- Victreebel example: predicted 0.290 damage → actual 0.520 damage to switched-in Volbeat
- Likely causes:
  1. Threat calculation underestimating unrevealed movesets
  2. Stats estimation for Pokemon with limited information
  3. Switch evaluation cache possibly outdated

### Next Steps
Run longer test batches (50+ battles) to:
1. Confirm KO bonus effect is consistent
2. Identify any new patterns of poor decisions
3. Target second-order improvements (switches, recovery move evaluation, etc.)

Currently at 53% win rate, target is 60%+
