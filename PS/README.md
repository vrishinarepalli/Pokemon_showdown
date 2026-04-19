# Pokemon Showdown Bot

A playing agent for Pokemon Showdown. The initial target is Gen 9
Random Battles. The project combines three layers: a belief state over
the opponent's hidden information, a search-based planner, and a
learned value function trained by self-play.

An earlier phase of this repository produced a real-time set
predictor as a Chrome extension. That predictor is retained and
reused as the belief-state component of the bot.

## Project direction

- **v1** — Random Battle agent, trained by self-play against a local
  `pokemon-showdown` server, evaluated offline and in manual challenge
  battles. Scope, milestones, and design rationale are in
  [`specs_bot_v1.md`](specs_bot_v1.md).
- **Set predictor (existing)** — Python module under `src/` and
  Chrome extension under `extension/`. Documented in
  [`specs_set_predictor.md`](specs_set_predictor.md). Still usable as
  a standalone product; also feeds the bot's belief state.
- **Team generator** — earlier direction, archived. See
  [`specs.md`](specs.md).

Automated play on the public ladder is out of scope. Showdown's Terms
of Service prohibit it; the bot is developed and evaluated against a
local server and consenting opponents in challenge battles.

## Architecture at a glance

```
  WebSocket                belief state              planner
  to local      ---->      over randbats     ---->   expectimax /
  Showdown                 sets (Bayes)              MCTS
  server
                                                       |
                                                       v
                                                  value function
                                                  (hand-crafted -> NN)
```

The client layer connects to Showdown using `poke-env`. The belief
module adapts the existing predictor to operate on Random Battle set
data published by the Showdown team. The simulator used for rollouts
is Showdown's own engine, accessed through `poke-env`.

## Repository layout

```
PS/
  specs_bot_v1.md            v1 scope and design rationale
  specs_set_predictor.md     predictor component spec
  specs.md                   archived team generator plan
  TESTING.md                 test guide

  src/                       Python predictor (reused as belief state)
    data_fetcher.py
    data_manager.py
    pokemon_data_parser.py
    set_predictor.py

  data/                      cached datasets
    pokemon/                 pokedex, moves, abilities, items
    usage/                   Smogon usage statistics

  extension/                 Chrome extension (predictor overlay)
    background/
    content/
    lib/
    popup/
    manifest.json

  bot/                       planned, see specs_bot_v1.md

  convert_data_to_js.py      bakes data/ into extension/lib/
  update_data.py             refreshes Smogon usage data
  test_scenarios.py          predictor test harness
  requirements.txt           Python dependencies
```

The `bot/` tree is described in `specs_bot_v1.md`; it is added as
each milestone is implemented rather than stubbed up front.

## Status

| Component             | Status                |
| --------------------- | --------------------- |
| Data pipeline         | Complete              |
| Set predictor (lib)   | Complete              |
| Chrome extension      | Complete              |
| Bot v1 design         | Complete (this doc)   |
| Bot v1 milestones     | Not started           |

## Installation

### Predictor / extension

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python convert_data_to_js.py
```

Load `extension/` as an unpacked extension from
`chrome://extensions/`.

### Bot

The bot connects to a local `pokemon-showdown` server over WebSocket.
It does not automate the public ladder.

Install the server (one-time):

```bash
git clone https://github.com/smogon/pokemon-showdown ~/pokemon-showdown
cd ~/pokemon-showdown
npm install
```

Install Python dependencies (already included in `requirements.txt`):

```bash
pip install -r requirements.txt
```

Run the M1 smoke test. In one shell, start the server:

```bash
cd ~/pokemon-showdown
node pokemon-showdown start --no-security
```

`--no-security` disables authentication so any username connects
without a password. In a second shell, from this repository's `PS/`
directory:

```bash
python -m bot.client.smoke_test
```

A single `gen9randombattle` runs between two random agents; the
script prints the result. This confirms the harness is functional
and is the acceptance test for M1.

## Documentation

- [`specs_bot_v1.md`](specs_bot_v1.md) — bot v1 scope, architecture,
  milestones, design rationale.
- [`specs_set_predictor.md`](specs_set_predictor.md) — predictor
  component specification.
- [`specs.md`](specs.md) — archived team generator direction.
- [`TESTING.md`](TESTING.md) — predictor test guide.
