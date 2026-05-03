# Pokemon Showdown AI Bot

A Gen 9 Random Battle agent for Pokemon Showdown. The bot uses a depth-1 expectimax planner backed by a hand-crafted value function, a Bayesian belief state over the opponent's hidden team, and per-battle adaptive logic that learns the opponent's patterns mid-game.

---

## How it works

```
Showdown server  -->  poke-env client  -->  Belief state  -->  Expectimax planner
  (WebSocket)                                (Bayes over                |
                                              randbat sets)        Value function
                                                                   (handcrafted)
```

- **Belief state** (`bot/belief/`) — Tracks revealed moves, abilities, and items each turn. Prunes the set of possible builds using the official Showdown random battle data.
- **Planner** (`bot/agents/expectimax.py`) — Depth-1 expectimax over all moves and switches. Evaluates type matchups, speed tiers, hazards, setup moves, sacrifice plays, and mid-game adaptation (switch-in pattern learning, stat-boost tracking).
- **Opponent tracker** (`bot/data/opp_tracker.py`) — Records which opponent Pokemon switch in against each of our active Pokemon, letting the bot predict pivots like "clodsire always comes in on jolteon."
- **Value function** (`bot/value/handcrafted.py`) — Scores the HP exchange after each simulated turn. Non-linear penalty for damage taken, reward for damage dealt, KO bonuses.

---

## Repository layout

```
PS/
  bot/                       Main bot package
    agents/
      expectimax.py          Core decision engine (move + switch evaluator)
      heuristic.py           Opponent agent (used in self-play)
      battle_logger.py       Per-turn debug logging
      debug.py               In-game state printer
    belief/
      state.py               Bayesian belief state over opp sets
    data/
      opp_tracker.py         Per-battle opponent team + pattern tracker
      sets_db.py             Randbat sets database interface
    value/
      handcrafted.py         Hand-crafted value function
    client/                  WebSocket client (poke-env wrapper)
    training/                Self-play training harness

  src/                       Chrome extension predictor (standalone)
  extension/                 Chrome extension UI
  data/                      Cached Pokedex, moves, abilities, usage stats
  tests/                     Test suite
  docs/                      Design docs, specs, architecture notes

  requirements.txt           Python dependencies
  run_tests.sh               Run test suite
  extract_logs.sh            Extract battle logs for a specific turn
```

---

## Getting started

### Prerequisites

- Python 3.10+
- A local [Pokemon Showdown](https://github.com/smogon/pokemon-showdown) server

### Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run the local Showdown server

```bash
git clone https://github.com/smogon/pokemon-showdown ~/pokemon-showdown
cd ~/pokemon-showdown && npm install
node pokemon-showdown start --no-security
```

### Run a smoke test battle

```bash
python -m bot.agents.smoke_test
```

This runs a single Gen 9 Random Battle and prints the result. Use it to confirm everything is wired up correctly.

### Run the test suite

```bash
./run_tests.sh
```

---

## Debugging

Use `newbug <turn>` in your shell to capture the decision log for a specific turn into a numbered `debug<n>.txt` file. Use `rmdebug <n>` to clean up debug files 1 through n.

Both commands are defined in `~/.zshrc`. See `extract_logs.sh` for the underlying log extraction.

---

## Design docs

Full specs, architecture notes, and feature write-ups are in [`docs/`](docs/).
