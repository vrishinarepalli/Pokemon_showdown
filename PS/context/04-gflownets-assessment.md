# 04 — GFlowNets for Opponent Modeling (assessment: don't)

## The idea (user's)
Use GFlowNets + a NN to "learn how other users play" by training on ≥5k battles,
in the archived ML branch — to model opponents and adapt.

## What GFlowNets actually are
GFlowNets (Bengio 2021) train a NN to **sample diverse objects with probability
proportional to a reward**. Built for *generative* problems (e.g. drug design)
where you want *many diverse good candidates*, not one optimum.

## Verdict: right goal, wrong tool
- What we want is an **opponent model**: estimate `P(opponent action | state)`
  and which archetype they play. That's **density estimation / imitation**, not
  reward-proportional generation. Textbook tools: **behavioral cloning** (NN with
  cross-entropy on observed human moves) or **clustering** behavior features into
  archetypes. Both are simpler, interpretable, converge on less data.
- GFlowNets solve the *opposite* shape (generate diversity from *your own*
  reward). There's no reward-to-be-proportional-to in "predict what the human
  did" — just data to fit. You'd pay GFlowNets' training finickiness
  (flow-matching/trajectory-balance, instability) for nothing.
- **Data killer (any method):** 5k games vs M4/scripted bots have zero archetype
  diversity → you'd just model M4. Opponent modeling only means something on
  **real human data**. So it's premature regardless of architecture.
- Where GFlowNets *could* fit later: generating *diverse teams/strategies* for a
  self-play curriculum — different goal than "learn how users play."

## Recommendation
Keep the goal, drop GFlowNets. At M6, with human logs: **archetype clustering +
behavioral cloning.** Prior art: the **metamon** paper does offline-RL
transformers on Showdown replays — build on that, not GFlowNets. The ML branch
(`archive/pre-ponytail-cleanup`) is preserved for prototyping, but point any
prototype at BC/clustering.

See data sourcing in [05-human-training-and-data.md](05-human-training-and-data.md).
