"""
Data Fetcher Module
Downloads latest usage statistics from Smogon
"""
import requests
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict


class SmogonDataFetcher:
    """Fetches usage statistics and moveset data from Smogon"""

    BASE_URL = "https://www.smogon.com/stats"
    CACHE_DIR = Path("data/cache")
    USAGE_DIR = Path("data/usage")

    def __init__(self, tier: str = "gen9ou", rating: int = 1500):
        """
        Initialize the data fetcher

        Args:
            tier: The tier to fetch data for (default: gen9ou)
            rating: The rating threshold for stats (default: 1500)
        """
        self.tier = tier
        self.rating = rating
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.USAGE_DIR.mkdir(parents=True, exist_ok=True)

    def get_latest_month(self) -> str:
        """
        Get the latest month available on Smogon stats
        Automatically finds the most recent available data

        Returns:
            Month string in format YYYY-MM
        """
        # Try to fetch the stats page to find latest month
        try:
            response = requests.get(self.BASE_URL, timeout=10)
            response.raise_for_status()

            # Parse HTML to find latest month directories
            # Format: YYYY-MM/
            import re
            months = re.findall(r'(\d{4}-\d{2})/', response.text)
            if months:
                # Get the most recent month
                latest = sorted(months)[-1]
                print(f"  Found latest month: {latest}")
                return latest
        except Exception as e:
            print(f"  Could not auto-detect latest month: {e}")

        # Fallback: Use current year-month minus 1
        now = datetime.now()
        # Smogon stats are usually 1 month behind
        month = now.month - 1
        year = now.year
        if month == 0:
            month = 12
            year -= 1

        latest = f"{year}-{month:02d}"
        print(f"  Using fallback month: {latest}")
        return latest

    def fetch_usage_stats(self, month: Optional[str] = None) -> Dict:
        """
        Fetch usage statistics for a specific month

        Args:
            month: Month in format YYYY-MM (defaults to latest)

        Returns:
            Dictionary with usage statistics
        """
        if month is None:
            month = self.get_latest_month()

        url = f"{self.BASE_URL}/{month}/{self.tier}-{self.rating}.txt"
        print(f"Fetching usage stats from: {url}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse the usage stats
            usage_data = self._parse_usage_stats(response.text)

            # Save to file
            output_file = self.USAGE_DIR / f"{self.tier}_usage.json"
            with open(output_file, 'w') as f:
                json.dump(usage_data, f, indent=2)

            print(f"✓ Usage stats saved to {output_file}")
            return usage_data

        except requests.RequestException as e:
            print(f"✗ Error fetching usage stats: {e}")
            return {}

    def fetch_moveset_stats(self, month: Optional[str] = None) -> Dict:
        """
        Fetch detailed moveset statistics

        Args:
            month: Month in format YYYY-MM (defaults to latest)

        Returns:
            Dictionary with moveset statistics
        """
        if month is None:
            month = self.get_latest_month()

        url = f"{self.BASE_URL}/{month}/moveset/{self.tier}-{self.rating}.txt"
        print(f"Fetching moveset stats from: {url}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse the moveset stats
            moveset_data = self._parse_moveset_stats(response.text)

            # Save to file
            output_file = self.USAGE_DIR / f"{self.tier}_movesets.json"
            with open(output_file, 'w') as f:
                json.dump(moveset_data, f, indent=2)

            print(f"✓ Moveset stats saved to {output_file}")
            return moveset_data

        except requests.RequestException as e:
            print(f"✗ Error fetching moveset stats: {e}")
            return {}

    def _parse_usage_stats(self, text: str) -> Dict:
        """
        Parse usage statistics from Smogon text format

        Args:
            text: Raw text from Smogon usage stats

        Returns:
            Parsed usage data
        """
        usage_data = {
            "pokemon": [],
            "total_battles": 0,
            "avg_weight_per_team": 0.0
        }

        lines = text.split('\n')
        parsing_pokemon = False

        for line in lines:
            # Extract total battles (don't strip for this check)
            if "Total battles:" in line:
                try:
                    usage_data["total_battles"] = int(line.split(':')[1].strip())
                except:
                    pass

            # Extract average weight
            if "Avg. weight/team:" in line:
                try:
                    usage_data["avg_weight_per_team"] = float(line.split(':')[1].strip())
                except:
                    pass

            # Start of Pokemon rankings - look for the header separator
            if '+' in line and '----' in line:
                parsing_pokemon = True
                continue

            # Skip header line with column names
            if parsing_pokemon and 'Rank' in line and 'Pokemon' in line:
                continue

            # Skip separator lines
            if parsing_pokemon and '+' in line and '----' in line:
                continue

            # Parse Pokemon data
            if parsing_pokemon and "|" in line and line.strip().startswith('|'):
                parts = [p.strip() for p in line.split('|')]
                # Filter out empty parts from leading/trailing |
                parts = [p for p in parts if p]

                if len(parts) >= 3:
                    try:
                        rank = int(parts[0])
                        name = parts[1]
                        usage_percent = float(parts[2].rstrip('%'))

                        usage_data["pokemon"].append({
                            "rank": rank,
                            "name": name,
                            "usage_percent": usage_percent
                        })
                    except (ValueError, IndexError):
                        # Stop parsing if we hit a non-data line
                        if not parts[0].isdigit():
                            parsing_pokemon = False

        return usage_data

    def _parse_moveset_stats(self, text: str) -> Dict:
        """
        Parse moveset statistics from Smogon text format

        Args:
            text: Raw text from Smogon moveset stats

        Returns:
            Parsed moveset data
        """
        moveset_data = {}
        current_pokemon = None
        current_section = None

        lines = text.split('\n')

        for line in lines:
            stripped = line.strip()

            # Skip separator lines
            if stripped.startswith('+---'):
                continue

            # New Pokemon section - Pokemon name appears between | ... |
            # Look for lines that are ONLY the Pokemon name (surrounded by lots of dashes above/below)
            if stripped.startswith('|') and stripped.endswith('|') and '|' in line:
                parts = stripped.split('|')
                if len(parts) == 3 and parts[0] == '' and parts[2] == '':  # Format: | Name |
                    potential_name = parts[1].strip()

                    # Check if this is a Pokemon name (not a stat line or section header)
                    # Pokemon names won't have numbers, parentheses, colons, or percentages
                    if potential_name and not any(x in potential_name for x in [':', 'Raw count', 'Avg.', '%', 'KOed', 'switched', '(', ')', '±']):
                        # Skip section headers
                        if potential_name.lower() not in ['abilities', 'items', 'spreads', 'moves', 'tera types', 'teammates', 'checks and counters']:
                            current_pokemon = potential_name
                            current_section = None
                            moveset_data[current_pokemon] = {
                                "abilities": {},
                                "items": {},
                                "moves": {},
                                "spreads": {},
                                "teammates": {},
                                "tera_types": {}
                            }
                            continue

            # Section headers
            if current_pokemon and stripped.startswith('|') and stripped.endswith('|'):
                section_name = stripped.strip('| ').strip().lower()
                if section_name == 'abilities':
                    current_section = 'abilities'
                    continue
                elif section_name == 'items':
                    current_section = 'items'
                    continue
                elif section_name == 'moves':
                    current_section = 'moves'
                    continue
                elif section_name == 'spreads':
                    current_section = 'spreads'
                    continue
                elif section_name == 'teammates':
                    current_section = 'teammates'
                    continue
                elif section_name == 'tera types':
                    current_section = 'tera_types'
                    continue
                elif 'checks and counters' in section_name:
                    current_section = None  # Don't parse this section
                    continue

            # Parse data lines (format: "| Name percentage% |")
            if current_pokemon and current_section and stripped.startswith('|') and stripped.endswith('|'):
                data_line = stripped.strip('| ').strip()

                # Skip "Other" entries and empty lines
                if not data_line or data_line.startswith('Other'):
                    continue

                # Extract name and percentage
                # Format: "Name percentage%"
                if '%' in data_line:
                    try:
                        # Split by percentage sign
                        parts = data_line.split('%')[0]
                        # Last word before % is the number
                        words = parts.rsplit(None, 1)
                        if len(words) == 2:
                            name = words[0].strip()
                            percentage = float(words[1])

                            if name and current_pokemon in moveset_data:
                                moveset_data[current_pokemon][current_section][name] = percentage
                    except (ValueError, IndexError):
                        pass

        return moveset_data

    def fetch_all_data(self, month: Optional[str] = None) -> bool:
        """
        Fetch all data (usage + movesets) for a month

        Args:
            month: Month in format YYYY-MM (defaults to latest)

        Returns:
            True if successful, False otherwise
        """
        print(f"\n=== Fetching {self.tier.upper()} data ===\n")

        usage_data = self.fetch_usage_stats(month)
        moveset_data = self.fetch_moveset_stats(month)

        success = bool(usage_data and moveset_data)

        if success:
            print(f"\n✓ Successfully fetched all data for {self.tier}")
            print(f"  - {len(usage_data.get('pokemon', []))} Pokemon in usage stats")
            print(f"  - {len(moveset_data)} Pokemon with moveset data")
        else:
            print(f"\n✗ Failed to fetch complete data")

        return success


def main():
    """Main entry point for data fetching"""
    fetcher = SmogonDataFetcher(tier="gen9ou", rating=1500)
    fetcher.fetch_all_data()


if __name__ == "__main__":
    main()
