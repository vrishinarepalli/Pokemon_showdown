"""
Niche Metagame Mechanics Detector
Handles complex game mechanics and edge cases that affect set prediction
"""
from typing import Dict, List, Optional, Set
from dataclasses import dataclass


@dataclass
class MechanicConstraint:
    """Represents a constraint from a game mechanic"""
    ruled_out_items: Set[str]
    ruled_out_abilities: Set[str]
    confirmed_items: Set[str]
    confirmed_abilities: Set[str]
    probability_boosts: Dict[str, float]  # item/ability -> multiplier
    reason: str


class NicheMechanicsDetector:
    """
    Detects niche game mechanics and their implications for set prediction

    Covers:
    - Form changes (Ogerpon, Archaludon, etc.)
    - Weather/terrain interactions
    - Paradox Pokemon mechanics
    - Status-based items (Flame/Toxic Orb)
    - Multi-hit interactions
    - Priority move interactions
    - And many more edge cases
    """

    def __init__(self):
        # Forme-change Pokemon and their required items
        self.form_change_items = {
            'Ogerpon-Wellspring': 'Wellspring Mask',
            'Ogerpon-Hearthflame': 'Hearthflame Mask',
            'Ogerpon-Cornerstone': 'Cornerstone Mask',
            'Archaludon': None,  # No required item, but has forms
            'Genesect': ['Douse Drive', 'Shock Drive', 'Burn Drive', 'Chill Drive'],
            'Silvally': ['Fire Memory', 'Water Memory', 'Grass Memory', 'Electric Memory',
                        'Ice Memory', 'Fighting Memory', 'Poison Memory', 'Ground Memory',
                        'Flying Memory', 'Psychic Memory', 'Bug Memory', 'Rock Memory',
                        'Ghost Memory', 'Dragon Memory', 'Dark Memory', 'Steel Memory',
                        'Fairy Memory']
        }

        # Paradox Pokemon and their abilities
        self.paradox_pokemon = {
            # Future Paradoxes (Quark Drive)
            'Iron Valiant': 'Quark Drive',
            'Iron Treads': 'Quark Drive',
            'Iron Moth': 'Quark Drive',
            'Iron Hands': 'Quark Drive',
            'Iron Jugulis': 'Quark Drive',
            'Iron Thorns': 'Quark Drive',
            'Iron Bundle': 'Quark Drive',
            'Iron Crown': 'Quark Drive',
            'Iron Boulder': 'Quark Drive',
            'Iron Leaves': 'Quark Drive',

            # Past Paradoxes (Protosynthesis)
            'Great Tusk': 'Protosynthesis',
            'Scream Tail': 'Protosynthesis',
            'Brute Bonnet': 'Protosynthesis',
            'Flutter Mane': 'Protosynthesis',
            'Slither Wing': 'Protosynthesis',
            'Sandy Shocks': 'Protosynthesis',
            'Roaring Moon': 'Protosynthesis',
            'Walking Wake': 'Protosynthesis',
            'Gouging Fire': 'Protosynthesis',
            'Raging Bolt': 'Protosynthesis',
        }

        # Abilities that indicate specific items
        self.ability_item_synergies = {
            'Guts': ['Flame Orb', 'Toxic Orb'],
            'Marvel Scale': ['Flame Orb', 'Toxic Orb'],
            'Quick Feet': ['Flame Orb', 'Toxic Orb'],
            'Poison Heal': ['Toxic Orb'],
            'Magic Guard': ['Life Orb', 'Flame Orb'],  # No damage from items
            'Unburden': ['Normal Gem', 'Electric Seed', 'Grassy Seed', 'Misty Seed', 'Psychic Seed'],
            'Weak Armor': ['Rocky Helmet'],  # Synergy
            'Iron Barbs': ['Rocky Helmet'],
            'Rough Skin': ['Rocky Helmet'],
        }

        # Moves that reveal specific interactions
        self.move_item_reveals = {
            # Choice items can't switch moves
            'Trick': ['Choice Scarf', 'Choice Band', 'Choice Specs'],  # Often used to trick Choice items
            'Switcheroo': ['Choice Scarf', 'Choice Band', 'Choice Specs'],

            # Fling reveals item
            'Fling': True,  # Any item (revealed when used)

            # Acrobatics is stronger without item
            'Acrobatics': None,  # Often used with no item or Flying Gem

            # Natural Gift reveals berry
            'Natural Gift': True,  # Reveals berry type
        }

        # Status moves that have specific item interactions
        self.status_move_items = {
            'Rest': ['Chesto Berry', 'Lum Berry'],  # Common with Rest
            'Sleep Talk': ['Chesto Berry'],  # Rest + Sleep Talk combo
            'Facade': ['Flame Orb', 'Toxic Orb'],  # Doubles power with status
            'Psycho Shift': ['Flame Orb', 'Toxic Orb'],  # Transfers status
        }

        # Terrain setters
        self.terrain_setters = {
            'Electric Terrain': ['Electric Seed', 'Terrain Extender'],
            'Grassy Terrain': ['Grassy Seed', 'Terrain Extender'],
            'Psychic Terrain': ['Psychic Seed', 'Terrain Extender'],
            'Misty Terrain': ['Misty Seed', 'Terrain Extender'],
        }

        # Weather setters
        self.weather_setters = {
            'Sandstorm': ['Smooth Rock'],
            'Rain Dance': ['Damp Rock'],
            'Sunny Day': ['Heat Rock'],
            'Snow': ['Icy Rock'],
        }

        # Multi-hit move interactions
        self.multi_hit_moves = {
            'Bullet Seed', 'Rock Blast', 'Icicle Spear', 'Pin Missile',
            'Tail Slap', 'Scale Shot', 'Bone Rush', 'Fury Attack',
            'Population Bomb',  # Gen 9
        }

        # Contact moves (important for Rocky Helmet, etc.)
        self.contact_moves = {
            'Close Combat', 'Knock Off', 'U-turn', 'Extreme Speed',
            'Sucker Punch', 'Aqua Jet', 'Ice Shard', 'Quick Attack',
            'Mach Punch', 'Accelerock', 'Shadow Sneak', 'Fake Out',
        }

    def detect_forme_change(self, pokemon: str, context: dict) -> Optional[MechanicConstraint]:
        """
        Detect if Pokemon has a forme change and required item

        Args:
            pokemon: Pokemon species name
            context: Battle context

        Returns:
            MechanicConstraint if forme requires specific item
        """
        if pokemon in self.form_change_items:
            required = self.form_change_items[pokemon]

            if isinstance(required, str):
                # Single required item
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items={required},
                    confirmed_abilities=set(),
                    probability_boosts={required: 100.0},
                    reason=f"{pokemon} forme requires {required}"
                )
            elif isinstance(required, list):
                # One of multiple items
                boosts = {item: 20.0 for item in required}
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts=boosts,
                    reason=f"{pokemon} may use form-changing item"
                )

        return None

    def detect_paradox_booster_energy(self, pokemon: str, ability_activated: bool,
                                     weather_active: Optional[str] = None,
                                     terrain_active: Optional[str] = None) -> Optional[MechanicConstraint]:
        """
        Detect Booster Energy usage on Paradox Pokemon

        Protosynthesis activates in sun OR with Booster Energy
        Quark Drive activates in Electric Terrain OR with Booster Energy

        Args:
            pokemon: Pokemon species
            ability_activated: Whether Protosynthesis/Quark Drive activated
            weather_active: Current weather
            terrain_active: Current terrain

        Returns:
            MechanicConstraint if Booster Energy is confirmed/ruled out
        """
        if pokemon not in self.paradox_pokemon:
            return None

        ability = self.paradox_pokemon[pokemon]

        if not ability_activated:
            # Ability didn't activate, no conclusions yet
            return None

        # Check if activation was natural
        if ability == 'Protosynthesis' and weather_active == 'Sun':
            # Natural activation, item unknown
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities={ability},
                probability_boosts={},
                reason=f"Protosynthesis activated naturally (sun present)"
            )

        if ability == 'Quark Drive' and terrain_active == 'Electric Terrain':
            # Natural activation, item unknown
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities={ability},
                probability_boosts={},
                reason=f"Quark Drive activated naturally (Electric Terrain present)"
            )

        # Activation without natural condition = Booster Energy!
        if ability == 'Protosynthesis' and weather_active != 'Sun':
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items={'Booster Energy'},
                confirmed_abilities={ability},
                probability_boosts={'Booster Energy': 100.0},
                reason=f"Protosynthesis activated without sun → Booster Energy confirmed"
            )

        if ability == 'Quark Drive' and terrain_active != 'Electric Terrain':
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items={'Booster Energy'},
                confirmed_abilities={ability},
                probability_boosts={'Booster Energy': 100.0},
                reason=f"Quark Drive activated without Electric Terrain → Booster Energy confirmed"
            )

        return None

    def detect_status_orb_activation(self, pokemon: str, status_inflicted: Optional[str],
                                    ability: Optional[str] = None,
                                    took_damage: bool = False) -> Optional[MechanicConstraint]:
        """
        Detect Flame Orb / Toxic Orb activation

        Args:
            pokemon: Pokemon species
            status_inflicted: Status condition (burn/poison)
            ability: Pokemon's ability
            took_damage: Whether Pokemon took damage this turn

        Returns:
            MechanicConstraint if status orb is likely
        """
        # Pokemon got status on their turn (not from opponent)
        if status_inflicted == 'burn' and not took_damage:
            # Likely Flame Orb activation
            constraint = MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={'Flame Orb': 5.0},
                reason="Pokemon burned on own turn → likely Flame Orb"
            )

            # If has Guts/Marvel Scale/Quick Feet, very likely
            if ability in ['Guts', 'Marvel Scale', 'Quick Feet']:
                constraint.probability_boosts['Flame Orb'] = 20.0
                constraint.reason = f"{ability} + self-inflicted burn → very likely Flame Orb"

            return constraint

        if status_inflicted in ['poison', 'badly poisoned'] and not took_damage:
            # Likely Toxic Orb
            constraint = MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={'Toxic Orb': 5.0},
                reason="Pokemon poisoned on own turn → likely Toxic Orb"
            )

            # If has Poison Heal, almost certain
            if ability == 'Poison Heal':
                constraint.probability_boosts['Toxic Orb'] = 30.0
                constraint.reason = "Poison Heal + poison → very likely Toxic Orb"

            return constraint

        return None

    def detect_multi_hit_interaction(self, move_used: str, damage_taken: int,
                                    hits_count: int) -> Optional[MechanicConstraint]:
        """
        Detect Loaded Dice or other multi-hit interactions

        Loaded Dice makes multi-hit moves always hit 4-5 times

        Args:
            move_used: Move that was used
            damage_taken: Total damage
            hits_count: Number of hits

        Returns:
            MechanicConstraint if Loaded Dice is likely
        """
        if move_used in self.multi_hit_moves:
            if hits_count >= 4:
                # Likely Loaded Dice (or just lucky)
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={'Loaded Dice': 3.0},
                    reason=f"{move_used} hit {hits_count} times → possibly Loaded Dice"
                )

        return None

    def detect_speed_changes(self, pokemon: str, speed_changed: bool,
                            move_used: Optional[str] = None) -> Optional[MechanicConstraint]:
        """
        Detect speed-altering items (Choice Scarf, Iron Ball, etc.)

        Args:
            pokemon: Pokemon species
            speed_changed: Whether speed seems different than expected
            move_used: Move that was used

        Returns:
            MechanicConstraint for speed items
        """
        if speed_changed:
            # Could be Choice Scarf, Tailwind, or other factors
            # Can't confirm without damage calc or multiple observations
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={'Choice Scarf': 2.0, 'Iron Ball': 0.1},
                reason="Speed differs from expected → possible Choice Scarf"
            )

        return None

    def detect_priority_interaction(self, move_used: str, went_first: bool,
                                   terrain_active: Optional[str] = None) -> Optional[MechanicConstraint]:
        """
        Detect priority move interactions

        Psychic Terrain blocks priority moves
        Grassy Glide has priority in Grassy Terrain

        Args:
            move_used: Move used
            went_first: Whether Pokemon went first
            terrain_active: Active terrain

        Returns:
            MechanicConstraint based on priority
        """
        priority_moves = {
            'Extreme Speed': 2, 'Fake Out': 3, 'Sucker Punch': 1,
            'Aqua Jet': 1, 'Ice Shard': 1, 'Mach Punch': 1,
            'Shadow Sneak': 1, 'Accelerock': 1, 'Quick Attack': 1,
            'Thunderclap': 1,  # Gen 9
        }

        # Grassy Glide has priority in Grassy Terrain
        if move_used == 'Grassy Glide' and went_first and terrain_active == 'Grassy Terrain':
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={},
                reason="Grassy Glide used in Grassy Terrain (has priority)"
            )

        # Priority blocked by Psychic Terrain
        if move_used in priority_moves and not went_first and terrain_active == 'Psychic Terrain':
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={},
                reason="Priority move blocked by Psychic Terrain"
            )

        return None

    def detect_air_balloon(self, pokemon: str, hit_by_ground_move: bool,
                          turns_in_battle: int) -> Optional[MechanicConstraint]:
        """
        Detect Air Balloon

        Air Balloon makes Pokemon immune to Ground moves until hit

        Args:
            pokemon: Pokemon species
            hit_by_ground_move: Whether hit by Ground-type move
            turns_in_battle: Turns since switched in

        Returns:
            MechanicConstraint for Air Balloon
        """
        # If hit by Ground move early, probably doesn't have Air Balloon
        if hit_by_ground_move and turns_in_battle <= 2:
            return MechanicConstraint(
                ruled_out_items={'Air Balloon'},
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={},
                reason="Hit by Ground move → not Air Balloon"
            )

        return None

    def detect_heavy_duty_boots(self, pokemon: str, pokemon_types: List[str],
                                hazard_type: str, took_hazard_damage: bool,
                                ability: Optional[str] = None,
                                revealed_item: Optional[str] = None) -> Optional[MechanicConstraint]:
        """
        Detect Heavy-Duty Boots (with proper exception handling)

        Heavy-Duty Boots makes Pokemon immune to ALL entry hazards
        BUT other things can also grant hazard immunity:
        - Flying types: Immune to Spikes, Toxic Spikes, Sticky Web (NOT Stealth Rock)
        - Levitate: Immune to Spikes, Toxic Spikes, Sticky Web (NOT Stealth Rock)
        - Air Balloon: Immune to Spikes, Toxic Spikes, Sticky Web (NOT Stealth Rock)
        - Poison/Steel types: Immune to Toxic Spikes only
        - Magic Guard: Immune to all indirect damage

        Args:
            pokemon: Pokemon species
            pokemon_types: List of Pokemon's types
            hazard_type: Type of hazard (Stealth Rock, Spikes, Toxic Spikes, Sticky Web)
            took_hazard_damage: Whether Pokemon took damage from hazard
            ability: Pokemon's ability (if known)
            revealed_item: Pokemon's item (if already revealed)

        Returns:
            MechanicConstraint based on hazard immunity analysis
        """
        if revealed_item:
            # Item already known, no detection needed
            return None

        # If took damage, definitely doesn't have Heavy-Duty Boots
        if took_hazard_damage:
            return MechanicConstraint(
                ruled_out_items={'Heavy-Duty Boots'},
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={},
                reason=f"Took {hazard_type} damage → not Heavy-Duty Boots"
            )

        # Pokemon did NOT take hazard damage - analyze why
        # Check for natural immunities

        # STEALTH ROCK - only Heavy-Duty Boots or Magic Guard grant immunity
        if hazard_type == 'Stealth Rock':
            if ability == 'Magic Guard':
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities={'Magic Guard'},
                    probability_boosts={},
                    reason="Immune to Stealth Rock via Magic Guard (not Heavy-Duty Boots)"
                )
            else:
                # No natural immunity to Stealth Rock exists
                # Must be Heavy-Duty Boots!
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items={'Heavy-Duty Boots'},
                    confirmed_abilities=set(),
                    probability_boosts={'Heavy-Duty Boots': 100.0},
                    reason="Immune to Stealth Rock → Heavy-Duty Boots confirmed (no natural immunity)"
                )

        # SPIKES / STICKY WEB - Flying, Levitate, or Air Balloon also grant immunity
        if hazard_type in ['Spikes', 'Sticky Web']:
            # Check natural immunities
            is_flying = 'Flying' in pokemon_types
            has_levitate = ability == 'Levitate'
            has_magic_guard = ability == 'Magic Guard'

            if is_flying:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason=f"Flying-type immune to {hazard_type} (not Heavy-Duty Boots)"
                )

            if has_levitate:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities={'Levitate'},
                    probability_boosts={},
                    reason=f"Levitate grants immunity to {hazard_type} (not Heavy-Duty Boots)"
                )

            if has_magic_guard:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities={'Magic Guard'},
                    probability_boosts={},
                    reason=f"Magic Guard grants immunity to {hazard_type} (not Heavy-Duty Boots)"
                )

            # Could be Air Balloon OR Heavy-Duty Boots
            # Can't confirm either without more information
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={'Heavy-Duty Boots': 3.0, 'Air Balloon': 3.0},
                reason=f"Immune to {hazard_type} → likely Heavy-Duty Boots OR Air Balloon"
            )

        # TOXIC SPIKES - Poison/Steel types, Flying, Levitate also grant immunity
        if hazard_type == 'Toxic Spikes':
            is_poison = 'Poison' in pokemon_types
            is_steel = 'Steel' in pokemon_types
            is_flying = 'Flying' in pokemon_types
            has_levitate = ability == 'Levitate'
            has_magic_guard = ability == 'Magic Guard'

            if is_poison:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason="Poison-type immune to Toxic Spikes (not Heavy-Duty Boots)"
                )

            if is_steel:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason="Steel-type immune to Toxic Spikes (not Heavy-Duty Boots)"
                )

            if is_flying:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason="Flying-type immune to Toxic Spikes (not Heavy-Duty Boots)"
                )

            if has_levitate:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities={'Levitate'},
                    probability_boosts={},
                    reason="Levitate grants immunity to Toxic Spikes (not Heavy-Duty Boots)"
                )

            if has_magic_guard:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities={'Magic Guard'},
                    probability_boosts={},
                    reason="Magic Guard grants immunity to Toxic Spikes (not Heavy-Duty Boots)"
                )

            # Could be Air Balloon OR Heavy-Duty Boots
            return MechanicConstraint(
                ruled_out_items=set(),
                ruled_out_abilities=set(),
                confirmed_items=set(),
                confirmed_abilities=set(),
                probability_boosts={'Heavy-Duty Boots': 3.0, 'Air Balloon': 3.0},
                reason="Immune to Toxic Spikes → likely Heavy-Duty Boots OR Air Balloon"
            )

        return None

    def detect_knock_off_interaction(self, move_used: str, damage_dealt: int,
                                    expected_damage: int) -> Optional[MechanicConstraint]:
        """
        Detect Knock Off damage boost

        Knock Off deals 1.5x damage if target has an item

        Args:
            move_used: Move used
            damage_dealt: Actual damage
            expected_damage: Expected base damage

        Returns:
            MechanicConstraint if item presence can be inferred
        """
        if move_used == 'Knock Off':
            # If damage is ~1.5x expected, opponent has item
            # If damage is ~1.0x expected, opponent has no item or knocked off
            damage_ratio = damage_dealt / max(expected_damage, 1)

            if 1.4 <= damage_ratio <= 1.6:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason="Knock Off dealt boosted damage → opponent has item"
                )
            elif 0.9 <= damage_ratio <= 1.1:
                return MechanicConstraint(
                    ruled_out_items=set(),
                    ruled_out_abilities=set(),
                    confirmed_items=set(),
                    confirmed_abilities=set(),
                    probability_boosts={},
                    reason="Knock Off dealt normal damage → opponent has no item"
                )

        return None

    def apply_all_constraints(self, pokemon: str, context: dict) -> List[MechanicConstraint]:
        """
        Apply all niche mechanic checks based on battle context

        Args:
            pokemon: Pokemon species
            context: Battle context with observations

        Returns:
            List of applicable MechanicConstraints
        """
        constraints = []

        # Check forme changes
        forme_constraint = self.detect_forme_change(pokemon, context)
        if forme_constraint:
            constraints.append(forme_constraint)

        # Check Paradox Pokemon
        if context.get('ability_activated'):
            paradox_constraint = self.detect_paradox_booster_energy(
                pokemon,
                True,
                context.get('weather'),
                context.get('terrain')
            )
            if paradox_constraint:
                constraints.append(paradox_constraint)

        # Check status orbs
        if context.get('status_inflicted'):
            status_constraint = self.detect_status_orb_activation(
                pokemon,
                context.get('status_inflicted'),
                context.get('ability'),
                context.get('took_damage', False)
            )
            if status_constraint:
                constraints.append(status_constraint)

        # Check multi-hit moves
        if context.get('move_used') and context.get('hits_count'):
            multi_hit_constraint = self.detect_multi_hit_interaction(
                context['move_used'],
                context.get('damage_taken', 0),
                context['hits_count']
            )
            if multi_hit_constraint:
                constraints.append(multi_hit_constraint)

        return constraints


def main():
    """Test niche mechanics detector"""
    detector = NicheMechanicsDetector()

    print("=" * 70)
    print("Niche Mechanics Detector - Test Cases")
    print("=" * 70)

    # Test 1: Paradox Pokemon Booster Energy
    print("\n[Test 1] Raging Bolt - Protosynthesis activation")
    print("-" * 70)
    constraint = detector.detect_paradox_booster_energy(
        pokemon="Raging Bolt",
        ability_activated=True,
        weather_active=None,  # No sun
        terrain_active=None
    )
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Confirmed items: {constraint.confirmed_items}")
        print(f"  Probability boosts: {constraint.probability_boosts}")

    # Test 2: Forme change
    print("\n[Test 2] Ogerpon-Wellspring - Forme change")
    print("-" * 70)
    constraint = detector.detect_forme_change("Ogerpon-Wellspring", {})
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Confirmed items: {constraint.confirmed_items}")

    # Test 3: Status orb
    print("\n[Test 3] Pokemon with Guts - Self-inflicted burn")
    print("-" * 70)
    constraint = detector.detect_status_orb_activation(
        pokemon="Ursaluna",
        status_inflicted="burn",
        ability="Guts",
        took_damage=False
    )
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Probability boosts: {constraint.probability_boosts}")

    # Test 4: Multi-hit with Loaded Dice
    print("\n[Test 4] Bullet Seed - 5 hits")
    print("-" * 70)
    constraint = detector.detect_multi_hit_interaction(
        move_used="Bullet Seed",
        damage_taken=100,
        hits_count=5
    )
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Probability boosts: {constraint.probability_boosts}")

    # Test 5: Heavy-Duty Boots (Stealth Rock - CONFIRMED)
    print("\n[Test 5] Kingambit - Immune to Stealth Rock")
    print("-" * 70)
    constraint = detector.detect_heavy_duty_boots(
        pokemon="Kingambit",
        pokemon_types=["Dark", "Steel"],
        hazard_type="Stealth Rock",
        took_hazard_damage=False,  # Didn't take damage
        ability="Supreme Overlord"
    )
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Confirmed items: {constraint.confirmed_items}")

    # Test 6: Heavy-Duty Boots (Spikes - AMBIGUOUS)
    print("\n[Test 6] Kingambit - Immune to Spikes")
    print("-" * 70)
    constraint = detector.detect_heavy_duty_boots(
        pokemon="Kingambit",
        pokemon_types=["Dark", "Steel"],
        hazard_type="Spikes",
        took_hazard_damage=False,
        ability="Supreme Overlord"
    )
    if constraint:
        print(f"✓ {constraint.reason}")
        print(f"  Probability boosts: {constraint.probability_boosts}")

    # Test 7: NOT Heavy-Duty Boots (Flying type)
    print("\n[Test 7] Corviknight - Immune to Spikes (Flying type)")
    print("-" * 70)
    constraint = detector.detect_heavy_duty_boots(
        pokemon="Corviknight",
        pokemon_types=["Flying", "Steel"],
        hazard_type="Spikes",
        took_hazard_damage=False,
        ability="Pressure"
    )
    if constraint:
        print(f"✓ {constraint.reason}")

    # Test 8: NOT Heavy-Duty Boots (Poison type + Toxic Spikes)
    print("\n[Test 8] Gliscor - Immune to Toxic Spikes (Poison type)")
    print("-" * 70)
    constraint = detector.detect_heavy_duty_boots(
        pokemon="Gliscor",
        pokemon_types=["Ground", "Flying"],  # Actually Flying
        hazard_type="Toxic Spikes",
        took_hazard_damage=False,
        ability="Poison Heal"
    )
    if constraint:
        print(f"✓ {constraint.reason}")

    print("\n" + "=" * 70)
    print("All tests complete!")


if __name__ == "__main__":
    main()
