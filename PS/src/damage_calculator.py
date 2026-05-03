"""
Pokemon Damage Calculator
Calculates damage ranges for moves and helps predict sets based on damage observations
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import math


@dataclass
class DamageResult:
    """Result of a damage calculation"""
    min_damage: int
    max_damage: int
    min_percent: float
    max_percent: float
    guaranteed_ko: bool
    possible_ko: bool
    roll_to_ko: Optional[str]  # e.g., "87.5% chance to KO"


class TypeChart:
    """Type effectiveness chart"""

    # Type effectiveness multipliers
    IMMUNE = 0.0
    NOT_VERY_EFFECTIVE = 0.5
    NEUTRAL = 1.0
    SUPER_EFFECTIVE = 2.0

    # Complete type chart (Gen 9)
    EFFECTIVENESS = {
        'Normal': {'Rock': 0.5, 'Ghost': 0, 'Steel': 0.5},
        'Fire': {'Fire': 0.5, 'Water': 0.5, 'Grass': 2, 'Ice': 2, 'Bug': 2, 'Rock': 0.5, 'Dragon': 0.5, 'Steel': 2},
        'Water': {'Fire': 2, 'Water': 0.5, 'Grass': 0.5, 'Ground': 2, 'Rock': 2, 'Dragon': 0.5},
        'Electric': {'Water': 2, 'Electric': 0.5, 'Grass': 0.5, 'Ground': 0, 'Flying': 2, 'Dragon': 0.5},
        'Grass': {'Fire': 0.5, 'Water': 2, 'Grass': 0.5, 'Poison': 0.5, 'Ground': 2, 'Flying': 0.5, 'Bug': 0.5, 'Rock': 2, 'Dragon': 0.5, 'Steel': 0.5},
        'Ice': {'Fire': 0.5, 'Water': 0.5, 'Grass': 2, 'Ice': 0.5, 'Ground': 2, 'Flying': 2, 'Dragon': 2, 'Steel': 0.5},
        'Fighting': {'Normal': 2, 'Ice': 2, 'Poison': 0.5, 'Flying': 0.5, 'Psychic': 0.5, 'Bug': 0.5, 'Rock': 2, 'Ghost': 0, 'Dark': 2, 'Steel': 2, 'Fairy': 0.5},
        'Poison': {'Grass': 2, 'Poison': 0.5, 'Ground': 0.5, 'Rock': 0.5, 'Ghost': 0.5, 'Steel': 0, 'Fairy': 2},
        'Ground': {'Fire': 2, 'Electric': 2, 'Grass': 0.5, 'Poison': 2, 'Flying': 0, 'Bug': 0.5, 'Rock': 2, 'Steel': 2},
        'Flying': {'Electric': 0.5, 'Grass': 2, 'Fighting': 2, 'Bug': 2, 'Rock': 0.5, 'Steel': 0.5},
        'Psychic': {'Fighting': 2, 'Poison': 2, 'Psychic': 0.5, 'Dark': 0, 'Steel': 0.5},
        'Bug': {'Fire': 0.5, 'Grass': 2, 'Fighting': 0.5, 'Poison': 0.5, 'Flying': 0.5, 'Psychic': 2, 'Ghost': 0.5, 'Dark': 2, 'Steel': 0.5, 'Fairy': 0.5},
        'Rock': {'Fire': 2, 'Ice': 2, 'Fighting': 0.5, 'Ground': 0.5, 'Flying': 2, 'Bug': 2, 'Steel': 0.5},
        'Ghost': {'Normal': 0, 'Psychic': 2, 'Ghost': 2, 'Dark': 0.5},
        'Dragon': {'Dragon': 2, 'Steel': 0.5, 'Fairy': 0},
        'Dark': {'Fighting': 0.5, 'Psychic': 2, 'Ghost': 2, 'Dark': 0.5, 'Fairy': 0.5},
        'Steel': {'Fire': 0.5, 'Water': 0.5, 'Electric': 0.5, 'Ice': 2, 'Rock': 2, 'Steel': 0.5, 'Fairy': 2},
        'Fairy': {'Fire': 0.5, 'Fighting': 2, 'Poison': 0.5, 'Dragon': 2, 'Dark': 2, 'Steel': 0.5},
    }

    @classmethod
    def get_effectiveness(cls, attack_type: str, defending_types: List[str]) -> float:
        """
        Get type effectiveness multiplier

        Args:
            attack_type: Type of the attacking move
            defending_types: List of defending Pokemon's types

        Returns:
            Effectiveness multiplier (0, 0.25, 0.5, 1, 2, 4)
        """
        multiplier = 1.0

        for def_type in defending_types:
            if attack_type in cls.EFFECTIVENESS:
                multiplier *= cls.EFFECTIVENESS[attack_type].get(def_type, 1.0)

        return multiplier


class DamageCalculator:
    """
    Pokemon damage calculator based on Gen 9 damage formula

    Damage = ((2 * Level / 5 + 2) * Power * A / D / 50 + 2) * Modifiers

    Where modifiers include:
    - STAB (1.5x if move type matches Pokemon type)
    - Type effectiveness
    - Random factor (0.85 - 1.0)
    - Critical hit (1.5x)
    - Items (Life Orb, Choice Band, etc.)
    - Abilities
    - Weather
    - Screens
    - And many more...
    """

    def __init__(self, data_manager):
        """
        Initialize damage calculator

        Args:
            data_manager: DataManager with Pokemon data
        """
        self.data_manager = data_manager
        self.type_chart = TypeChart()

    def calculate_damage(
        self,
        attacker_name: str,
        defender_name: str,
        move_name: str,
        attacker_stats: Optional[Dict[str, int]] = None,
        defender_stats: Optional[Dict[str, int]] = None,
        attacker_item: Optional[str] = None,
        defender_item: Optional[str] = None,
        attacker_ability: Optional[str] = None,
        defender_ability: Optional[str] = None,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        is_crit: bool = False,
        screen_active: Optional[str] = None,
    ) -> DamageResult:
        """
        Calculate damage range for a move

        Args:
            attacker_name: Attacking Pokemon
            defender_name: Defending Pokemon
            move_name: Move being used
            attacker_stats: Attacker's stats (if known)
            defender_stats: Defender's stats (if known)
            attacker_item: Attacker's item
            defender_item: Defender's item
            attacker_ability: Attacker's ability
            defender_ability: Defender's ability
            weather: Active weather
            terrain: Active terrain
            is_crit: Whether it's a critical hit
            screen_active: Light Screen or Reflect

        Returns:
            DamageResult with damage range
        """
        # Get Pokemon data
        attacker_data = self.data_manager.get_pokemon_info(attacker_name)
        defender_data = self.data_manager.get_pokemon_info(defender_name)
        move_data = self.data_manager.get_move_info(move_name)

        if not move_data or not attacker_data or not defender_data:
            return DamageResult(0, 0, 0.0, 0.0, False, False, None)

        # Get move power
        power = move_data.get('basePower', 0)
        if power == 0:
            return DamageResult(0, 0, 0.0, 0.0, False, False, None)

        # Determine if physical or special
        move_category = move_data.get('category', 'Physical')
        is_physical = move_category == 'Physical'

        # Get stats (use base stats if not provided)
        if attacker_stats is None:
            attack_stat = self._estimate_stat(
                attacker_data['baseStats']['atk' if is_physical else 'spa'],
                level=50,
                nature_boost=True
            )
        else:
            attack_stat = attacker_stats['atk' if is_physical else 'spa']

        if defender_stats is None:
            defense_stat = self._estimate_stat(
                defender_data['baseStats']['def' if is_physical else 'spd'],
                level=50,
                nature_boost=False
            )
        else:
            defense_stat = defender_stats['def' if is_physical else 'spd']

        # Calculate base damage
        level = 50
        base_damage = ((2 * level / 5 + 2) * power * attack_stat / defense_stat / 50 + 2)

        # Apply modifiers
        modifier = 1.0

        # STAB
        move_type = move_data.get('type', 'Normal')
        attacker_types = attacker_data.get('types', [])
        if move_type in attacker_types:
            # Check for Adaptability
            if attacker_ability == 'Adaptability':
                modifier *= 2.0
            else:
                modifier *= 1.5

        # Type effectiveness
        defender_types = defender_data.get('types', [])
        effectiveness = self.type_chart.get_effectiveness(move_type, defender_types)
        modifier *= effectiveness

        # Critical hit
        if is_crit:
            modifier *= 1.5

        # Weather modifiers
        if weather:
            modifier *= self._get_weather_modifier(move_type, weather)

        # Terrain modifiers
        if terrain:
            modifier *= self._get_terrain_modifier(move_type, terrain, defender_data)

        # Item modifiers
        if attacker_item:
            modifier *= self._get_item_modifier(attacker_item, move_type, is_physical)

        # Ability modifiers
        if attacker_ability:
            modifier *= self._get_ability_modifier(attacker_ability, move_data, attacker_data)

        # Defensive item/ability modifiers
        if defender_item:
            modifier *= self._get_defensive_item_modifier(defender_item, move_type, is_physical)

        if defender_ability:
            modifier *= self._get_defensive_ability_modifier(
                defender_ability, move_type, move_data, attacker_ability
            )

        # Screen modifiers
        if screen_active:
            if (screen_active == 'Reflect' and is_physical) or \
               (screen_active == 'Light Screen' and not is_physical):
                modifier *= 0.5

        # Calculate damage range (random factor 0.85 - 1.0)
        min_damage = math.floor(base_damage * modifier * 0.85)
        max_damage = math.floor(base_damage * modifier * 1.0)

        # Get defender HP
        defender_hp = self._estimate_hp(defender_data['baseStats']['hp'], level=50)

        # Calculate percentages
        min_percent = (min_damage / defender_hp) * 100
        max_percent = (max_damage / defender_hp) * 100

        # Check KO potential
        guaranteed_ko = min_damage >= defender_hp
        possible_ko = max_damage >= defender_hp

        # Calculate KO probability
        roll_to_ko = None
        if possible_ko and not guaranteed_ko:
            # Number of rolls that KO / total rolls (16 possible rolls)
            ko_rolls = sum(1 for i in range(16) if math.floor(base_damage * modifier * (0.85 + i * 0.01)) >= defender_hp)
            roll_to_ko = f"{(ko_rolls / 16) * 100:.1f}% chance to KO"

        return DamageResult(
            min_damage=min_damage,
            max_damage=max_damage,
            min_percent=min_percent,
            max_percent=max_percent,
            guaranteed_ko=guaranteed_ko,
            possible_ko=possible_ko,
            roll_to_ko=roll_to_ko
        )

    def _estimate_stat(self, base_stat: int, level: int = 50, nature_boost: bool = False) -> int:
        """Estimate stat with max EVs and beneficial nature"""
        ev = 252
        iv = 31
        stat = math.floor(((2 * base_stat + iv + math.floor(ev / 4)) * level / 100) + 5)
        if nature_boost:
            stat = math.floor(stat * 1.1)
        return stat

    def _estimate_hp(self, base_hp: int, level: int = 50) -> int:
        """Estimate HP with max EVs"""
        ev = 252
        iv = 31
        return math.floor(((2 * base_hp + iv + math.floor(ev / 4)) * level / 100) + level + 10)

    def _get_weather_modifier(self, move_type: str, weather: str) -> float:
        """Get weather damage modifier"""
        if weather == 'Sun':
            if move_type == 'Fire':
                return 1.5
            elif move_type == 'Water':
                return 0.5
        elif weather == 'Rain':
            if move_type == 'Water':
                return 1.5
            elif move_type == 'Fire':
                return 0.5

        return 1.0

    def _get_terrain_modifier(self, move_type: str, terrain: str, defender_data: dict) -> float:
        """Get terrain damage modifier"""
        # Terrains boost moves of matching type by 1.3x if grounded
        terrain_boosts = {
            'Electric Terrain': 'Electric',
            'Grassy Terrain': 'Grass',
            'Psychic Terrain': 'Psychic',
            'Misty Terrain': 'Fairy'
        }

        # TODO: Check if Pokemon is grounded (not Flying type, no Levitate)
        if terrain in terrain_boosts and move_type == terrain_boosts[terrain]:
            return 1.3

        return 1.0

    def _get_item_modifier(self, item: str, move_type: str, is_physical: bool) -> float:
        """Get offensive item modifier"""
        # Life Orb
        if item == 'Life Orb':
            return 1.3

        # Choice items
        if item == 'Choice Band' and is_physical:
            return 1.5
        if item == 'Choice Specs' and not is_physical:
            return 1.5

        # Type-boosting items
        type_items = {
            'Charcoal': 'Fire', 'Mystic Water': 'Water', 'Miracle Seed': 'Grass',
            'Magnet': 'Electric', 'Never-Melt Ice': 'Ice', 'Black Belt': 'Fighting',
            'Poison Barb': 'Poison', 'Soft Sand': 'Ground', 'Sharp Beak': 'Flying',
            'Twisted Spoon': 'Psychic', 'Silver Powder': 'Bug', 'Hard Stone': 'Rock',
            'Spell Tag': 'Ghost', 'Dragon Fang': 'Dragon', 'Black Glasses': 'Dark',
            'Metal Coat': 'Steel', 'Pixie Plate': 'Fairy'
        }

        if item in type_items and type_items[item] == move_type:
            return 1.2

        return 1.0

    def _get_ability_modifier(self, ability: str, move_data: dict, attacker_data: dict) -> float:
        """Get offensive ability modifier"""
        # Sheer Force
        if ability == 'Sheer Force' and move_data.get('secondary'):
            return 1.3

        # Technician (moves 60 power or less)
        if ability == 'Technician' and move_data.get('basePower', 0) <= 60:
            return 1.5

        # Tough Claws (contact moves)
        if ability == 'Tough Claws' and move_data.get('flags', {}).get('contact'):
            return 1.3

        # More abilities...
        return 1.0

    def _get_defensive_item_modifier(self, item: str, move_type: str, is_physical: bool) -> float:
        """Get defensive item modifier"""
        # Assault Vest
        if item == 'Assault Vest' and not is_physical:
            return 0.67

        # Eviolite (would need to check if Pokemon evolves)
        # This is complex, skip for now

        return 1.0

    def _get_defensive_ability_modifier(self, ability: str, move_type: str,
                                       move_data: dict, attacker_ability: Optional[str]) -> float:
        """Get defensive ability modifier"""
        # Multiscale/Shadow Shield (at full HP)
        if ability in ['Multiscale', 'Shadow Shield']:
            return 0.5

        # Filter/Solid Rock/Prism Armor (super effective)
        if ability in ['Filter', 'Solid Rock', 'Prism Armor']:
            # Would need to check effectiveness
            pass

        # Thick Fat
        if ability == 'Thick Fat' and move_type in ['Fire', 'Ice']:
            return 0.5

        return 1.0

    def calculate_reverse_stats(self, attacker_name: str, defender_name: str,
                               move_name: str, actual_damage: int,
                               defender_hp: int) -> Dict[str, int]:
        """
        Reverse-engineer stats from observed damage

        Args:
            attacker_name: Attacking Pokemon
            defender_name: Defending Pokemon
            move_name: Move used
            actual_damage: Actual damage dealt
            defender_hp: Defender's current/max HP

        Returns:
            Estimated stat ranges
        """
        # This is complex and requires iterating through possible stat combinations
        # For now, return empty dict
        # TODO: Implement reverse damage calculation
        return {}


def main():
    """Test damage calculator"""
    from src.data_manager import DataManager

    dm = DataManager()

    if not dm.is_data_available():
        print("Error: Data not available. Run update_data.py first.")
        return

    calc = DamageCalculator(dm)

    print("=" * 70)
    print("Damage Calculator Test")
    print("=" * 70)

    # Test 1: Kingambit Sucker Punch vs Great Tusk
    print("\n[Test 1] Kingambit Sucker Punch vs Great Tusk")
    print("-" * 70)
    result = calc.calculate_damage(
        attacker_name="Kingambit",
        defender_name="Great Tusk",
        move_name="Sucker Punch",
        attacker_item="Black Glasses",
        attacker_ability="Supreme Overlord"
    )
    print(f"Damage: {result.min_damage}-{result.max_damage} ({result.min_percent:.1f}%-{result.max_percent:.1f}%)")
    print(f"Guaranteed KO: {result.guaranteed_ko}")
    print(f"Possible KO: {result.possible_ko}")
    if result.roll_to_ko:
        print(f"KO Chance: {result.roll_to_ko}")

    # Test 2: Great Tusk Close Combat vs Kingambit
    print("\n[Test 2] Great Tusk Close Combat vs Kingambit")
    print("-" * 70)
    result = calc.calculate_damage(
        attacker_name="Great Tusk",
        defender_name="Kingambit",
        move_name="Close Combat",
        attacker_ability="Protosynthesis",
        defender_item="Leftovers"
    )
    print(f"Damage: {result.min_damage}-{result.max_damage} ({result.min_percent:.1f}%-{result.max_percent:.1f}%)")
    print(f"Guaranteed KO: {result.guaranteed_ko}")
    print(f"Possible KO: {result.possible_ko}")

    # Test 3: Raging Bolt Thunderbolt vs Corviknight
    print("\n[Test 3] Raging Bolt Thunderbolt vs Corviknight")
    print("-" * 70)
    result = calc.calculate_damage(
        attacker_name="Raging Bolt",
        defender_name="Corviknight",
        move_name="Thunderbolt",
        attacker_item="Life Orb",
        defender_item="Rocky Helmet"
    )
    print(f"Damage: {result.min_damage}-{result.max_damage} ({result.min_percent:.1f}%-{result.max_percent:.1f}%)")
    print(f"Type effectiveness: Super Effective!")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
