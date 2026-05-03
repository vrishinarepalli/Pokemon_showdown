"""
Pokemon Showdown Battle Log Parser
Parses Pokemon Showdown battle protocol to extract battle events
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class BattleEvent:
    """Represents a battle event"""
    event_type: str
    turn: int
    player: str  # 'p1' or 'p2'
    pokemon: Optional[str] = None
    move: Optional[str] = None
    item: Optional[str] = None
    ability: Optional[str] = None
    damage: Optional[str] = None
    status: Optional[str] = None
    weather: Optional[str] = None
    terrain: Optional[str] = None
    details: Optional[Dict] = None


class PokemonShowdownParser:
    """
    Parses Pokemon Showdown battle protocol

    Pokemon Showdown uses a pipe-delimited protocol:
    |switch|p2a: Kingambit|Kingambit, L50, M|100/100
    |move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
    |-damage|p1a: Great Tusk|65/100
    |move|p1a: Great Tusk|Close Combat|p2a: Kingambit
    |-damage|p2a: Kingambit|20/100
    """

    def __init__(self):
        """Initialize parser"""
        self.current_turn = 0
        self.battle_state = {
            'p1': {},  # Player 1's Pokemon
            'p2': {},  # Player 2's Pokemon (opponent)
            'weather': None,
            'terrain': None,
            'hazards': {
                'p1': [],  # Hazards on p1's side
                'p2': []   # Hazards on p2's side
            }
        }
        self.events = []

    def parse_line(self, line: str) -> Optional[BattleEvent]:
        """
        Parse a single line from the battle log

        Args:
            line: Battle log line (starts with |)

        Returns:
            BattleEvent if parseable, None otherwise
        """
        if not line or not line.startswith('|'):
            return None

        # Split by pipe delimiter
        parts = line.split('|')[1:]  # Skip empty first element
        if not parts:
            return None

        command = parts[0]

        # Dispatch to appropriate parser
        if command == 'switch' or command == 'drag':
            return self._parse_switch(parts)
        elif command == 'move':
            return self._parse_move(parts)
        elif command == '-damage':
            return self._parse_damage(parts)
        elif command == '-heal':
            return self._parse_heal(parts)
        elif command == '-status':
            return self._parse_status(parts)
        elif command == '-ability':
            return self._parse_ability(parts)
        elif command == '-item':
            return self._parse_item(parts)
        elif command == '-enditem':
            return self._parse_enditem(parts)
        elif command == 'weather':
            return self._parse_weather(parts)
        elif command == '-weather':
            return self._parse_weather(parts)
        elif command == 'terrain' or command == '-fieldstart':
            return self._parse_terrain(parts)
        elif command == 'turn':
            return self._parse_turn(parts)
        elif command == '-sidestart':
            return self._parse_sidestart(parts)
        elif command == 'faint':
            return self._parse_faint(parts)
        elif command == '-boost' or command == '-unboost':
            return self._parse_boost(parts)

        return None

    def _parse_switch(self, parts: List[str]) -> BattleEvent:
        """
        Parse switch/drag event
        Format: |switch|POKEMON|DETAILS|HP STATUS
        Example: |switch|p2a: Kingambit|Kingambit, L50, M|100/100
        """
        if len(parts) < 4:
            return None

        # Parse pokemon identifier (e.g., "p2a: Kingambit")
        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        # Parse details (e.g., "Kingambit, L50, M")
        details = parts[2]
        species = details.split(',')[0].strip()

        # Parse HP
        hp_status = parts[3]
        current_hp = self._parse_hp(hp_status)

        # Update battle state
        if player not in self.battle_state:
            self.battle_state[player] = {}

        self.battle_state[player][position] = {
            'species': species,
            'nickname': nickname,
            'hp': current_hp,
            'status': None,
            'revealed_moves': set(),
            'revealed_ability': None,
            'revealed_item': None
        }

        return BattleEvent(
            event_type='switch',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            details={'nickname': nickname, 'position': position, 'hp': current_hp}
        )

    def _parse_move(self, parts: List[str]) -> BattleEvent:
        """
        Parse move event
        Format: |move|POKEMON|MOVE|TARGET
        Example: |move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
        """
        if len(parts) < 3:
            return None

        # Parse attacker
        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        # Parse move name
        move = parts[2]

        # Track revealed move
        species = self.battle_state.get(player, {}).get(position, {}).get('species')
        if species and player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['revealed_moves'].add(move)

        return BattleEvent(
            event_type='move',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            move=move,
            details={'position': position}
        )

    def _parse_damage(self, parts: List[str]) -> BattleEvent:
        """
        Parse damage event
        Format: |-damage|POKEMON|HP STATUS
        Example: |-damage|p1a: Great Tusk|65/100
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        hp_status = parts[2]
        current_hp = self._parse_hp(hp_status)

        # Update HP
        if player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['hp'] = current_hp

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='damage',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            damage=hp_status,
            details={'hp': current_hp}
        )

    def _parse_heal(self, parts: List[str]) -> BattleEvent:
        """
        Parse heal event
        Format: |-heal|POKEMON|HP STATUS|[from] ITEM/ABILITY
        Example: |-heal|p2a: Kingambit|25/100|[from] item: Leftovers
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        hp_status = parts[2]
        current_hp = self._parse_hp(hp_status)

        # Check for heal source (Leftovers, Black Sludge, etc.)
        source = None
        if len(parts) >= 4 and parts[3].startswith('[from]'):
            source = parts[3].replace('[from] item:', '').replace('[from] ability:', '').strip()

        # Update HP
        if player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['hp'] = current_hp

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='heal',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            details={'hp': current_hp, 'source': source}
        )

    def _parse_status(self, parts: List[str]) -> BattleEvent:
        """
        Parse status event
        Format: |-status|POKEMON|STATUS
        Example: |-status|p2a: Kingambit|brn
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        status = parts[2]

        # Update status
        if player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['status'] = status

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='status',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            status=status
        )

    def _parse_ability(self, parts: List[str]) -> BattleEvent:
        """
        Parse ability reveal
        Format: |-ability|POKEMON|ABILITY
        Example: |-ability|p2a: Raging Bolt|Protosynthesis
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        ability = parts[2]

        # Update revealed ability
        if player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['revealed_ability'] = ability

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='ability',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            ability=ability
        )

    def _parse_item(self, parts: List[str]) -> BattleEvent:
        """
        Parse item reveal
        Format: |-item|POKEMON|ITEM
        Example: |-item|p2a: Kingambit|Leftovers
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        item = parts[2]

        # Update revealed item
        if player in self.battle_state and position in self.battle_state[player]:
            self.battle_state[player][position]['revealed_item'] = item

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='item',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            item=item
        )

    def _parse_enditem(self, parts: List[str]) -> BattleEvent:
        """
        Parse item removal (used/knocked off)
        Format: |-enditem|POKEMON|ITEM|[from] move: Knock Off
        Example: |-enditem|p2a: Kingambit|Leftovers|[from] move: Knock Off
        """
        if len(parts) < 3:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        item = parts[2]

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='enditem',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            item=item
        )

    def _parse_weather(self, parts: List[str]) -> BattleEvent:
        """
        Parse weather change
        Format: |-weather|WEATHER
        Example: |-weather|SunnyDay
        """
        if len(parts) < 2:
            return None

        weather = parts[1]
        self.battle_state['weather'] = weather

        return BattleEvent(
            event_type='weather',
            turn=self.current_turn,
            player='',
            weather=weather
        )

    def _parse_terrain(self, parts: List[str]) -> BattleEvent:
        """
        Parse terrain change
        Format: |-fieldstart|move: Electric Terrain
        Example: |-fieldstart|move: Electric Terrain
        """
        if len(parts) < 2:
            return None

        terrain_str = parts[1].replace('move:', '').strip()
        self.battle_state['terrain'] = terrain_str

        return BattleEvent(
            event_type='terrain',
            turn=self.current_turn,
            player='',
            terrain=terrain_str
        )

    def _parse_turn(self, parts: List[str]) -> BattleEvent:
        """
        Parse turn counter
        Format: |turn|NUMBER
        Example: |turn|5
        """
        if len(parts) < 2:
            return None

        self.current_turn = int(parts[1])

        return BattleEvent(
            event_type='turn',
            turn=self.current_turn,
            player=''
        )

    def _parse_sidestart(self, parts: List[str]) -> BattleEvent:
        """
        Parse hazard setup
        Format: |-sidestart|SIDE|HAZARD
        Example: |-sidestart|p2: Player|Stealth Rock
        """
        if len(parts) < 3:
            return None

        side = 'p1' if 'p1' in parts[1] else 'p2'
        hazard = parts[2]

        if side in self.battle_state['hazards']:
            self.battle_state['hazards'][side].append(hazard)

        return BattleEvent(
            event_type='hazard',
            turn=self.current_turn,
            player=side,
            details={'hazard': hazard}
        )

    def _parse_faint(self, parts: List[str]) -> BattleEvent:
        """
        Parse faint event
        Format: |faint|POKEMON
        Example: |faint|p2a: Kingambit
        """
        if len(parts) < 2:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='faint',
            turn=self.current_turn,
            player=player,
            pokemon=species
        )

    def _parse_boost(self, parts: List[str]) -> BattleEvent:
        """
        Parse stat boost/drop
        Format: |-boost|POKEMON|STAT|AMOUNT
        Example: |-boost|p2a: Raging Bolt|spa|1
        """
        if len(parts) < 4:
            return None

        pokemon_id = parts[1]
        player, position, nickname = self._parse_pokemon_id(pokemon_id)

        stat = parts[2]
        amount = int(parts[3])

        species = self.battle_state.get(player, {}).get(position, {}).get('species')

        return BattleEvent(
            event_type='boost',
            turn=self.current_turn,
            player=player,
            pokemon=species,
            details={'stat': stat, 'amount': amount}
        )

    def _parse_pokemon_id(self, pokemon_id: str) -> Tuple[str, str, str]:
        """
        Parse Pokemon identifier
        Format: "p2a: Kingambit" or "p1a: Great Tusk"

        Returns:
            (player, position, nickname)
        """
        if ':' in pokemon_id:
            position_part, nickname = pokemon_id.split(':', 1)
            nickname = nickname.strip()
        else:
            position_part = pokemon_id
            nickname = pokemon_id

        # Extract player and position (e.g., "p2a" -> player="p2", position="a")
        player = position_part[:2]  # "p1" or "p2"
        position = position_part[2:].strip()  # "a", "b", etc.

        return player, position, nickname

    def _parse_hp(self, hp_status: str) -> float:
        """
        Parse HP from status string
        Format: "65/100" or "65/100 par"

        Returns:
            HP as percentage (0-100)
        """
        hp_part = hp_status.split()[0]  # Remove status if present
        if '/' in hp_part:
            current, max_hp = hp_part.split('/')
            return (float(current) / float(max_hp)) * 100
        return 100.0

    def parse_battle_log(self, log_lines: List[str]) -> List[BattleEvent]:
        """
        Parse complete battle log

        Args:
            log_lines: List of battle log lines

        Returns:
            List of BattleEvents
        """
        events = []
        for line in log_lines:
            event = self.parse_line(line)
            if event:
                events.append(event)
                self.events.append(event)

        return events

    def get_pokemon_info(self, player: str, position: str) -> Optional[Dict]:
        """
        Get information about a specific Pokemon

        Args:
            player: 'p1' or 'p2'
            position: 'a', 'b', 'c', etc.

        Returns:
            Pokemon info dict or None
        """
        return self.battle_state.get(player, {}).get(position)


def main():
    """Test battle log parser"""
    print("=" * 70)
    print("Pokemon Showdown Battle Log Parser Test")
    print("=" * 70)

    # Example battle log
    battle_log = [
        "|turn|1",
        "|switch|p2a: Raging Bolt|Raging Bolt, L50|100/100",
        "|-ability|p2a: Raging Bolt|Protosynthesis",
        "|switch|p1a: Great Tusk|Great Tusk, L50|100/100",
        "|turn|2",
        "|move|p2a: Raging Bolt|Thunderbolt|p1a: Great Tusk",
        "|-damage|p1a: Great Tusk|65/100",
        "|move|p1a: Great Tusk|Earthquake|p2a: Raging Bolt",
        "|-damage|p2a: Raging Bolt|30/100",
        "|turn|3",
        "|move|p2a: Raging Bolt|Calm Mind|p2a: Raging Bolt",
        "|-boost|p2a: Raging Bolt|spa|1",
        "|-boost|p2a: Raging Bolt|spd|1",
        "|-heal|p2a: Raging Bolt|40/100|[from] item: Leftovers",
        "|move|p1a: Great Tusk|Close Combat|p2a: Raging Bolt",
        "|-damage|p2a: Raging Bolt|0 fnt",
        "|faint|p2a: Raging Bolt",
    ]

    # Parse battle log
    parser = PokemonShowdownParser()
    events = parser.parse_battle_log(battle_log)

    print("\nParsed Events:")
    print("-" * 70)
    for event in events:
        if event.event_type == 'switch':
            print(f"[Turn {event.turn}] {event.player} switched to {event.pokemon}")
        elif event.event_type == 'move':
            print(f"[Turn {event.turn}] {event.pokemon} used {event.move}")
        elif event.event_type == 'ability':
            print(f"[Turn {event.turn}] {event.pokemon}'s ability: {event.ability}")
        elif event.event_type == 'item':
            print(f"[Turn {event.turn}] {event.pokemon}'s item: {event.item}")
        elif event.event_type == 'damage':
            print(f"[Turn {event.turn}] {event.pokemon} took damage: {event.details['hp']:.1f}%")
        elif event.event_type == 'heal':
            print(f"[Turn {event.turn}] {event.pokemon} healed to {event.details['hp']:.1f}% " +
                  f"(from {event.details['source']})")
        elif event.event_type == 'boost':
            print(f"[Turn {event.turn}] {event.pokemon} {event.details['stat']} " +
                  f"{'+' if event.details['amount'] > 0 else ''}{event.details['amount']}")
        elif event.event_type == 'faint':
            print(f"[Turn {event.turn}] {event.pokemon} fainted")

    # Show tracked Pokemon
    print("\n\nTracked Pokemon:")
    print("-" * 70)
    for player in ['p1', 'p2']:
        for position, data in parser.battle_state.get(player, {}).items():
            print(f"\n{player}{position}: {data['species']}")
            print(f"  HP: {data['hp']:.1f}%")
            print(f"  Revealed moves: {data['revealed_moves']}")
            print(f"  Revealed ability: {data['revealed_ability']}")
            print(f"  Revealed item: {data['revealed_item']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
