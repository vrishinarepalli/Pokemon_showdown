"""Hand-crafted value function V(state) for M4.

Returns a scalar in [-1, 1]; positive values mean we are winning.

Terms (weighted sum):
  - Active HP exchange after a simulated turn  (0.35)
  - Team-wide average HP differential          (0.25)
  - Pokemon count differential                 (0.20)
  - Stat-boost differential on active Pokemon  (0.10)
  - KO bonus for eliminating opponent           (+0.15 when opp HP hits 0)

The weights are deliberately conservative. The value function exists to
rank actions, not to produce a calibrated win probability — calibration
is the job of the learned network in M5.
"""

_UNKNOWN_OPP_HP = 1.0  # unseen opponent Pokemon assumed at full HP


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

        total = (
            0.40 * (our_hp_after - opp_hp_after)
            + 0.25 * _team_hp_diff(battle)
            + 0.20 * _count_diff(battle)
            + 0.10 * _boost_diff(battle)
            + ko_term
        )
        return max(-1.0, min(1.0, total))


def _team_hp_diff(battle) -> float:
    our_hp = sum(p.current_hp_fraction for p in battle.team.values() if not p.fainted)
    our_alive = sum(1 for p in battle.team.values() if not p.fainted)
    our_avg = our_hp / max(our_alive, 1)

    revealed = list(battle.opponent_team.values())
    their_alive_hp = sum(p.current_hp_fraction for p in revealed if not p.fainted)
    their_fainted = sum(1 for p in revealed if p.fainted)
    their_unknown = 6 - len(revealed)
    their_total = their_alive_hp + their_unknown * _UNKNOWN_OPP_HP
    their_alive_count = max(6 - their_fainted, 1)
    their_avg = their_total / their_alive_count

    return our_avg - their_avg


def _count_diff(battle) -> float:
    ours = sum(1 for p in battle.team.values() if not p.fainted)
    their_fainted = sum(1 for p in battle.opponent_team.values() if p.fainted)
    theirs = 6 - their_fainted
    return (ours - theirs) / 6.0


def _boost_diff(battle) -> float:
    our_b = battle.active_pokemon.boosts if battle.active_pokemon else {}
    opp_b = battle.opponent_active_pokemon.boosts if battle.opponent_active_pokemon else {}
    useful = ("atk", "spa", "spe")
    ours = sum(our_b.get(k, 0) for k in useful)
    theirs = sum(opp_b.get(k, 0) for k in useful)
    return (ours - theirs) * 0.1
