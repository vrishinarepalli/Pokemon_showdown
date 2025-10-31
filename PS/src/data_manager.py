"""
Data Manager Module
Handles loading, caching, and accessing Pokemon and usage data
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


class DataManager:
    """Manages access to Pokemon and usage data"""

    def __init__(self):
        """Initialize data manager"""
        self.pokemon_dir = Path("data/pokemon")
        self.usage_dir = Path("data/usage")

        # Cache for loaded data
        self._pokedex = None
        self._moves = None
        self._items = None
        self._abilities = None
        self._usage_stats = None
        self._moveset_stats = None

    def load_pokedex(self) -> Dict:
        """
        Load Pokedex data

        Returns:
            Dictionary of Pokemon data
        """
        if self._pokedex is None:
            pokedex_file = self.pokemon_dir / "pokedex.json"
            if pokedex_file.exists():
                with open(pokedex_file, 'r') as f:
                    self._pokedex = json.load(f)
            else:
                print(f"Warning: {pokedex_file} not found. Run data fetcher first.")
                self._pokedex = {}

        return self._pokedex

    def load_moves(self) -> Dict:
        """
        Load moves data

        Returns:
            Dictionary of move data
        """
        if self._moves is None:
            moves_file = self.pokemon_dir / "moves.json"
            if moves_file.exists():
                with open(moves_file, 'r') as f:
                    self._moves = json.load(f)
            else:
                print(f"Warning: {moves_file} not found. Run data fetcher first.")
                self._moves = {}

        return self._moves

    def load_items(self) -> Dict:
        """
        Load items data

        Returns:
            Dictionary of item data
        """
        if self._items is None:
            items_file = self.pokemon_dir / "items.json"
            if items_file.exists():
                with open(items_file, 'r') as f:
                    self._items = json.load(f)
            else:
                print(f"Warning: {items_file} not found. Run data fetcher first.")
                self._items = {}

        return self._items

    def load_abilities(self) -> Dict:
        """
        Load abilities data

        Returns:
            Dictionary of ability data
        """
        if self._abilities is None:
            abilities_file = self.pokemon_dir / "abilities.json"
            if abilities_file.exists():
                with open(abilities_file, 'r') as f:
                    self._abilities = json.load(f)
            else:
                print(f"Warning: {abilities_file} not found. Run data fetcher first.")
                self._abilities = {}

        return self._abilities

    def load_usage_stats(self, tier: str = "gen9ou") -> Dict:
        """
        Load usage statistics for a tier

        Args:
            tier: The tier to load stats for

        Returns:
            Dictionary with usage statistics
        """
        usage_file = self.usage_dir / f"{tier}_usage.json"
        if usage_file.exists():
            with open(usage_file, 'r') as f:
                self._usage_stats = json.load(f)
        else:
            print(f"Warning: {usage_file} not found. Run data fetcher first.")
            self._usage_stats = {}

        return self._usage_stats

    def load_moveset_stats(self, tier: str = "gen9ou") -> Dict:
        """
        Load moveset statistics for a tier

        Args:
            tier: The tier to load stats for

        Returns:
            Dictionary with moveset statistics
        """
        moveset_file = self.usage_dir / f"{tier}_movesets.json"
        if moveset_file.exists():
            with open(moveset_file, 'r') as f:
                self._moveset_stats = json.load(f)
        else:
            print(f"Warning: {moveset_file} not found. Run data fetcher first.")
            self._moveset_stats = {}

        return self._moveset_stats

    def get_pokemon_info(self, pokemon_name: str) -> Optional[Dict]:
        """
        Get information about a specific Pokemon

        Args:
            pokemon_name: Name of the Pokemon

        Returns:
            Pokemon data or None if not found
        """
        pokedex = self.load_pokedex()
        # Try exact match first
        pokemon_id = pokemon_name.lower().replace(' ', '').replace('-', '')

        if pokemon_id in pokedex:
            return pokedex[pokemon_id]

        # Try searching by name
        for pid, data in pokedex.items():
            if data.get('name', '').lower() == pokemon_name.lower():
                return data

        return None

    def get_top_pokemon(self, tier: str = "gen9ou", limit: int = 20) -> List[Dict]:
        """
        Get top Pokemon by usage in a tier

        Args:
            tier: The tier to get stats for
            limit: Number of top Pokemon to return

        Returns:
            List of top Pokemon with usage data
        """
        usage_stats = self.load_usage_stats(tier)
        pokemon_list = usage_stats.get('pokemon', [])

        return pokemon_list[:limit]

    def get_pokemon_moveset(self, pokemon_name: str, tier: str = "gen9ou") -> Optional[Dict]:
        """
        Get moveset data for a specific Pokemon

        Args:
            pokemon_name: Name of the Pokemon
            tier: The tier to get moveset for

        Returns:
            Moveset data or None if not found
        """
        moveset_stats = self.load_moveset_stats(tier)

        # Try exact match
        if pokemon_name in moveset_stats:
            return moveset_stats[pokemon_name]

        # Try case-insensitive match
        for name, data in moveset_stats.items():
            if name.lower() == pokemon_name.lower():
                return data

        return None

    def get_move_info(self, move_name: str) -> Optional[Dict]:
        """
        Get information about a specific move

        Args:
            move_name: Name of the move

        Returns:
            Move data or None if not found
        """
        moves = self.load_moves()
        move_id = move_name.lower().replace(' ', '').replace('-', '')

        if move_id in moves:
            return moves[move_id]

        return None

    def get_item_info(self, item_name: str) -> Optional[Dict]:
        """
        Get information about a specific item

        Args:
            item_name: Name of the item

        Returns:
            Item data or None if not found
        """
        items = self.load_items()
        item_id = item_name.lower().replace(' ', '').replace('-', '')

        if item_id in items:
            return items[item_id]

        return None

    def get_ability_info(self, ability_name: str) -> Optional[Dict]:
        """
        Get information about a specific ability

        Args:
            ability_name: Name of the ability

        Returns:
            Ability data or None if not found
        """
        abilities = self.load_abilities()
        ability_id = ability_name.lower().replace(' ', '').replace('-', '')

        if ability_id in abilities:
            return abilities[ability_id]

        return None

    def is_data_available(self) -> bool:
        """
        Check if all required data files are available

        Returns:
            True if all data is available, False otherwise
        """
        required_files = [
            self.pokemon_dir / "pokedex.json",
            self.pokemon_dir / "moves.json",
            self.pokemon_dir / "items.json",
            self.pokemon_dir / "abilities.json",
            self.usage_dir / "gen9ou_usage.json",
            self.usage_dir / "gen9ou_movesets.json",
        ]

        return all(f.exists() for f in required_files)


def main():
    """Test data manager functionality"""
    dm = DataManager()

    print("=== Testing Data Manager ===\n")

    if not dm.is_data_available():
        print("⚠ Data files not found. Please run data fetcher first.")
        return

    # Test loading data
    print("Loading data...")
    pokedex = dm.load_pokedex()
    moves = dm.load_moves()
    usage = dm.load_usage_stats()

    print(f"✓ Loaded {len(pokedex)} Pokemon")
    print(f"✓ Loaded {len(moves)} moves")
    print(f"✓ Loaded {len(usage.get('pokemon', []))} Pokemon with usage stats")

    # Test top Pokemon
    print("\n=== Top 10 Pokemon in OU ===")
    top_pokemon = dm.get_top_pokemon(limit=10)
    for i, pkmn in enumerate(top_pokemon, 1):
        print(f"{i}. {pkmn['name']}: {pkmn['usage_percent']:.2f}%")

    # Test getting specific Pokemon info
    if top_pokemon:
        test_pokemon = top_pokemon[0]['name']
        print(f"\n=== Moveset for {test_pokemon} ===")
        moveset = dm.get_pokemon_moveset(test_pokemon)
        if moveset:
            print(f"Abilities: {list(moveset.get('abilities', {}).keys())[:3]}")
            print(f"Items: {list(moveset.get('items', {}).keys())[:3]}")
            print(f"Moves: {list(moveset.get('moves', {}).keys())[:5]}")


if __name__ == "__main__":
    main()
