"""
Set Predictor Module
Predicts opponent Pokemon sets using Bayesian inference and Smogon usage data
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import json
from pathlib import Path
from collections import defaultdict


@dataclass
class SetPrediction:
    """Represents predictions for a Pokemon's set"""
    pokemon: str

    # Known information (revealed during battle)
    revealed_moves: Set[str] = field(default_factory=set)
    revealed_ability: Optional[str] = None
    revealed_item: Optional[str] = None
    revealed_tera: Optional[str] = None

    # Predictions (probability distributions)
    ability_probs: Dict[str, float] = field(default_factory=dict)
    item_probs: Dict[str, float] = field(default_factory=dict)
    move_probs: Dict[str, float] = field(default_factory=dict)
    spread_probs: Dict[str, float] = field(default_factory=dict)
    tera_probs: Dict[str, float] = field(default_factory=dict)

    # Metadata
    confidence: float = 0.0
    turns_seen: int = 0

    # Game mechanic constraints (items ruled out by observations)
    impossible_items: Set[str] = field(default_factory=set)


class SetPredictor:
    """Predicts Pokemon sets based on Smogon usage data and revealed information"""

    def __init__(self, data_manager):
        """
        Initialize the set predictor

        Args:
            data_manager: DataManager instance with loaded Smogon data
        """
        self.data_manager = data_manager
        self.tier = "gen9ou"

        # Cache for correlations
        self._move_correlations = {}
        self._set_archetypes = {}

        # Define non-attacking moves (blocked by Assault Vest)
        # Pivot moves like U-turn, Volt Switch deal damage so they're NOT in this list
        self.non_attacking_moves = {
            'Swords Dance', 'Nasty Plot', 'Dragon Dance', 'Calm Mind', 'Bulk Up', 'Quiver Dance',
            'Stealth Rock', 'Spikes', 'Toxic Spikes', 'Sticky Web',
            'Thunder Wave', 'Will-O-Wisp', 'Toxic', 'Spore', 'Sleep Powder', 'Hypnosis',
            'Recover', 'Roost', 'Soft-Boiled', 'Wish', 'Synthesis', 'Morning Sun', 'Moonlight',
            'Protect', 'Detect', 'Substitute', 'Taunt', 'Encore', 'Trick', 'Switcheroo',
            'Defog', 'Haze', 'Whirlwind', 'Roar',
            'Light Screen', 'Reflect', 'Tailwind', 'Trick Room', 'Magic Room', 'Wonder Room',
            'Leech Seed', 'Rest', 'Sleep Talk', 'Baton Pass',
            'Teleport', 'Parting Shot'  # Parting Shot lowers stats but deals no damage
        }

    def create_initial_prediction(self, pokemon_name: str) -> SetPrediction:
        """
        Create initial prediction when Pokemon is first seen

        Args:
            pokemon_name: Name of the Pokemon

        Returns:
            SetPrediction with initial probabilities from Smogon data
        """
        prediction = SetPrediction(pokemon=pokemon_name)

        # Get Smogon moveset data
        moveset_data = self.data_manager.get_pokemon_moveset(pokemon_name, self.tier)

        if not moveset_data:
            print(f"Warning: No moveset data found for {pokemon_name}")
            return prediction

        # Initialize probabilities from Smogon usage percentages
        prediction.ability_probs = self._normalize_probs(moveset_data.get('abilities', {}))
        prediction.item_probs = self._normalize_probs(moveset_data.get('items', {}))
        prediction.move_probs = self._normalize_probs(moveset_data.get('moves', {}))
        prediction.spread_probs = self._normalize_probs(moveset_data.get('spreads', {}))
        prediction.tera_probs = self._normalize_probs(moveset_data.get('tera_types', {}))

        # AUTO-CONFIRM single-ability Pokemon
        if len(prediction.ability_probs) == 1:
            ability_name = list(prediction.ability_probs.keys())[0]
            prediction.revealed_ability = ability_name
            prediction.ability_probs = {ability_name: 1.0}
            print(f"  ✓ Single ability: {ability_name} (auto-confirmed)")

        # AUTO-CONFIRM required items (forme changes)
        # Check if this Pokemon requires a specific item (e.g., Ogerpon masks)
        required_item = self._get_required_item(pokemon_name)
        if required_item:
            prediction.revealed_item = required_item
            prediction.item_probs = {required_item: 1.0}
            print(f"  ✓ Required item: {required_item} (forme-specific)")

        # Calculate initial confidence (how concentrated is the distribution)
        prediction.confidence = self._calculate_confidence(prediction)

        return prediction

    def update_with_move(self, prediction: SetPrediction, move_name: str) -> SetPrediction:
        """
        Update prediction when a move is revealed

        Args:
            prediction: Current prediction
            move_name: Name of the revealed move

        Returns:
            Updated SetPrediction
        """
        # Add to revealed moves
        prediction.revealed_moves.add(move_name)
        prediction.turns_seen += 1

        # Set this move to 100% probability
        if move_name in prediction.move_probs:
            prediction.move_probs[move_name] = 1.0
        else:
            # Move wasn't in common sets, but now we know it exists
            prediction.move_probs[move_name] = 1.0

        # Apply game mechanic constraints
        prediction = self._apply_move_constraints(prediction, move_name)

        # Update other move probabilities based on correlations
        prediction = self._update_correlated_moves(prediction, move_name)

        # Update item/ability probabilities (some moves correlate with items/abilities)
        prediction = self._update_correlated_items(prediction, move_name)

        # Recalculate confidence
        prediction.confidence = self._calculate_confidence(prediction)

        return prediction

    def update_with_ability(self, prediction: SetPrediction, ability_name: str) -> SetPrediction:
        """
        Update prediction when ability is revealed

        Args:
            prediction: Current prediction
            ability_name: Name of the revealed ability

        Returns:
            Updated SetPrediction
        """
        prediction.revealed_ability = ability_name
        prediction.turns_seen += 1

        # Set this ability to 100%
        prediction.ability_probs = {ability_name: 1.0}

        # Some Pokemon have different moveset preferences based on ability
        # Example: Protean vs Torrent on Greninja
        prediction = self._update_for_ability(prediction, ability_name)

        prediction.confidence = self._calculate_confidence(prediction)
        return prediction

    def update_with_item(self, prediction: SetPrediction, item_name: str) -> SetPrediction:
        """
        Update prediction when item is revealed

        Args:
            prediction: Current prediction
            item_name: Name of the revealed item

        Returns:
            Updated SetPrediction
        """
        prediction.revealed_item = item_name
        prediction.turns_seen += 1

        # Set this item to 100%
        prediction.item_probs = {item_name: 1.0}

        # Update move correlations based on item
        # Example: Choice Scarf → offensive moves, Leftovers → recovery/defensive
        prediction = self._update_for_item(prediction, item_name)

        prediction.confidence = self._calculate_confidence(prediction)
        return prediction

    def apply_damage_constraints(self, prediction: SetPrediction,
                                 took_hazard_damage: bool = False,
                                 healed_over_time: bool = False,
                                 took_recoil: bool = False) -> SetPrediction:
        """
        Public method to apply damage-based constraints

        Args:
            prediction: Current prediction
            took_hazard_damage: Whether Pokemon took entry hazard damage
            healed_over_time: Whether Pokemon healed passively
            took_recoil: Whether Pokemon took recoil damage

        Returns:
            Updated prediction
        """
        return self._apply_damage_constraints(prediction, took_hazard_damage, healed_over_time, took_recoil)

    def apply_ability_activation_constraint(self, prediction: SetPrediction,
                                           ability_activated_on_switch: bool = False,
                                           sun_active: bool = False,
                                           electric_terrain_active: bool = False) -> SetPrediction:
        """
        Apply Booster Energy detection based on ability activation

        Protosynthesis/Quark Drive can activate two ways:
        1. Naturally (Sun for Protosynthesis, Electric Terrain for Quark Drive)
        2. Via Booster Energy item (when weather/terrain not present)

        Args:
            prediction: Current prediction
            ability_activated_on_switch: Whether Protosynthesis/Quark Drive activated on switch
            sun_active: Whether harsh sunlight is active
            electric_terrain_active: Whether Electric Terrain is active

        Returns:
            Updated prediction
        """
        if prediction.revealed_item:
            return prediction

        # Check if ability is Protosynthesis or Quark Drive
        is_protosynthesis = prediction.revealed_ability == "Protosynthesis"
        is_quark_drive = prediction.revealed_ability == "Quark Drive"

        if not (is_protosynthesis or is_quark_drive):
            return prediction

        if ability_activated_on_switch:
            # Protosynthesis activates in sun naturally
            if is_protosynthesis and sun_active:
                print(f"  ℹ️  Protosynthesis activated naturally (sun present)")
                print(f"     Item is unknown - could be anything")
                return prediction

            # Quark Drive activates in Electric Terrain naturally
            if is_quark_drive and electric_terrain_active:
                print(f"  ℹ️  Quark Drive activated naturally (Electric Terrain present)")
                print(f"     Item is unknown - could be anything")
                return prediction

            # If ability activated but NO weather/terrain, must be Booster Energy!
            if is_protosynthesis and not sun_active:
                print(f"  ⚡ Protosynthesis activated without sun!")
                print(f"  ✓ Item CONFIRMED: Booster Energy")
                prediction.revealed_item = "Booster Energy"
                prediction.item_probs = {"Booster Energy": 1.0}

            elif is_quark_drive and not electric_terrain_active:
                print(f"  ⚡ Quark Drive activated without Electric Terrain!")
                print(f"  ✓ Item CONFIRMED: Booster Energy")
                prediction.revealed_item = "Booster Energy"
                prediction.item_probs = {"Booster Energy": 1.0}

        return prediction

    def get_top_predictions(self, prediction: SetPrediction, n: int = 5) -> Dict[str, List[Tuple[str, float]]]:
        """
        Get top N predictions for each category

        Args:
            prediction: Current prediction
            n: Number of top predictions to return

        Returns:
            Dictionary with top predictions for abilities, items, moves
        """
        result = {}

        # Top abilities
        if not prediction.revealed_ability:
            result['abilities'] = sorted(
                prediction.ability_probs.items(),
                key=lambda x: x[1],
                reverse=True
            )[:n]
        else:
            result['abilities'] = [(prediction.revealed_ability, 1.0)]

        # Top items
        if not prediction.revealed_item:
            result['items'] = sorted(
                prediction.item_probs.items(),
                key=lambda x: x[1],
                reverse=True
            )[:n]
        else:
            result['items'] = [(prediction.revealed_item, 1.0)]

        # Top unrevealed moves
        unrevealed_moves = {
            move: prob
            for move, prob in prediction.move_probs.items()
            if move not in prediction.revealed_moves
        }
        result['moves'] = sorted(
            unrevealed_moves.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]

        # Revealed moves
        result['revealed_moves'] = list(prediction.revealed_moves)

        return result

    def _normalize_probs(self, data: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize percentages to probabilities (0-1 range)

        Args:
            data: Dictionary with percentage values

        Returns:
            Dictionary with normalized probabilities
        """
        if not data:
            return {}

        # Convert percentages to decimals
        probs = {key: value / 100.0 for key, value in data.items()}

        # Normalize to sum to 1.0 (in case percentages don't sum to 100)
        total = sum(probs.values())
        if total > 0:
            probs = {key: value / total for key, value in probs.items()}

        return probs

    def _apply_move_constraints(self, prediction: SetPrediction, move_name: str) -> SetPrediction:
        """
        Apply hard constraints based on game mechanics

        Args:
            prediction: Current prediction
            move_name: Move that was just used

        Returns:
            Updated prediction with constraints applied
        """
        if prediction.revealed_item:
            # Item already known, no constraints to apply
            return prediction

        # CONSTRAINT 1: Using 2+ different moves → NOT a Choice item
        if len(prediction.revealed_moves) >= 2:
            choice_items = {'Choice Band', 'Choice Scarf', 'Choice Specs'}
            for item in choice_items:
                if item not in prediction.impossible_items:
                    prediction.impossible_items.add(item)
                    print(f"  ⚠️  Ruled out {item} (used {len(prediction.revealed_moves)} different moves)")

        # CONSTRAINT 2: Using a non-attacking move → NOT Assault Vest
        if move_name in self.non_attacking_moves:
            if 'Assault Vest' not in prediction.impossible_items:
                prediction.impossible_items.add('Assault Vest')
                print(f"  ⚠️  Ruled out Assault Vest (used status move: {move_name})")

        # Remove impossible items from probability distribution
        for item in prediction.impossible_items:
            if item in prediction.item_probs:
                del prediction.item_probs[item]

        # Renormalize item probabilities
        total = sum(prediction.item_probs.values())
        if total > 0:
            prediction.item_probs = {
                item: prob / total
                for item, prob in prediction.item_probs.items()
            }

        return prediction

    def _apply_damage_constraints(self, prediction: SetPrediction,
                                   took_hazard_damage: bool = False,
                                   healed_over_time: bool = False,
                                   took_recoil: bool = False) -> SetPrediction:
        """
        Apply constraints based on damage observations

        Args:
            prediction: Current prediction
            took_hazard_damage: Whether Pokemon took Stealth Rock/Spikes damage on switch-in
            healed_over_time: Whether Pokemon healed at end of turn
            took_recoil: Whether Pokemon took recoil damage from move

        Returns:
            Updated prediction
        """
        if prediction.revealed_item:
            return prediction

        # Took hazard damage → NOT Heavy-Duty Boots
        if took_hazard_damage:
            if 'Heavy-Duty Boots' not in prediction.impossible_items:
                prediction.impossible_items.add('Heavy-Duty Boots')
                print(f"  ⚠️  Ruled out Heavy-Duty Boots (took entry hazard damage)")
                if 'Heavy-Duty Boots' in prediction.item_probs:
                    del prediction.item_probs['Heavy-Duty Boots']

        # Healed over time → likely Leftovers/Black Sludge
        if healed_over_time:
            healing_items = ['Leftovers', 'Black Sludge', 'Shell Bell']
            for item in healing_items:
                if item in prediction.item_probs:
                    prediction.item_probs[item] *= 3.0  # Strong boost

        # Took recoil → likely Life Orb (or recoil move like Brave Bird)
        if took_recoil:
            if 'Life Orb' in prediction.item_probs:
                prediction.item_probs['Life Orb'] *= 2.0

        # Renormalize
        total = sum(prediction.item_probs.values())
        if total > 0:
            prediction.item_probs = {
                item: prob / total
                for item, prob in prediction.item_probs.items()
            }

        return prediction

    def _calculate_confidence(self, prediction: SetPrediction) -> float:
        """
        Calculate overall confidence in prediction

        Higher confidence = more concentrated probability distribution

        Args:
            prediction: Current prediction

        Returns:
            Confidence score (0-1)
        """
        # Factors that increase confidence:
        # 1. How many things have been revealed
        # 2. How concentrated the remaining probabilities are

        revealed_count = len(prediction.revealed_moves)
        if prediction.revealed_ability:
            revealed_count += 1
        if prediction.revealed_item:
            revealed_count += 1

        # Base confidence from revealed information (0-6 things can be revealed)
        base_confidence = revealed_count / 6.0

        # Entropy of probability distributions (lower entropy = higher confidence)
        # For simplicity, use max probability as a proxy
        max_move_prob = max(prediction.move_probs.values()) if prediction.move_probs else 0
        max_item_prob = max(prediction.item_probs.values()) if prediction.item_probs else 0
        max_ability_prob = max(prediction.ability_probs.values()) if prediction.ability_probs else 0

        distribution_confidence = (max_move_prob + max_item_prob + max_ability_prob) / 3.0

        # Combined confidence (weighted average)
        confidence = 0.6 * base_confidence + 0.4 * distribution_confidence

        return min(1.0, confidence)

    def _update_correlated_moves(self, prediction: SetPrediction, revealed_move: str) -> SetPrediction:
        """
        Update move probabilities based on move correlations

        Some moves are commonly used together (e.g., Swords Dance + setup sweeper moves)

        Args:
            prediction: Current prediction
            revealed_move: Move that was just revealed

        Returns:
            Updated prediction
        """
        # Common move synergies
        move_synergies = {
            # Setup moves increase probability of attacking moves
            'Swords Dance': ['Sucker Punch', 'Close Combat', 'Iron Head', 'Earthquake'],
            'Nasty Plot': ['Dark Pulse', 'Sludge Bomb', 'Flamethrower', 'Focus Blast'],
            'Dragon Dance': ['Outrage', 'Earthquake', 'Extreme Speed', 'Fire Punch'],

            # Choice items (if move used early, likely has more coverage)
            'U-turn': ['Earthquake', 'Close Combat', 'Stone Edge'],
            'Volt Switch': ['Thunderbolt', 'Hidden Power', 'Focus Blast'],

            # Defensive moves
            'Stealth Rock': ['Rapid Spin', 'Earthquake', 'Close Combat'],
            'Spikes': ['Rapid Spin', 'Toxic', 'Protect'],
        }

        if revealed_move in move_synergies:
            synergy_moves = move_synergies[revealed_move]
            boost_factor = 1.5  # Increase probability by 50%

            for move in synergy_moves:
                if move in prediction.move_probs and move not in prediction.revealed_moves:
                    prediction.move_probs[move] *= boost_factor

            # Renormalize
            total = sum(prediction.move_probs.values())
            if total > 0:
                prediction.move_probs = {
                    move: prob / total
                    for move, prob in prediction.move_probs.items()
                }

        return prediction

    def _update_correlated_items(self, prediction: SetPrediction, revealed_move: str) -> SetPrediction:
        """
        Update item probabilities based on revealed move

        Args:
            prediction: Current prediction
            revealed_move: Move that was just revealed

        Returns:
            Updated prediction
        """
        # If item already revealed, skip
        if prediction.revealed_item:
            return prediction

        # Move -> Item correlations
        move_item_hints = {
            # Setup moves suggest defensive or speed items
            'Swords Dance': ['Leftovers', 'Life Orb', 'Lum Berry'],
            'Nasty Plot': ['Leftovers', 'Life Orb', 'Focus Sash'],
            'Dragon Dance': ['Leftovers', 'Lum Berry', 'Life Orb'],

            # Pivot moves suggest utility items
            'U-turn': ['Choice Scarf', 'Choice Band', 'Heavy-Duty Boots'],
            'Volt Switch': ['Choice Specs', 'Choice Scarf', 'Heavy-Duty Boots'],

            # Defensive moves suggest bulk items
            'Stealth Rock': ['Leftovers', 'Rocky Helmet', 'Heavy-Duty Boots'],
            'Protect': ['Leftovers', 'Black Sludge', 'Sitrus Berry'],
        }

        if revealed_move in move_item_hints:
            suggested_items = move_item_hints[revealed_move]
            boost_factor = 1.3

            for item in suggested_items:
                if item in prediction.item_probs:
                    prediction.item_probs[item] *= boost_factor

            # Renormalize
            total = sum(prediction.item_probs.values())
            if total > 0:
                prediction.item_probs = {
                    item: prob / total
                    for item, prob in prediction.item_probs.items()
                }

        return prediction

    def _update_for_ability(self, prediction: SetPrediction, ability: str) -> SetPrediction:
        """
        Update predictions based on confirmed ability

        Some abilities have specific moveset preferences

        Args:
            prediction: Current prediction
            ability: Confirmed ability

        Returns:
            Updated prediction
        """
        # Ability-specific moveset adjustments
        ability_preferences = {
            'Protean': ['U-turn', 'Low Kick', 'Ice Beam', 'Gunk Shot'],  # Coverage focused
            'Torrent': ['Hydro Pump', 'Surf', 'Water Spout'],  # Water moves
            'Regenerator': ['U-turn', 'Volt Switch', 'Teleport'],  # Pivot moves
            'Guts': ['Flame Orb', 'Toxic Orb'],  # Status orbs (affects items too)
        }

        # This is a simplified example - in reality, you'd want to reload
        # the moveset data filtered by ability

        return prediction

    def _update_for_item(self, prediction: SetPrediction, item: str) -> SetPrediction:
        """
        Update predictions based on confirmed item

        Args:
            prediction: Current prediction
            item: Confirmed item

        Returns:
            Updated prediction
        """
        # Item-specific moveset adjustments
        item_preferences = {
            'Choice Scarf': ['offensive'],  # Favor coverage moves
            'Choice Band': ['offensive', 'physical'],
            'Choice Specs': ['offensive', 'special'],
            'Leftovers': ['defensive', 'setup'],
            'Life Orb': ['offensive'],
            'Focus Sash': ['setup', 'suicide lead'],
        }

        # This is a simplified example
        return prediction

    def _get_required_item(self, pokemon_name: str) -> Optional[str]:
        """
        Get required item for forme-specific Pokemon

        Args:
            pokemon_name: Pokemon species name

        Returns:
            Required item name, or None if no specific item required
        """
        # Forme-specific required items
        required_items = {
            # Ogerpon formes
            'Ogerpon-Wellspring': 'Wellspring Mask',
            'Ogerpon-Hearthflame': 'Hearthflame Mask',
            'Ogerpon-Cornerstone': 'Cornerstone Mask',

            # Arceus plates (if ever added to OU)
            'Arceus-Fire': 'Flame Plate',
            'Arceus-Water': 'Splash Plate',
            'Arceus-Electric': 'Zap Plate',
            # ... etc

            # Silvally memories (if relevant)
            'Silvally-Fire': 'Fire Memory',
            'Silvally-Water': 'Water Memory',
            # ... etc
        }

        return required_items.get(pokemon_name)


def main():
    """Test the set predictor"""
    from src.data_manager import DataManager

    dm = DataManager()

    if not dm.is_data_available():
        print("Error: Data not available. Run update_data.py first.")
        return

    predictor = SetPredictor(dm)

    # Test with Kingambit
    print("=" * 60)
    print("Set Predictor Test - Kingambit")
    print("=" * 60)

    # Turn 1: Kingambit is sent out
    print("\n[Turn 1] Kingambit sent out")
    print("-" * 60)
    prediction = predictor.create_initial_prediction("Kingambit")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Confidence: {prediction.confidence:.1%}")
    print(f"\nTop Abilities:")
    for ability, prob in top['abilities']:
        print(f"  - {ability}: {prob:.1%}")
    print(f"\nTop Items:")
    for item, prob in top['items']:
        print(f"  - {item}: {prob:.1%}")
    print(f"\nTop Moves:")
    for move, prob in top['moves']:
        print(f"  - {move}: {prob:.1%}")

    # Turn 3: Kingambit uses Sucker Punch
    print("\n\n[Turn 3] Kingambit used Sucker Punch!")
    print("-" * 60)
    prediction = predictor.update_with_move(prediction, "Sucker Punch")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Confidence: {prediction.confidence:.1%}")
    print(f"\nRevealed Moves: {', '.join(top['revealed_moves'])}")
    print(f"\nPredicted Remaining Moves:")
    for move, prob in top['moves']:
        print(f"  - {move}: {prob:.1%}")

    # Turn 5: Kingambit uses Swords Dance
    print("\n\n[Turn 5] Kingambit used Swords Dance!")
    print("-" * 60)
    prediction = predictor.update_with_move(prediction, "Swords Dance")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Confidence: {prediction.confidence:.1%}")
    print(f"\nRevealed Moves: {', '.join(top['revealed_moves'])}")
    print(f"\nPredicted Remaining Moves:")
    for move, prob in top['moves']:
        print(f"  - {move}: {prob:.1%}")
    print(f"\nTop Items (updated):")
    for item, prob in top['items']:
        print(f"  - {item}: {prob:.1%}")

    # Turn 7: Kingambit uses Kowtow Cleave
    print("\n\n[Turn 7] Kingambit used Kowtow Cleave!")
    print("-" * 60)
    prediction = predictor.update_with_move(prediction, "Kowtow Cleave")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Confidence: {prediction.confidence:.1%}")
    print(f"\nRevealed Moves: {', '.join(top['revealed_moves'])}")
    print(f"\nPredicted 4th Move:")
    for move, prob in top['moves']:
        print(f"  - {move}: {prob:.1%}")
    print(f"\nTop Items (Choice items now ruled out):")
    for item, prob in top['items']:
        print(f"  - {item}: {prob:.1%}")

    print("\n" + "=" * 60)

    # Test 2: Assault Vest constraint
    print("\n\n" + "=" * 60)
    print("Constraint Test - Raging Bolt with Assault Vest")
    print("=" * 60)

    print("\n[Turn 1] Raging Bolt sent out")
    print("-" * 60)
    prediction2 = predictor.create_initial_prediction("Raging Bolt")

    top2 = predictor.get_top_predictions(prediction2, n=3)
    print(f"Top Items:")
    for item, prob in top2['items']:
        print(f"  - {item}: {prob:.1%}")

    print("\n[Turn 2] Raging Bolt used Thunderbolt")
    print("-" * 60)
    prediction2 = predictor.update_with_move(prediction2, "Thunderbolt")

    print("\n[Turn 3] Raging Bolt used Calm Mind (status move)")
    print("-" * 60)
    prediction2 = predictor.update_with_move(prediction2, "Calm Mind")

    top2 = predictor.get_top_predictions(prediction2, n=3)
    print(f"\nTop Items (Assault Vest ruled out):")
    for item, prob in top2['items']:
        print(f"  - {item}: {prob:.1%}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
