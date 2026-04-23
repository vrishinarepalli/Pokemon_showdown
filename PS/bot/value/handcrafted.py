"""Hand-crafted value function V(state) for M4.

Returns a scalar in [-1, 1]; positive values mean we are winning.

Depth-1 expectimax only compares the direct outcomes of candidate actions
from the same battle state, so terms that are constant within a turn
(team HP, count, boosts) do not affect the argmax. The value function
therefore focuses on what actually changes action-to-action: the active
HP exchange and whether a KO was secured.
"""

import math


class HandcraftedValue:
    def score_transition(
        self,
        battle,
        our_hp_after: float,
        opp_hp_after: float,
    ) -> float:
        """Score the battle state after one simulated turn of damage exchange.

        our_hp_after  : estimated HP fraction of our active Pokemon after the turn.
        opp_hp_after  : estimated HP fraction of opponent active Pokemon after the turn.
        Both values are clamped to [0, 1] internally.

        Non-linear HP-lost penalty:
        - 0-55% damage taken: log-shaped mild penalty (mon is healthy, small impact)
        - 55-100% damage taken: linear steep penalty (entering danger zone)
        - KO (100%): major red flag penalty
        """
        our_hp_after = max(0.0, min(1.0, our_hp_after))
        opp_hp_after = max(0.0, min(1.0, opp_hp_after))

        # Our HP penalty (non-linear)
        our_hp_lost = 1.0 - our_hp_after
        if our_hp_lost <= 0.55:
            # Log-shaped mild penalty for 0-55% damage
            # log(1) = 0, log(1.55) ~ 0.44
            our_penalty = -math.log(1 + our_hp_lost) * 0.35
        else:
            # Linear steep past 55%
            transition_penalty = -math.log(1.55) * 0.35  # Value at threshold
            beyond = (our_hp_lost - 0.55) / 0.45
            our_penalty = transition_penalty + (-0.55 * beyond)

        # Opponent HP reward (linear, we want to reduce it)
        opp_reward = 1.0 - opp_hp_after

        # KO bonus for finishing the opponent
        ko_bonus = 0.2 if opp_hp_after <= 0.0 else 0.0

        # Major red flag if we get KO'd
        self_ko_penalty = -0.15 if our_hp_after <= 0.0 else 0.0

        total = our_penalty + opp_reward + ko_bonus + self_ko_penalty
        return max(-1.0, min(1.0, total))
