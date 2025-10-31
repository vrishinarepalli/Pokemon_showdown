"""
Pokemon Data Parser Module
Fetches and parses Pokemon, move, and item data from Pokemon Showdown
"""
import requests
import json
import re
from pathlib import Path
from typing import Dict, List, Optional


class PokemonShowdownParser:
    """Parses Pokemon data from Pokemon Showdown's GitHub repository"""

    # Pokemon Showdown data repository
    BASE_URL = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data"

    DATA_DIR = Path("data/pokemon")

    def __init__(self):
        """Initialize the parser"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_pokedex(self) -> Dict:
        """
        Fetch Pokemon data (Pokedex)

        Returns:
            Dictionary with Pokemon data
        """
        url = f"{self.BASE_URL}/pokedex.ts"
        print(f"Fetching Pokedex data from Pokemon Showdown...")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse TypeScript export to JSON
            pokedex_data = self._parse_typescript_export(response.text)

            # Save to file
            output_file = self.DATA_DIR / "pokedex.json"
            with open(output_file, 'w') as f:
                json.dump(pokedex_data, f, indent=2)

            print(f"✓ Pokedex data saved to {output_file}")
            print(f"  - {len(pokedex_data)} Pokemon loaded")
            return pokedex_data

        except requests.RequestException as e:
            print(f"✗ Error fetching Pokedex: {e}")
            return {}

    def fetch_moves(self) -> Dict:
        """
        Fetch moves data

        Returns:
            Dictionary with move data
        """
        url = f"{self.BASE_URL}/moves.ts"
        print(f"Fetching moves data from Pokemon Showdown...")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse TypeScript export to JSON
            moves_data = self._parse_typescript_export(response.text)

            # Save to file
            output_file = self.DATA_DIR / "moves.json"
            with open(output_file, 'w') as f:
                json.dump(moves_data, f, indent=2)

            print(f"✓ Moves data saved to {output_file}")
            print(f"  - {len(moves_data)} moves loaded")
            return moves_data

        except requests.RequestException as e:
            print(f"✗ Error fetching moves: {e}")
            return {}

    def fetch_items(self) -> Dict:
        """
        Fetch items data

        Returns:
            Dictionary with item data
        """
        url = f"{self.BASE_URL}/items.ts"
        print(f"Fetching items data from Pokemon Showdown...")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse TypeScript export to JSON
            items_data = self._parse_typescript_export(response.text)

            # Save to file
            output_file = self.DATA_DIR / "items.json"
            with open(output_file, 'w') as f:
                json.dump(items_data, f, indent=2)

            print(f"✓ Items data saved to {output_file}")
            print(f"  - {len(items_data)} items loaded")
            return items_data

        except requests.RequestException as e:
            print(f"✗ Error fetching items: {e}")
            return {}

    def fetch_abilities(self) -> Dict:
        """
        Fetch abilities data

        Returns:
            Dictionary with ability data
        """
        url = f"{self.BASE_URL}/abilities.ts"
        print(f"Fetching abilities data from Pokemon Showdown...")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse TypeScript export to JSON
            abilities_data = self._parse_typescript_export(response.text)

            # Save to file
            output_file = self.DATA_DIR / "abilities.json"
            with open(output_file, 'w') as f:
                json.dump(abilities_data, f, indent=2)

            print(f"✓ Abilities data saved to {output_file}")
            print(f"  - {len(abilities_data)} abilities loaded")
            return abilities_data

        except requests.RequestException as e:
            print(f"✗ Error fetching abilities: {e}")
            return {}

    def _parse_typescript_export(self, ts_content: str) -> Dict:
        """
        Parse TypeScript export to Python dictionary

        This is a simplified parser that works for Pokemon Showdown's data format.
        The files export objects like: export const BattlePokedex: {[name: string]: SpeciesData} = {

        Args:
            ts_content: TypeScript file content

        Returns:
            Parsed dictionary
        """
        # Find the main export object
        # Pattern: export const Name = { ... };
        pattern = r'export const \w+(?::\s*\{[^}]+\})?\s*=\s*(\{[\s\S]*?\n\};)'
        match = re.search(pattern, ts_content)

        if not match:
            print("Warning: Could not find TypeScript export pattern")
            return {}

        object_str = match.group(1)

        # Remove the trailing '};'
        if object_str.endswith('};'):
            object_str = object_str[:-2] + '}'

        # Convert TypeScript object to JSON-like format
        # This is a simplified conversion that handles common cases
        try:
            # Replace single quotes with double quotes (careful with contractions)
            json_str = object_str

            # Handle trailing commas (allowed in TS, not in JSON)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

            # Convert undefined to null
            json_str = json_str.replace('undefined', 'null')

            # This is still TypeScript-like, so we need a more robust approach
            # For now, return a simplified structure
            # In production, consider using a TS->JSON converter or the actual API

            return self._extract_pokemon_data_simple(ts_content)

        except Exception as e:
            print(f"Error parsing TypeScript: {e}")
            return self._extract_pokemon_data_simple(ts_content)

    def _extract_pokemon_data_simple(self, content: str) -> Dict:
        """
        Simplified extraction of Pokemon data using regex patterns

        Args:
            content: File content

        Returns:
            Extracted data dictionary
        """
        data = {}

        # Extract individual Pokemon entries
        # Pattern: pokemonid: { ... },
        pokemon_pattern = r'(\w+):\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\},'

        matches = re.finditer(pokemon_pattern, content)

        for match in matches:
            pokemon_id = match.group(1)
            pokemon_data_str = match.group(2)

            pokemon_info = {}

            # Extract common fields
            fields = {
                'num': r'num:\s*(\d+)',
                'name': r'name:\s*["\']([^"\']+)["\']',
                'types': r'types:\s*\[([^\]]+)\]',
                'baseStats': r'baseStats:\s*\{([^}]+)\}',
                'abilities': r'abilities:\s*\{([^}]+)\}',
                'weightkg': r'weightkg:\s*([\d.]+)',
            }

            for field, pattern in fields.items():
                field_match = re.search(pattern, pokemon_data_str)
                if field_match:
                    value = field_match.group(1)

                    if field == 'types':
                        # Parse array of types
                        types = re.findall(r'["\']([^"\']+)["\']', value)
                        pokemon_info[field] = types
                    elif field == 'baseStats':
                        # Parse base stats object
                        stats = {}
                        stats_pattern = r'(\w+):\s*(\d+)'
                        for stat_match in re.finditer(stats_pattern, value):
                            stats[stat_match.group(1)] = int(stat_match.group(2))
                        pokemon_info[field] = stats
                    elif field == 'abilities':
                        # Parse abilities object
                        abilities = {}
                        abilities_pattern = r'(\w+):\s*["\']([^"\']+)["\']'
                        for ability_match in re.finditer(abilities_pattern, value):
                            abilities[ability_match.group(1)] = ability_match.group(2)
                        pokemon_info[field] = abilities
                    elif field == 'num':
                        pokemon_info[field] = int(value)
                    elif field == 'weightkg':
                        pokemon_info[field] = float(value)
                    else:
                        pokemon_info[field] = value

            if pokemon_info:
                data[pokemon_id] = pokemon_info

        return data

    def fetch_all_data(self) -> bool:
        """
        Fetch all Pokemon data (Pokedex, moves, items, abilities)

        Returns:
            True if successful, False otherwise
        """
        print(f"\n=== Fetching Pokemon Showdown data ===\n")

        pokedex = self.fetch_pokedex()
        moves = self.fetch_moves()
        items = self.fetch_items()
        abilities = self.fetch_abilities()

        success = bool(pokedex and moves and items and abilities)

        if success:
            print(f"\n✓ Successfully fetched all Pokemon data")
        else:
            print(f"\n✗ Failed to fetch complete Pokemon data")

        return success


def main():
    """Main entry point for Pokemon data parsing"""
    parser = PokemonShowdownParser()
    parser.fetch_all_data()


if __name__ == "__main__":
    main()
