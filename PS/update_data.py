#!/usr/bin/env python3
"""
Update Data Script
Fetches latest data from Smogon and Pokemon Showdown
"""
import sys
from src.data_fetcher import SmogonDataFetcher
from src.pokemon_data_parser import PokemonShowdownParser
from src.data_manager import DataManager


def main():
    """Main function to update all data"""
    print("=" * 60)
    print("Pokemon Team Generator - Data Update")
    print("=" * 60)

    # Step 1: Fetch Pokemon Showdown data
    print("\n[1/3] Fetching Pokemon Showdown data...")
    print("-" * 60)
    parser = PokemonShowdownParser()
    showdown_success = parser.fetch_all_data()

    if not showdown_success:
        print("\n✗ Failed to fetch Pokemon Showdown data")
        print("Continuing with Smogon data...")

    # Step 2: Fetch Smogon usage statistics
    print("\n[2/3] Fetching Smogon usage statistics...")
    print("-" * 60)
    fetcher = SmogonDataFetcher(tier="gen9ou", rating=1500)
    smogon_success = fetcher.fetch_all_data()

    if not smogon_success:
        print("\n✗ Failed to fetch Smogon usage data")
        return 1

    # Step 3: Verify data
    print("\n[3/3] Verifying data integrity...")
    print("-" * 60)
    dm = DataManager()

    if dm.is_data_available():
        print("✓ All data files present")

        # Load and display summary
        usage = dm.load_usage_stats()
        top_pokemon = dm.get_top_pokemon(limit=5)

        print(f"\n📊 Data Summary:")
        print(f"   - Total battles analyzed: {usage.get('total_battles', 'N/A')}")
        print(f"   - Pokemon tracked: {len(usage.get('pokemon', []))}")
        print(f"\n🏆 Top 5 Pokemon in OU:")
        for i, pkmn in enumerate(top_pokemon, 1):
            print(f"   {i}. {pkmn['name']}: {pkmn['usage_percent']:.2f}%")

        print("\n" + "=" * 60)
        print("✓ Data update complete!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some data files are missing")
        print("Please check the error messages above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
