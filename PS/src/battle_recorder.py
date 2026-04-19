"""
Battle History Recorder
Records complete battle information for machine learning training
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path


@dataclass
class RevealedTiming:
    """Track when information was revealed"""
    first_seen: int  # Turn number
    moves: List[int]  # Turn numbers for each move
    ability: Optional[int] = None
    item: Optional[int] = None
    tera_type: Optional[int] = None


@dataclass
class TeamContext:
    """Team composition context"""
    player_lead: str
    visible_threats: List[str]  # Pokemon that could threaten this Pokemon
    team_types: Dict[str, float]  # Type distribution


@dataclass
class PokemonRecord:
    """Complete record of a Pokemon seen in battle"""
    species: str
    ability: str
    item: str
    moves: List[str]
    tera_type: Optional[str]
    spread: Optional[str]  # e.g., "Adamant:0/252/4/0/0/252"

    # What we observed during battle
    revealed_moves: List[str]
    revealed_timing: RevealedTiming
    team_context: TeamContext

    # Battle state when first seen
    turn_first_seen: int
    opponent_rating: Optional[int] = None


@dataclass
class BattleRecord:
    """Complete battle record"""
    battle_id: str
    timestamp: str
    tier: str
    player_rating: Optional[int]
    opponent_username: Optional[str]
    pokemon: List[PokemonRecord]

    # Battle outcome
    winner: Optional[str] = None  # 'player' or 'opponent'
    turn_count: Optional[int] = None


class BattleRecorder:
    """Records battle history for ML training"""

    def __init__(self, data_dir: Path = None):
        """
        Initialize battle recorder

        Args:
            data_dir: Directory to store battle history
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "battles"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.current_battle: Optional[BattleRecord] = None
        self.battle_history: List[BattleRecord] = []

        # Load existing history
        self._load_history()

    def start_battle(self, battle_id: str, tier: str,
                    player_rating: Optional[int] = None,
                    opponent_username: Optional[str] = None):
        """
        Start recording a new battle

        Args:
            battle_id: Unique battle identifier
            tier: Battle tier (e.g., "gen9ou")
            player_rating: Player's rating
            opponent_username: Opponent's username
        """
        self.current_battle = BattleRecord(
            battle_id=battle_id,
            timestamp=datetime.now().isoformat(),
            tier=tier,
            player_rating=player_rating,
            opponent_username=opponent_username,
            pokemon=[]
        )

    def record_pokemon(self, pokemon_data: PokemonRecord):
        """
        Record a Pokemon's complete set

        Args:
            pokemon_data: Complete Pokemon record
        """
        if self.current_battle is None:
            raise ValueError("No active battle. Call start_battle() first.")

        self.current_battle.pokemon.append(pokemon_data)

    def end_battle(self, winner: Optional[str] = None, turn_count: Optional[int] = None):
        """
        End current battle and save to history

        Args:
            winner: 'player' or 'opponent'
            turn_count: Total turns in battle
        """
        if self.current_battle is None:
            return

        self.current_battle.winner = winner
        self.current_battle.turn_count = turn_count

        # Add to history
        self.battle_history.append(self.current_battle)

        # Save to disk
        self._save_battle(self.current_battle)

        # Clear current battle
        self.current_battle = None

    def get_all_battles(self, tier: Optional[str] = None,
                       min_rating: Optional[int] = None) -> List[BattleRecord]:
        """
        Get all recorded battles with optional filters

        Args:
            tier: Filter by tier
            min_rating: Minimum rating

        Returns:
            List of battle records
        """
        battles = self.battle_history

        if tier:
            battles = [b for b in battles if b.tier == tier]

        if min_rating:
            battles = [b for b in battles if b.player_rating and b.player_rating >= min_rating]

        return battles

    def get_pokemon_records(self, species: Optional[str] = None,
                          tier: Optional[str] = None) -> List[PokemonRecord]:
        """
        Get all Pokemon records with optional filters

        Args:
            species: Filter by Pokemon species
            tier: Filter by tier

        Returns:
            List of Pokemon records
        """
        records = []
        battles = self.get_all_battles(tier=tier)

        for battle in battles:
            for pokemon in battle.pokemon:
                if species is None or pokemon.species == species:
                    records.append(pokemon)

        return records

    def get_statistics(self) -> Dict:
        """
        Get statistics about recorded battles

        Returns:
            Dictionary with statistics
        """
        total_battles = len(self.battle_history)
        total_pokemon = sum(len(b.pokemon) for b in self.battle_history)

        species_counts = {}
        for battle in self.battle_history:
            for pokemon in battle.pokemon:
                species_counts[pokemon.species] = species_counts.get(pokemon.species, 0) + 1

        return {
            'total_battles': total_battles,
            'total_pokemon': total_pokemon,
            'unique_species': len(species_counts),
            'most_common': sorted(species_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }

    def _save_battle(self, battle: BattleRecord):
        """Save battle to disk"""
        filename = f"{battle.battle_id}.json"
        filepath = self.data_dir / filename

        with open(filepath, 'w') as f:
            json.dump(asdict(battle), f, indent=2)

    def _load_history(self):
        """Load all battles from disk"""
        if not self.data_dir.exists():
            return

        for filepath in self.data_dir.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    # Convert dicts back to dataclasses
                    battle = self._dict_to_battle_record(data)
                    self.battle_history.append(battle)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")

    def _dict_to_battle_record(self, data: dict) -> BattleRecord:
        """Convert dictionary to BattleRecord"""
        pokemon = []
        for p in data['pokemon']:
            pokemon.append(PokemonRecord(
                species=p['species'],
                ability=p['ability'],
                item=p['item'],
                moves=p['moves'],
                tera_type=p.get('tera_type'),
                spread=p.get('spread'),
                revealed_moves=p['revealed_moves'],
                revealed_timing=RevealedTiming(**p['revealed_timing']),
                team_context=TeamContext(**p['team_context']),
                turn_first_seen=p['turn_first_seen'],
                opponent_rating=p.get('opponent_rating')
            ))

        return BattleRecord(
            battle_id=data['battle_id'],
            timestamp=data['timestamp'],
            tier=data['tier'],
            player_rating=data.get('player_rating'),
            opponent_username=data.get('opponent_username'),
            pokemon=pokemon,
            winner=data.get('winner'),
            turn_count=data.get('turn_count')
        )

    def export_for_ml(self, output_file: Path = None) -> Path:
        """
        Export battle history in format suitable for ML training

        Args:
            output_file: Output file path

        Returns:
            Path to exported file
        """
        if output_file is None:
            output_file = self.data_dir / "ml_training_data.json"

        # Create simplified format for ML
        ml_data = []
        for battle in self.battle_history:
            for pokemon in battle.pokemon:
                ml_data.append({
                    'pokemon': pokemon.species,
                    'tier': battle.tier,
                    'rating': battle.player_rating,
                    'turn_first_seen': pokemon.turn_first_seen,
                    'revealed_moves': pokemon.revealed_moves,
                    'revealed_move_count': len(pokemon.revealed_moves),
                    'move_reveal_turns': pokemon.revealed_timing.moves,
                    'team_context': asdict(pokemon.team_context),

                    # Targets
                    'actual_item': pokemon.item,
                    'actual_ability': pokemon.ability,
                    'actual_moves': pokemon.moves,
                    'actual_tera': pokemon.tera_type,
                    'actual_spread': pokemon.spread
                })

        with open(output_file, 'w') as f:
            json.dump(ml_data, f, indent=2)

        return output_file


def main():
    """Test battle recorder"""
    recorder = BattleRecorder()

    # Example: Record a battle
    recorder.start_battle(
        battle_id="gen9ou-test123",
        tier="gen9ou",
        player_rating=1650
    )

    # Record a Pokemon
    recorder.record_pokemon(PokemonRecord(
        species="Kingambit",
        ability="Supreme Overlord",
        item="Leftovers",
        moves=["Sucker Punch", "Swords Dance", "Kowtow Cleave", "Iron Head"],
        tera_type="Ghost",
        spread="Adamant:0/252/4/0/0/252",
        revealed_moves=["Sucker Punch", "Swords Dance"],
        revealed_timing=RevealedTiming(
            first_seen=1,
            moves=[3, 5],
            ability=3,
            item=8
        ),
        team_context=TeamContext(
            player_lead="Great Tusk",
            visible_threats=["Kyurem", "Zapdos"],
            team_types={"Ground": 0.33, "Steel": 0.17}
        ),
        turn_first_seen=1,
        opponent_rating=1680
    ))

    recorder.end_battle(winner="player", turn_count=15)

    # Print statistics
    stats = recorder.get_statistics()
    print("Battle Recorder Statistics:")
    print(f"Total battles: {stats['total_battles']}")
    print(f"Total Pokemon: {stats['total_pokemon']}")
    print(f"Unique species: {stats['unique_species']}")

    # Export for ML
    ml_file = recorder.export_for_ml()
    print(f"\nML training data exported to: {ml_file}")


if __name__ == "__main__":
    main()
