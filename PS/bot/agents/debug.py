"""Debug helper: auto-create pokepastes and open in browser.

Enable via env var BOT_ANNOUNCE_TEAM=1. For the first battle in a run, each bot
posts its team to pokepast.es and opens the URL in the browser. Subsequent
battles are skipped to avoid spam - use --n-battles 1 for debugging.
"""

import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


LOG_DIR = Path("./battle_teams")

# Module-level state: only create pastes for first battle to avoid spam
_first_battle_id = None
_pasted_players = set()


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def _pretty_name(name: str) -> str:
    """Convert poke-env IDs to Showdown display format."""
    overrides = {
        "choicescarf": "Choice Scarf", "choiceband": "Choice Band",
        "choicespecs": "Choice Specs", "heavydutyboots": "Heavy-Duty Boots",
        "lifeorb": "Life Orb", "focussash": "Focus Sash",
        "assaultvest": "Assault Vest", "rockyhelmet": "Rocky Helmet",
        "airballoon": "Air Balloon", "leftovers": "Leftovers",
        "lightclay": "Light Clay", "mentalherb": "Mental Herb",
        "skyplate": "Sky Plate", "earthplate": "Earth Plate",
        "flameplate": "Flame Plate", "splashplate": "Splash Plate",
        "toxicplate": "Toxic Plate", "stormplate": "Storm Plate",
        "insectplate": "Insect Plate", "spookyplate": "Spooky Plate",
        "mindplate": "Mind Plate", "fistplate": "Fist Plate",
        "ironplate": "Iron Plate", "meadowplate": "Meadow Plate",
        "zapplate": "Zap Plate", "icicleplate": "Icicle Plate",
        "dracoplate": "Draco Plate", "dreadplate": "Dread Plate",
        "pixieplate": "Pixie Plate",
        "roughskin": "Rough Skin", "dryskin": "Dry Skin",
        "flashfire": "Flash Fire", "swiftswim": "Swift Swim",
        "solidrock": "Solid Rock", "intimidate": "Intimidate",
        "earthpower": "Earth Power", "calmmind": "Calm Mind",
        "swordsdance": "Swords Dance", "dragondance": "Dragon Dance",
        "nastyplot": "Nasty Plot", "bulkup": "Bulk Up",
        "irondefense": "Iron Defense", "closecombat": "Close Combat",
        "stoneedge": "Stone Edge", "gigaimpact": "Giga Impact",
        "flareblitz": "Flare Blitz", "flamecharge": "Flame Charge",
        "stompingtantrum": "Stomping Tantrum", "quickattack": "Quick Attack",
        "bodyslam": "Body Slam", "knockoff": "Knock Off",
        "gunkshot": "Gunk Shot", "earthquake": "Earthquake",
        "waterfall": "Waterfall", "flipturn": "Flip Turn",
        "poisonjab": "Poison Jab", "liquidation": "Liquidation",
        "dracometeor": "Draco Meteor", "aurasphere": "Aura Sphere",
        "lusterpurge": "Luster Purge", "overheat": "Overheat",
        "stealthrock": "Stealth Rock", "spikes": "Spikes",
        "toxicspikes": "Toxic Spikes", "stickyweb": "Sticky Web",
        "willowisp": "Will-O-Wisp", "thunderwave": "Thunder Wave",
        "sleeppowder": "Sleep Powder", "stunspore": "Stun Spore",
        "poisonpowder": "Poison Powder", "recover": "Recover",
        "roost": "Roost", "slackoff": "Slack Off",
        "milkdrink": "Milk Drink", "softboiled": "Soft-Boiled",
        "morningsun": "Morning Sun", "synthesis": "Synthesis",
        "moonlight": "Moonlight", "shoreup": "Shore Up",
        "wish": "Wish", "toxic": "Toxic", "judgment": "Judgment",
        "foulplay": "Foul Play", "doubleshock": "Double Shock",
        "bleakwindstorm": "Bleakwind Storm", "turboblaze": "Turboblaze",
    }
    if not name:
        return "?"
    key = name.lower().replace("-", "").replace(" ", "").replace("_", "")
    if key in overrides:
        return overrides[key]
    return name.replace("_", " ").replace("-", " ").title()


def format_team(battle, username: str) -> str:
    """Format team in Showdown teambuilder import/export format."""
    out = []
    team = battle.team or {}
    for ident, mon in team.items():
        species = getattr(mon, "species", "?")
        level = getattr(mon, "level", 100)
        item_raw = getattr(mon, "item", None)
        ability_raw = getattr(mon, "ability", None) or "?"
        tera = getattr(mon, "tera_type", None)

        header = species.title()
        if item_raw:
            header += f" @ {_pretty_name(item_raw)}"
        out.append(header)
        out.append(f"Ability: {_pretty_name(ability_raw)}")
        if level != 100:
            out.append(f"Level: {level}")
        if tera:
            tera_name = getattr(tera, "name", str(tera)).title()
            out.append(f"Tera Type: {tera_name}")
        out.append("EVs: 85 HP / 85 Atk / 85 Def / 85 SpA / 85 SpD / 85 Spe")
        for move in (mon.moves or {}).values():
            out.append(f"- {_pretty_name(move.id)}")
        out.append("")  # blank line between mons

    return "\n".join(out).rstrip() + "\n"


def _submit_pokepastes(team_text: str, title: str) -> str:
    """POST team to pokepast.es, return the paste URL. None on failure."""
    data = urllib.parse.urlencode({
        "paste": team_text,
        "title": title,
        "author": "M4 Bot Debug",
        "notes": "Auto-generated from local Showdown dev server",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://pokepast.es/create",
        data=data,
        method="POST",
        headers={"User-Agent": "poke-env-m4-debug/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.geturl()
    except Exception as e:
        print(f"[announce] pokepast.es submit failed: {e}", file=sys.stderr, flush=True)
        return None


def announce_team(player, battle) -> None:
    """Create pokepaste and open in browser for first battle only."""
    global _first_battle_id

    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    # Lock to first battle only (avoid spam with multi-battle runs)
    if _first_battle_id is None:
        _first_battle_id = battle.battle_tag
    if battle.battle_tag != _first_battle_id:
        return

    # Only submit once per player (each bot announces its own team)
    if player.username in _pasted_players:
        return
    _pasted_players.add(player.username)

    text = format_team(battle, player.username)

    # Save locally too
    try:
        LOG_DIR.mkdir(exist_ok=True)
        local_file = LOG_DIR / f"{battle.battle_tag.replace('/', '_')}_{player.username}.txt"
        with local_file.open("w") as f:
            f.write(text)
    except Exception:
        pass

    # Submit to pokepast.es and open in browser
    title = f"{player.username} - {battle.battle_tag}"
    url = _submit_pokepastes(text, title)
    if url:
        print(f"\n[{player.username}] paste: {url}", file=sys.stderr, flush=True)
        try:
            webbrowser.open_new_tab(url)
        except Exception as e:
            print(f"[announce] browser open failed: {e}", file=sys.stderr, flush=True)
    else:
        # Fallback: print team locally
        print(f"\n[{player.username}] (pokepast.es failed, showing local):", file=sys.stderr, flush=True)
        print(text, file=sys.stderr, flush=True)
