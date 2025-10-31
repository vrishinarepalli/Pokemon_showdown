#!/usr/bin/env python3
"""
Convert Smogon usage data to JavaScript format for Chrome extension
"""
import json
from pathlib import Path


def main():
    print("Converting Smogon data to JavaScript...")

    # Load usage data
    usage_file = Path("data/usage/gen9ou_usage.json")
    moveset_file = Path("data/usage/gen9ou_movesets.json")

    if not usage_file.exists() or not moveset_file.exists():
        print("Error: Data files not found. Run update_data.py first.")
        return 1

    with open(usage_file, 'r') as f:
        usage_data = json.load(f)

    with open(moveset_file, 'r') as f:
        moveset_data = json.load(f)

    # Combine data
    combined_data = {
        "usage": usage_data,
        "movesets": moveset_data
    }

    # Write as JavaScript file
    output_file = Path("extension/lib/smogon_data.js")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        f.write("// Smogon OU Usage Data (Generated)\n")
        f.write("// Last updated: " + usage_data.get('last_updated', 'unknown') + "\n\n")
        f.write("const SMOGON_DATA = ")
        json.dump(combined_data, f, indent=2)
        f.write(";\n")

    print(f"✓ Data converted to {output_file}")
    print(f"  - {len(usage_data.get('pokemon', []))} Pokemon in usage stats")
    print(f"  - {len(moveset_data)} Pokemon with moveset data")

    return 0


if __name__ == "__main__":
    exit(main())
