# Random Battle Bot — v1 Scope

## Purpose

Build an agent that plays Gen 9 Random Battles on Pokemon Showdown
competitively. The existing set predictor becomes one component
(belief state) of a larger decision-making system.

This document captures the v1 scope, the architecture we converged on,
and the reasoning behind each decision. It supersedes the standalone
predictor direction described in `specs_set_predictor.md` for the
purposes of the bot project; the predictor module itself is retained
and reused.

## Non-goals for v1

- Team building. Random Battles generate teams server-side.
- Non-random formats (OU, VGC, etc.). The belief problem is harder
  there and team knowledge is asymmetric; revisit in v2.
- Automated play on the public ladder. Showdown's Terms of Service
  prohibit this; accounts doing it are banned. v1 runs against a
  local `pokemon-showdown` server and, for eval only, in challenge
  battles with consenting opponents.
- Personalized opponent modeling. In randbats most opponents are
  encountered once; per-user profiles have no signal to train on.
- Exploit-the-weak strategies. Playing near-optimally already beats
  weaker opponents; modeling their mistakes adds brittleness without
  meaningful winrate gain.

## Format

- `gen9randombattle`, singles, 6v6.
- Gen 9 mechanics including Terastallization.
- Set distribution is public: `pkmn.github.io/randbats/` mirrors
  `data/random-battles/gen9/sets.json` from the Showdown repo. Every
  Pokemon's candidate moves, items, abilities, tera types, level, and
  EV/IV spreads are enumerated with probabilities.

## Architecture

Six components, separable and independently testable.

### 1. Client layer

Connects to a running `pokemon-showdown` server over WebSocket, the
same protocol the web client uses. Responsible for:

- Authenticating as a throwaway account.
- Joining / creating battles.
- Receiving battle protocol messages.
- Sending `choose move N`, `choose switch N`, `choose team N`, and
  tera decisions.

Implementation: `poke-env` (Python). It wraps the Showdown protocol,
exposes a gym-like environment, and is the standard harness used by
published Pokemon RL agents. DOM automation of the real web client is
explicitly rejected — it is slower by three orders of magnitude and
offers no benefit.

### 2. Belief state

Maintains a posterior over each opponent Pokemon's concrete set.

- Prior: the enumerated sets from the randbats data file, weighted by
  their generation probabilities.
- Update: Bayesian filter over revealed information (moves used,
  ability triggered, item revealed, tera type revealed, damage
  observed). Any set inconsistent with observed data is dropped; the
  remainder is renormalized.
- Output: `P(set | observations)` for each opponent Pokemon, which
  the planner samples from.

The existing Python predictor in `src/set_predictor.py` is adapted
for this module. The formulation shifts from `P(move | pokemon)` to
`P(set | revealed_moves)` — moves that uniquely identify a set
collapse the belief immediately, which the per-move formulation
misses.

Three additional existing modules plug into this component rather
than being rewritten:

- `src/hybrid_predictor.py` wraps `set_predictor.py` with adaptive
  blending between the Bayesian baseline and a learned ML component.
  For v1 we run with ML weight at zero (pure Bayesian); the hybrid
  structure is kept so the ML path can be enabled in v2 without
  restructuring.
- `src/niche_mechanics.py` is a constraint refiner for Gen 9 edge
  cases — Heavy-Duty Boots vs. hazards, Paradox ability gates,
  Booster Energy, forme-locked items, Knock Off interactions. It is
  invoked after each Bayesian update to drop sets that are
  inconsistent with observed behaviour beyond simple move/ability
  matches.
- `src/battle_recorder.py` serialises finalised sets and revealed
  timing into a structured JSON log. It is the training-data feed
  for the value network (M5) and is called from the self-play loop,
  not from the belief update itself.

These modules were authored previously but were never wired
together. The M2 deliverable is that integration — not new
probabilistic code.

### 3. Simulator

Rolls out hypothetical turns for the planner. We do not write one.
Options:

- `@pkmn/sim` (TypeScript) — Showdown's actual engine repackaged as
  a library. Authoritative.
- `poke-env`'s built-in battle simulation via a subprocess
  `pokemon-showdown` binary. Same engine, Python-accessible.

Decision: use `poke-env`'s subprocess approach for v1. Same fidelity,
no cross-language bridge.

### 4. Opponent model

Outputs `P(opponent_action | state)` for the planner's expectation.

- v1: heuristic. Assume the opponent picks the move with highest
  expected damage against our active Pokemon, and switches when
  expected incoming damage exceeds a threshold (e.g. 50% of current
  HP). This matches roughly 80% of competent ladder players'
  behavior in randbats.
- v2: learned policy prior, trained from self-play trajectories.

`src/next_move_predictor.py` provides the scaffolding for this
component — a move-scoring framework with threat, defensive,
momentum, and game-theory axes. The framework is retained; the
scoring functions inside it are stubs and will be replaced with the
v1 heuristic. `src/damage_calculator.py` supplies the Gen 9 damage
formula used by the threat term.

### 5. Planner

Given our state, the belief over opponent sets, and the opponent
model, selects our action.

- v1: expectimax, depth 1. For each of our legal actions, sample N
  opponent sets from the belief, for each sampled set compute the
  expected next state under the opponent model (including damage
  rolls), score leaves with the value function, return the action
  with highest expected value.
- v2: MCTS with deeper rollouts and PUCT selection guided by a
  learned policy prior. AlphaZero-shaped.

### 6. Value function

Estimates `V(state) = P(win | state)`.

- v0 (bootstrap): hand-crafted evaluation — HP differential across
  both teams, hazards, boosts, speed control, status, Pokemon
  remaining. Used to train the first iteration of the planner.
- v1: neural network trained by self-play. State encoding includes
  both teams' revealed info, our hidden info, field conditions, and
  turn number. Train by regression on episode outcomes (Monte Carlo
  return) with TD bootstrapping for variance reduction.

## Training pipeline

Self-play in a local server, not on ladder. Ladder is used for final
evaluation only.

Curriculum, in order. Each stage must beat the previous one before
we advance; if it does not, the bug is in the current stage, not
the next.

1. **Random agent baseline.** Picks legal moves uniformly. Floor.
2. **Heuristic agent.** Max expected damage, simple switch rules.
   Must beat random ≥95%.
3. **Expectimax + hand-crafted value function.** Must beat the
   heuristic with meaningful margin.
4. **Self-play with learned value network.** Train on games between
   past versions. Must beat the hand-crafted evaluator.
5. **Policy network added as planner prior.** AlphaZero-style
   iteration.

Rationale for curriculum: it gives concrete acceptance tests at each
step, prevents silent regressions, and avoids the common failure
mode of training a learned agent end-to-end with no baseline to
compare against.

## Milestones

| M  | Deliverable                                              | Acceptance                                              |
| -- | -------------------------------------------------------- | ------------------------------------------------------- |
| M1 | Local server + poke-env harness + throwaway alt          | Two poke-env scripted agents complete a battle locally (complete) |
| M2 | Belief state module — integrate hybrid_predictor, niche_mechanics, battle_recorder behind a single interface | Posterior collapses to correct set within 3 revealed moves on recorded games |
| M3 | Heuristic agent                                          | ≥95% winrate vs random agent over 500 games (complete, 98.6%) |
| M4 | Expectimax planner + hand-crafted value function         | ≥60% winrate vs M3 over 500 games                       |
| M5 | Value network, self-play training loop, eval harness     | ≥60% winrate vs M4 over 500 games                       |
| M6 | Policy prior + MCTS                                      | ≥55% winrate vs M5 over 500 games                       |

Winrates are measured at statistically significant sample sizes; 500
games gives roughly ±4% confidence at 95%.

## Explicit design decisions and why

- **No database for set data.** The randbats set file is ~1 MB of
  JSON. In-memory is faster, simpler, and sufficient. A DB is only
  warranted if we start aggregating game logs at scale; that belongs
  in v2.
- **Do not condition training on opponent rating.** Elo is a
  matchmaking signal, not a feature. A 1000-rated opponent may be a
  new account, a tanked alt, or an experienced player on a fresh
  account. Rating has too much variance per-game to be useful.
  Self-play sidesteps this entirely.
- **Do not train on ladder games.** Slow (one game per few minutes),
  ToS-violating, and produces a non-stationary opponent distribution
  that is hard to learn from. Self-play gives us millions of games
  and a known opponent distribution.
- **Belief state is separate from the value function.** Belief is a
  pure probabilistic update from observations; value is a learned
  estimator over full states. Mixing them conflates model and
  evaluator and makes debugging harder.
- **Heuristic opponent model before learned one.** A learned
  opponent model requires trajectories to train, which requires a
  planner, which requires an opponent model. Heuristic breaks the
  circular dependency.

## Risks

- **Simulator fidelity.** Mitigated by using Showdown's own engine.
  If we see behavior divergence vs. the real site, the engine is
  likely correct and our interpretation of a log is wrong.
- **Training cost.** Self-play is cheap per game (seconds) but a
  useful value network may need 10^5–10^6 games. Budget CPU
  accordingly; no GPU required for the sim, only for the network.
- **ToS.** Eval on ladder must be manual or via consenting challenge
  battles. Do not wire the agent into an automated ladder loop.
- **Distribution shift between self-play and ladder.** Human
  opponents play differently than past selves. Expected; reported as
  an eval delta rather than a training signal.

## Out of scope, tracked for later

- Non-random formats.
- Opponent-specific adaptation within a session.
- Team preview lead selection beyond a simple heuristic.
- Tera timing optimization beyond a learned policy's native handling.
- Browser extension deployment. The existing extension remains as
  the predictor-overlay product; the bot is a separate artifact.

## Repository layout (planned)

Current code is retained. New bot code will live under `PS/bot/`:

```
PS/
  bot/
    client/        # poke-env wrapper, auth, matchmaking
    belief/        # set posterior (adapts src/set_predictor.py)
    agents/
      random.py
      heuristic.py
      expectimax.py
      learned.py
    value/         # hand-crafted and learned value functions
    training/      # self-play loop, curriculum, eval harness
    data/          # randbats sets, cached game logs
  src/             # existing predictor (reused by belief/)
  extension/       # existing predictor overlay (unchanged)
```

## Open questions

- Whether to standardize on Python end-to-end or move the planner to
  TypeScript alongside `@pkmn/sim`. Default: Python via poke-env.
  Revisit if the subprocess bridge becomes a performance bottleneck.
- Whether to use PPO-style policy-gradient training or AlphaZero-style
  search-and-update. Default: AlphaZero shape, since the value
  function is already central to the planner.
- State encoding for the value network. Deferred until M5 design.
