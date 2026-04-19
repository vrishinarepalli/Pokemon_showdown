"""Opponent belief state over hidden Pokemon set information.

Wraps the existing `HybridSetPredictor` and `NicheMechanicsDetector`
behind a single interface the bot's planner can call. One BeliefState
instance per battle; it holds one SetPrediction per opponent Pokemon
and updates it as information is revealed.

The underlying math (Bayesian filter over enumerated sets, ML blend,
niche-mechanic constraints) lives in the modules this class composes.
This file is purely the integration layer.
"""

from typing import Dict, List, Optional

from src.hybrid_predictor import HybridSetPredictor
from src.niche_mechanics import MechanicConstraint, NicheMechanicsDetector
from src.set_predictor import SetPrediction


class BeliefState:
    def __init__(
        self,
        data_manager,
        battle_id: str,
        tier: str = "gen9randombattle",
        player_rating: Optional[int] = None,
        opponent_username: Optional[str] = None,
    ):
        self.predictor = HybridSetPredictor(data_manager)
        self.mechanics = NicheMechanicsDetector()
        self.predictions: Dict[str, SetPrediction] = {}
        self.contexts: Dict[str, dict] = {}

        self.predictor.set_battle_context(
            battle_id=battle_id,
            tier=tier,
            player_rating=player_rating,
            opponent_username=opponent_username,
        )

    def observe_pokemon(self, pokemon_name: str) -> SetPrediction:
        if pokemon_name not in self.predictions:
            prediction = self.predictor.create_initial_prediction(pokemon_name)
            self.predictions[pokemon_name] = prediction
            self.contexts[pokemon_name] = {}
            self._apply_mechanics(pokemon_name)
        return self.predictions[pokemon_name]

    def observe_move(self, pokemon_name: str, move_name: str) -> SetPrediction:
        prediction = self._ensure(pokemon_name)
        self.predictions[pokemon_name] = self.predictor.update_with_move(
            prediction, move_name
        )
        self._apply_mechanics(pokemon_name)
        return self.predictions[pokemon_name]

    def observe_ability(self, pokemon_name: str, ability_name: str) -> SetPrediction:
        prediction = self._ensure(pokemon_name)
        self.predictions[pokemon_name] = self.predictor.update_with_ability(
            prediction, ability_name
        )
        self.contexts[pokemon_name]["ability_activated"] = True
        self._apply_mechanics(pokemon_name)
        return self.predictions[pokemon_name]

    def observe_item(self, pokemon_name: str, item_name: str) -> SetPrediction:
        prediction = self._ensure(pokemon_name)
        self.predictions[pokemon_name] = self.predictor.update_with_item(
            prediction, item_name
        )
        self._apply_mechanics(pokemon_name)
        return self.predictions[pokemon_name]

    def update_context(self, pokemon_name: str, **updates) -> None:
        self._ensure(pokemon_name)
        self.contexts[pokemon_name].update(updates)
        self._apply_mechanics(pokemon_name)

    def get_prediction(self, pokemon_name: str) -> Optional[SetPrediction]:
        return self.predictions.get(pokemon_name)

    def all_predictions(self) -> Dict[str, SetPrediction]:
        return dict(self.predictions)

    def finalize_pokemon(
        self,
        pokemon_name: str,
        ability: str,
        item: str,
        moves: List[str],
        tera: Optional[str] = None,
        spread: Optional[str] = None,
    ) -> None:
        self.predictor.finalize_pokemon(
            pokemon_name, ability, item, moves, tera, spread
        )

    def end_battle(self, winner: Optional[str] = None) -> None:
        self.predictor.end_battle(winner=winner)

    def _ensure(self, pokemon_name: str) -> SetPrediction:
        if pokemon_name not in self.predictions:
            return self.observe_pokemon(pokemon_name)
        return self.predictions[pokemon_name]

    def _apply_mechanics(self, pokemon_name: str) -> None:
        prediction = self.predictions[pokemon_name]
        context = self.contexts[pokemon_name]
        for constraint in self.mechanics.apply_all_constraints(pokemon_name, context):
            self._apply_constraint(prediction, constraint)

    def _apply_constraint(
        self, prediction: SetPrediction, constraint: MechanicConstraint
    ) -> None:
        for item in constraint.ruled_out_items:
            prediction.item_probs.pop(item, None)
            prediction.impossible_items.add(item)
        for ability in constraint.ruled_out_abilities:
            prediction.ability_probs.pop(ability, None)

        if constraint.confirmed_items:
            item = next(iter(constraint.confirmed_items))
            prediction.revealed_item = item
            prediction.item_probs = {item: 1.0}
        if constraint.confirmed_abilities:
            ability = next(iter(constraint.confirmed_abilities))
            prediction.revealed_ability = ability
            prediction.ability_probs = {ability: 1.0}

        for target, multiplier in constraint.probability_boosts.items():
            if target in prediction.item_probs:
                prediction.item_probs[target] *= multiplier
            if target in prediction.ability_probs:
                prediction.ability_probs[target] *= multiplier

        _renormalize(prediction.item_probs)
        _renormalize(prediction.ability_probs)


def _renormalize(probs: Dict[str, float]) -> None:
    total = sum(probs.values())
    if total > 0:
        for key in list(probs):
            probs[key] /= total
