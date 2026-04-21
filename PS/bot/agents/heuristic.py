"""Heuristic agent for M3.

Picks the move with the highest rough expected damage against the
opponent's active Pokemon, and switches to a better matchup when one
is clearly available.

The scoring is intentionally simple:

    score(move) = base_power * STAB * type_effectiveness * accuracy

No stat reads, no status side-effects, no prediction of opponent
switches. This is the floor the rest of the bot must exceed.

Acceptance: >=95% winrate vs RandomPlayer over 500 games.
"""

from poke_env.environment import MoveCategory
from poke_env.player import Player


STAB_MULTIPLIER = 1.5
STATUS_MOVE_SCORE = 1.0
SWITCH_ADVANTAGE_RATIO = 1.5


class HeuristicAgent(Player):
    def choose_move(self, battle):
        if not battle.available_moves and battle.available_switches:
            return self.create_order(self._best_switch(battle))

        best_move = max(
            battle.available_moves,
            key=lambda m: self._score_move(m, battle),
            default=None,
        )
        best_move_score = (
            self._score_move(best_move, battle) if best_move else 0.0
        )

        if battle.available_switches:
            switch_pokemon, switch_score = self._best_switch_with_score(battle)
            if switch_score > best_move_score * SWITCH_ADVANTAGE_RATIO:
                return self.create_order(switch_pokemon)

        if best_move is None:
            return self.choose_random_move(battle)

        return self.create_order(best_move)

    def _score_move(self, move, battle) -> float:
        if move.category == MoveCategory.STATUS:
            return STATUS_MOVE_SCORE

        base_power = move.base_power or 0
        if base_power <= 0:
            return 0.0

        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if attacker is None or defender is None:
            return float(base_power)

        effectiveness = move.type.damage_multiplier(
            defender.type_1, defender.type_2
        )
        stab = STAB_MULTIPLIER if move.type in attacker.types else 1.0
        accuracy = _accuracy(move)

        return base_power * stab * effectiveness * accuracy

    def _best_switch(self, battle):
        return max(
            battle.available_switches,
            key=lambda p: self._matchup_score(p, battle.opponent_active_pokemon),
        )

    def _best_switch_with_score(self, battle):
        opponent = battle.opponent_active_pokemon
        best = max(
            battle.available_switches,
            key=lambda p: self._matchup_score(p, opponent),
        )
        return best, self._matchup_score(best, opponent)

    def _matchup_score(self, pokemon, opponent) -> float:
        if opponent is None:
            return 0.0

        offense = 0.0
        for move in pokemon.moves.values():
            if move.category == MoveCategory.STATUS:
                continue
            base_power = move.base_power or 0
            if base_power <= 0:
                continue
            eff = move.type.damage_multiplier(opponent.type_1, opponent.type_2)
            stab = STAB_MULTIPLIER if move.type in pokemon.types else 1.0
            offense = max(offense, base_power * stab * eff)

        defense_penalty = 0.0
        for opp_type in (opponent.type_1, opponent.type_2):
            if opp_type is None:
                continue
            eff = opp_type.damage_multiplier(pokemon.type_1, pokemon.type_2)
            defense_penalty = max(defense_penalty, 80.0 * eff)

        return offense - defense_penalty


def _accuracy(move) -> float:
    value = move.accuracy
    if value is True or value is None:
        return 1.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)
