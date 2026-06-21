# Online Bot Research Notes

Date: 2026-05-21

Context: Current local M4 benchmark is 49/100 wins (49.0%) for
`ExpectimaxAgent` vs `HeuristicAgent`, below the M4 target of >=60% over
500 games. Battle-log analysis showed a high early switch rate:
89/200 first-two-turn decisions were switches (44.5%).

## Sources Reviewed

- Foul Play: https://pmariglia.github.io/posts/foul-play/
- Foul Play repo: https://github.com/pmariglia/foul-play
- poke-env docs/repo: https://poke-env.readthedocs.io/ and https://github.com/hsahovic/poke-env
- Randbats data: https://pkmn.github.io/randbats/
- PokéChamp repo/paper: https://github.com/sethkarten/pokechamp and https://arxiv.org/abs/2503.04094
- PokeLLMon paper: https://arxiv.org/abs/2402.01118

## Relevant Lessons

### 1. Panic Switching Is A Known Failure Mode

PokeLLMon explicitly calls out "panic switching" as a behavior to mitigate.
Our local logs show the same shape: M4 switches in 44.5% of first-two-turn
decisions. That is likely too high when the active Pokemon is not in immediate
KO danger.

Potential implementation:

- Add a switch gate in `ExpectimaxAgent.choose_move` after all move/switch
  candidates are scored.
- Require a switch to beat the best move by a margin unless:
  - the active Pokemon is likely KO'd this turn,
  - the switch-in is immune or hard-resists the predicted attack,
  - the switch-in gets a clear revenge/KO advantage next turn,
  - no usable move is available.
- Make the margin larger on turns 1-2 and in `SAFE` context.

### 2. Strong Bots Treat Set Prediction As Core, Not Optional

Foul Play says set prediction is as important as search, especially in random
formats where possible sets are constrained. It filters candidate sets using
battle observations, then samples plausible complete battle states before
searching.

Potential implementation:

- Wire `bot/belief/state.py` and `bot/data/sets_db.py` deeper into
  `ExpectimaxAgent`, not just into logging/tracking.
- When scoring opponent damage, use likely randbat moves from the set DB if
  revealed moves are incomplete.
- Weight opponent threat by posterior probability instead of using only
  revealed moves or generic synthetic baseline.

### 3. Hidden-Information Events Should Update Item/Stat Beliefs

Foul Play lists several inference rules that directly improve play:

- Damage dealt/taken narrows opponent stats.
- Move order reveals speed bounds when priority is equal.
- Extended weather reveals weather-extension items.
- Status moves rule out Assault Vest.
- Hazard damage rules out Heavy-Duty Boots.

Potential implementation:

- Record hazard-damage/no-hazard-damage events in the battle logger/tracker.
- Mark Assault Vest impossible when opponent uses a status move.
- Track speed-bound evidence after same-priority move order.
- Use these constraints when estimating opponent damage and when choosing
  switch-ins.

### 4. Search Should Model Simultaneous Moves

Foul Play moved away from naive expectiminimax because Pokémon actions are
selected simultaneously. Its MCTS variant handles simultaneous choices and
samples likely branches. PokéChamp also treats minimax-style search as a core
algorithmic component.

Potential implementation:

- Near term: keep depth-1 expectimax, but score move-vs-move pairs rather than
  "we act, then opponent reacts."
- Medium term: add a small sampled policy matrix for our legal actions vs the
  opponent's likely actions, then choose by robust expected value.
- Long term: consider integrating `poke-engine` or writing a lightweight MCTS
  around this repo's current value function.

### 5. Randbat Data Should Be Fresh And First-Class

The pkmn randbats project generates random-battle set options from Pokemon
Showdown and exposes JSON at `https://data.pkmn.cc/randbats/`. This is likely
more relevant to M4 than OU usage data because the benchmark format is
`gen9randombattle`.

Potential implementation:

- Add a data update script for `gen9randombattle` sets from pkmn randbats.
- Prefer randbat set options over `gen9ou` usage data in M4.
- Add a data-health check so empty `data/pokemon/*.json` files cannot silently
  break calculators/tests.

## Priority Order For This Repo

1. Add a conservative switch gate and rerun 100/500 battles.
2. Fix benchmark hygiene: keep `.venv`, add missing `tqdm`, and avoid scripts
   that run `git pull` as part of tests.
3. Add data-health checks for empty Pokemon/move/item/ability JSON.
4. Use randbat set DB for unrevealed move/threat estimation.
5. Add belief updates for Heavy-Duty Boots, Assault Vest, and speed bounds.
6. Revisit search architecture only after the switch gate and set-data fixes
   are measured.

## Current Measurement To Beat

- 20 battles: 12/20 wins (60.0%)
- 100 battles: 49/100 wins (49.0%)
- M4 acceptance: >=60% over 500 battles vs M3

## Competitive Strategy Research Addendum

Additional sources:

- Smogon Gen 7 Randbats guide: https://www.smogon.com/articles/randbats-beginners-guide
- Smogon Gen 8 Randbats guide: https://www.smogon.com/articles/randbats-guide-gen8
- Smogon expert randbats article: https://www.smogon.com/smog/issue35/randbats-expert
- Gen 9 Random Battles mechanics thread: https://www.smogon.com/forums/threads/questions-about-how-random-battles-formats-work-read-here.3712694/
- Random Battles level balancing: https://www.smogon.com/forums/threads/random-battles-level-balancing.3721211/
- Percymon AI report: https://varunramesh.net/content/documents/cs221-final-report.pdf
- Smogon Development overview: https://dev.smogon.com/

### 1. Build A Win-Condition Model, Not Just A Turn Evaluator

Smogon randbats guides repeatedly frame mid-game play around identifying the
team's win condition: preserve likely sweepers, weaken their checks, and avoid
revealing or sacrificing them too early. Our current `_mon_value` is mostly HP
and Speed, so it can undervalue a slow bulky setup mon or overvalue a fast but
low-impact attacker.

Potential implementation:

- Add a `wincon_score(pokemon, battle)` helper.
- Boost score for setup moves, strong STAB coverage, priority, recovery,
  speed-boosting moves, Beast Boost/Moxie-style abilities, Unaware, and high
  late-game matchup value.
- Penalize using a high wincon-score Pokemon as a sacrifice or blind switch.
- In late game, reward lines that keep the wincon healthy even if immediate
  HP-exchange score is slightly worse.

### 2. Separate "Switch To Preserve" From "Switch To Scout"

Smogon advice says switching is correct in bad lead matchups, but not if the
opponent can freely set up. Our bot should not treat every bad damage trade as
an automatic switch. It needs to distinguish:

- preserve a high-value active mon from a clear KO,
- pivot into an immunity/resist,
- scout a locked/uncertain attack,
- avoid giving a setup sweeper a free turn.

Potential implementation:

- Add a `switch_reason` classifier in `_eval_switch`.
- Only permit scouting switches when the switch-in survives and the active mon
  is valuable or has no useful status/damage option.
- If the opponent has setup moves likely by role or revealed set, increase the
  cost of switching unless the switch-in immediately threatens it.

### 3. Hazards Are Often Worth More In Randbats Than The Current Bot Assumes

Multiple Smogon guides emphasize hazards as central in Random Battles because
removal is scarce and many attacks nearly KO but need chip to finish. The
current hazard evaluator already exists, but it can be more strategic.

Potential implementation:

- Increase Stealth Rock value when:
  - opponent has unrevealed Pokemon,
  - we have U-turn/Volt Switch/Flip Turn/Parting Shot,
  - we have multiple fast attackers that benefit from chip,
  - opponent has revealed or likely Flying/Fire/Ice/Bug threats.
- Avoid second Spikes layer unless we already have momentum or the opponent
  cannot punish setup; Smogon notes the first and third layers are often more
  strategically meaningful than the second.
- Toxic Spikes should check known or possible grounded Poison-types before
  overvaluing.

### 4. Status Is A Strategic Resource, Not A Low-Damage Move

Expert randbats advice values burn, Toxic, and paralysis because they break
bulky Pokemon and swing speed tiers. Our status evaluator should be matchup-
and game-plan-aware.

Potential implementation:

- Burn physical attackers and bulky wincons more aggressively.
- Toxic bulky recovery Pokemon and walls when direct damage cannot 2HKO.
- Paralysis should be valued when it lets our team outspeed or enables
  flinch/slow-wallbreaker lines.
- Do not status into likely Magic Bounce, Guts, Poison Heal, RestTalk, or
  already-statused targets.

### 5. Use Randbat Role Mechanics Directly

The Gen 9 mechanics thread says each Pokemon can have one to three roles, and
roles define separate movepools, forced moves, and item behavior. This is more
useful than a flat "possible moves" list.

Potential implementation:

- Ingest `sets.json` / pkmn randbats data with role labels.
- Maintain role posterior per opponent Pokemon.
- When a move is revealed, eliminate roles that cannot contain it.
- Threat scoring should use role-conditioned move probabilities.
- If role implies Setup Sweeper, treat free turns as dangerous; if role implies
  Fast Attacker, expect immediate damage or Choice Scarf possibilities.

### 6. Speed Tiers Are Mostly Deterministic In Randbats

Randbats uses neutral natures and mostly 85 EVs, with exceptions for special
attackers and Gyro Ball/Trick Room users. Guides emphasize that Speed tiers are
memorable and visible from levels/tooltips.

Potential implementation:

- Replace rough speed estimates with randbat-specific level/stat calculation.
- Track speed-bound evidence from same-priority move order.
- Value paralysis, Sticky Web, and speed-boosting setup based on whether they
  change specific matchups, not as a generic bonus.
- Add a "revenge kill map": which team members outspeed and KO each revealed
  opponent after hazards.

### 7. KO Timing Matters

The Gen 8 guide warns that taking an easy KO can be bad if it gives a dangerous
backline Pokemon a free setup opportunity. Current evaluation rewards KOs
heavily without enough "what comes in next?" modeling.

Potential implementation:

- Before choosing a KO, estimate the worst opposing switch-in after the KO.
- If the KO move locks us, drops stats, or leaves us setup fodder, compare with
  status/hazard/pivot alternatives.
- Reward KOs more when our active can threaten likely revenge switch-ins.

### 8. Evaluation Should Include Benchmark Buckets

Smogon level balancing uses winrate statistics and confidence thresholds rather
than single-game impressions. We should do the same for bot changes.

Potential implementation:

- Run every change at 100 battles first, then 500 if promising.
- Save metrics by category:
  - early switch rate,
  - forced vs voluntary switches,
  - setup moves used and resulting winrate,
  - hazards set by turn 5,
  - status used vs bulky targets,
  - losses after taking a KO.
- Treat a change as promising only if it improves winrate and at least one
  diagnostic metric without causing a clear regression.

### 9. Older AI Work Supports Deeper Search With Strong Evaluation

Percymon used depth-2 minimax against greedy baselines, while Technical Machine
used expectiminimax with a weighted evaluation and transposition table. This
supports keeping M4's handcrafted evaluator, but improving branch quality and
state reuse before jumping to full RL.

Potential implementation:

- Add action pruning: top damaging moves, best status, best hazard, top 1-2
  switches.
- Search two plies only on high-impact turns: setup threat, likely KO, forced
  switch, or late-game wincon.
- Cache damage and state evaluations more aggressively.

## Updated Highest-Leverage Roadmap

1. Add conservative switch gate and classify switch reasons.
2. Add wincon scoring and preserve likely sweepers.
3. Load Gen 9 randbat role/set data and use it for opponent threat estimates.
4. Improve hazard/status valuation using randbats-specific strategy.
5. Add speed-tier and revenge-kill maps.
6. Add KO timing / next-switch-in penalty.
7. Run measured 100-battle and 500-battle benchmarks after each change.
