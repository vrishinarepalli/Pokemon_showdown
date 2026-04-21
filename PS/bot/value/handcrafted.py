"""Hand-crafted value function V(state) for M4.

Returns a scalar in [-1, 1]; positive values mean we are winning.

Depth-1 expectimax only compares the direct outcomes of candidate actions
from the same battle state, so terms that are constant within a turn
(team HP, count, boosts) do not affect the argmax. The value function
therefore focuses on what actually changes action-to-action: the active
HP exchange and whether a KO was secured.
"""


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
        """
        our_hp_after = max(0.0, min(1.0, our_hp_after))
        opp_hp_after = max(0.0, min(1.0, opp_hp_after))

        # Only bonus for KO'ing the opponent — no penalty for getting KO'd.
        # The HP differential term already captures the cost of dying. Adding
        # an extra penalty causes depth-1 search to incorrectly avoid trading
        # a low-HP mon for significant damage dealt, since it can't see the
        # follow-up turn where a fresh switch-in finishes the job.
        ko_term = 0.15 if opp_hp_after <= 0.0 else 0.0

        total = (our_hp_after - opp_hp_after) + ko_term
        return max(-1.0, min(1.0, total))
