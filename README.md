# Pokemon Showdown AI

A competitive AI agent for Gen 9 Random Battles on Pokemon Showdown, built from scratch in Python. The bot plays full battles autonomously, making real-time decisions under partial information using a custom game tree search, Bayesian belief tracking, and mid-game opponent modeling.

---

## What it does

The bot connects to a local Pokemon Showdown server via WebSocket and plays Gen 9 Random Battles end-to-end. Each turn it:

1. **Updates its belief state** — prunes the set of possible opponent builds using Bayesian inference over the official randbat set database (moves revealed, ability triggered, item inferred)
2. **Models the opponent** — predicts whether the opponent will attack or switch, and which Pokemon they'll bring in, using matchup scoring and learned per-battle pivot patterns
3. **Runs a depth-1 expectimax search** — evaluates every legal move and switch against the predicted opponent response, scoring by HP exchange, KO probability, hazard value, setup payoff, and sacrifice plays
4. **Picks the best action** — with tiebreakers for STAB, priority, and near-KO finishes

---

## Technical highlights

| Area | Detail |
|------|--------|
| **Search** | Depth-1 expectimax with opponent action prediction |
| **Belief state** | Bayesian set pruning over 500+ randbat species; revealed moves/abilities/items narrow the posterior each turn |
| **Opponent modeling** | Tracks per-matchup switch-in history mid-battle; predicts pivots like "clodsire always comes in on jolteon" |
| **Damage model** | Full Gen 9 damage formula — STAB, type effectiveness, stat stages, abilities (Water Absorb, Contrary, Guts, etc.), accuracy, priority |
| **Strategic context** | Classifies each turn as SAFE / TRADEOFF / DANGER and adjusts aggressiveness, setup willingness, and sacrifice logic accordingly |
| **Hazard & setup eval** | Values Stealth Rock / Spikes by team size remaining; evaluates Swords Dance / Nasty Plot with 2-turn rollout |
| **Forced-switch logic** | Picks the best replacement on KOs using type matchup, ability bonuses, and hazard cost |
| **Debug tooling** | Per-turn JSON decision logs with scores, reasoning strings, and predicted opponent damage for every candidate action |

---

## Architecture

```
WebSocket client (poke-env)
        |
        v
 Belief state update          OppTeamTracker
 (Bayes set pruning)     <-->  - revealed moves/abilities
        |                      - switch-in history
        v
 Strategic context
 (threat assessment, opp action prediction)
        |
        v
 Expectimax planner
 (move eval + switch eval)
        |
        v
 Value function
 (HP exchange score, KO bonus, hazard penalty)
```

### Key files

```
PS/bot/agents/expectimax.py      Core decision engine (~2200 lines)
PS/bot/agents/battle_logger.py   Per-turn debug log writer
PS/bot/belief/state.py           Bayesian belief state
PS/bot/data/opp_tracker.py       Opponent team + pivot pattern tracker
PS/bot/value/handcrafted.py      Hand-crafted value function
PS/bot/agents/heuristic.py       Rule-based opponent agent (for self-play)
```

---

## Getting started

### Requirements

- Python 3.10+
- Node.js (for local Showdown server)

### Install

```bash
# Clone and install Python deps
cd PS
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Install local Showdown server (one-time)
npm install
```

### Run a battle

Start the server in one terminal:
```bash
node node_modules/pokemon-showdown/pokemon-showdown start --no-security
```

Run the bot in another:
```bash
cd PS
python -m bot.agents.smoke_test_m4
```

### Run tests

```bash
cd PS && ./run_tests.sh
```

---

## Debugging

Use `newbug <turn>` in your shell to capture the full decision log for a turn into a `debug<n>.txt` file (scores, reasoning, predicted opponent damage for every candidate action). Use `rmdebug <n>` to clean up.

---

## Project layout

```
PS/                     Main Python project
  bot/                  Bot package
    agents/             Planners (expectimax, heuristic), logger, debug
    belief/             Bayesian belief state
    data/               Opponent tracker, randbat sets database
    value/              Value function
    client/             WebSocket client wrapper
  src/                  Chrome extension set predictor (standalone)
  extension/            Chrome extension UI
  data/                 Pokedex, moves, abilities, usage stats
  docs/                 Design docs, specs, architecture notes
  tests/                Test suite
package.json            Pokemon Showdown server dependency
```
