"""Debug helper: dump teams in Showdown teambuilder import format.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots will:
1. Print their team to terminal in Showdown's standard import/export format
2. Write to ./battle_teams/{battle_id}.txt

The output can be copy-pasted into Showdown's teambuilder:
  https://play.pokemonshowdown.com/teambuilder
  -> "Import from Text" button -> paste -> visual team display

Example output:
    === ExpecM4 TEAM ===
    Arceus @ Sky Plate
    Ability: Multitype
    Level: 69
    Tera Type: Steel
    EVs: 85 HP / 85 Atk / 85 Def / 85 SpA / 85 SpD / 85 Spe
    - Calm Mind
    - Recover
    - Earth Power
    - Judgment
"""

import os
import sys
from pathlib import Path


LOG_DIR = Path("./battle_teams")


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def _pretty_name(name: str) -> str:
    """Convert 'earthpower' -> 'Earth Power', 'skyplate' -> 'Sky Plate'.

    Best-effort word splitting for poke-env's lowercased IDs.
    Common multi-word items/moves get explicit handling.
    """
    # Manual overrides for common multi-word names that don't split cleanly
    overrides = {
        "choicescarf": "Choice Scarf",
        "choiceband": "Choice Band",
        "choicespecs": "Choice Specs",
        "heavydutyboots": "Heavy-Duty Boots",
        "lifeorb": "Life Orb",
        "focussash": "Focus Sash",
        "assaultvest": "Assault Vest",
        "rockyhelmet": "Rocky Helmet",
        "airballoon": "Air Balloon",
        "leftovers": "Leftovers",
        "lightclay": "Light Clay",
        "mentalherb": "Mental Herb",
        "skyplate": "Sky Plate",
        "earthplate": "Earth Plate",
        "flameplate": "Flame Plate",
        "splashplate": "Splash Plate",
        "toxicplate": "Toxic Plate",
        "piningplate": "Pining Plate",
        "stormplate": "Storm Plate",
        "insectplate": "Insect Plate",
        "spookyplate": "Spooky Plate",
        "mindplate": "Mind Plate",
        "fistplate": "Fist Plate",
        "ironplate": "Iron Plate",
        "meadowplate": "Meadow Plate",
        "zapplate": "Zap Plate",
        "icicleplate": "Icicle Plate",
        "dracoplate": "Draco Plate",
        "dreadplate": "Dread Plate",
        "pixieplate": "Pixie Plate",
        # Abilities
        "roughskin": "Rough Skin",
        "dryskin": "Dry Skin",
        "flashfire": "Flash Fire",
        "swiftswim": "Swift Swim",
        "solidrock": "Solid Rock",
        "intimidate": "Intimidate",
        # Moves
        "earthpower": "Earth Power",
        "calmmind": "Calm Mind",
        "swordsdance": "Swords Dance",
        "dragondance": "Dragon Dance",
        "nastyplot": "Nasty Plot",
        "bulkup": "Bulk Up",
        "irondefense": "Iron Defense",
        "closecombat": "Close Combat",
        "stoneedge": "Stone Edge",
        "gigaimpact": "Giga Impact",
        "flareblitz": "Flare Blitz",
        "flamecharge": "Flame Charge",
        "stompingtantrum": "Stomping Tantrum",
        "quickattack": "Quick Attack",
        "bodyslam": "Body Slam",
        "knockoff": "Knock Off",
        "gunkshot": "Gunk Shot",
        "earthquake": "Earthquake",
        "waterfall": "Waterfall",
        "flipturn": "Flip Turn",
        "poisonjab": "Poison Jab",
        "liquidation": "Liquidation",
        "dracometeor": "Draco Meteor",
        "aurasphere": "Aura Sphere",
        "lusterpurge": "Luster Purge",
        "overheat": "Overheat",
        "stealthrock": "Stealth Rock",
        "spikes": "Spikes",
        "toxicspikes": "Toxic Spikes",
        "stickyweb": "Sticky Web",
        "willowisp": "Will-O-Wisp",
        "thunderwave": "Thunder Wave",
        "sleeppowder": "Sleep Powder",
        "stunspore": "Stun Spore",
        "poisonpowder": "Poison Powder",
        "recover": "Recover",
        "roost": "Roost",
        "slackoff": "Slack Off",
        "milkdrink": "Milk Drink",
        "softboiled": "Soft-Boiled",
        "morningsun": "Morning Sun",
        "synthesis": "Synthesis",
        "moonlight": "Moonlight",
        "shoreup": "Shore Up",
        "wish": "Wish",
        "toxic": "Toxic",
        "judgment": "Judgment",
    }
    key = name.lower().replace("-", "").replace(" ", "").replace("_", "")
    if key in overrides:
        return overrides[key]
    # Fallback: capitalize each word by known split heuristic
    return name.replace("_", " ").replace("-", " ").title()


def format_team(battle, username: str) -> str:
    """Format team in Showdown teambuilder import/export format."""
    out = [f"=== {username} TEAM ==="]
    team = battle.team or {}
    for ident, mon in team.items():
        species = getattr(mon, "species", "?")
        level = getattr(mon, "level", 100)
        item_raw = getattr(mon, "item", None)
        ability_raw = getattr(mon, "ability", None) or "?"
        tera = getattr(mon, "tera_type", None)

        # Species @ Item
        item = _pretty_name(item_raw) if item_raw else None
        header = species.title()
        if item:
            header += f" @ {item}"
        out.append("")
        out.append(header)

        # Ability
        out.append(f"Ability: {_pretty_name(ability_raw)}")

        # Level (only if not 100)
        if level != 100:
            out.append(f"Level: {level}")

        # Tera
        if tera:
            tera_name = getattr(tera, "name", str(tera)).title()
            out.append(f"Tera Type: {tera_name}")

        # EVs (standard Gen 9 random battle spread)
        out.append("EVs: 85 HP / 85 Atk / 85 Def / 85 SpA / 85 SpD / 85 Spe")

        # Moves
        moves = (mon.moves or {}).values()
        for move in moves:
            out.append(f"- {_pretty_name(move.id)}")

    return "\n".join(out)


def announce_team(player, battle) -> None:
    """Print team in Showdown import format to terminal and file."""
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    text = format_team(battle, player.username)

    # Print to terminal
    print(text, file=sys.stdout, flush=True)
    print("", file=sys.stdout, flush=True)  # blank line separator

    # Also write to per-battle file
    try:
        LOG_DIR.mkdir(exist_ok=True)
        battle_file = LOG_DIR / f"{battle.battle_tag.replace('/', '_')}.txt"
        with battle_file.open("a") as f:
            f.write(text + "\n\n")
    except Exception as e:
        print(f"[announce] file write failed: {e}", file=sys.stderr, flush=True)
