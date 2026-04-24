"""Debug helper: dump full team info to terminal and file for spectators.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots will:
1. Print their full team info to terminal (stdout, pretty formatted)
2. Write to per-battle log file ./battle_teams/{battle_id}.txt

Chat messages are blocked for unregistered bot accounts, so we use terminal
and files instead. Use `tail -f battle_teams/*.txt` or cat the file while
spectating the replay.
"""

import os
import sys
from pathlib import Path


LOG_DIR = Path("./battle_teams")


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def format_team(battle, username: str) -> str:
    """Format own team info as a readable multi-line string."""
    lines = [f"{'='*70}", f"=== {username} TEAM (battle={battle.battle_tag}) ===", f"{'='*70}"]
    team = battle.team or {}
    for ident, mon in team.items():
        species = getattr(mon, "species", "?")
        level = getattr(mon, "level", "?")
        item = getattr(mon, "item", None) or "none"
        ability = getattr(mon, "ability", None) or "?"
        moves = ", ".join(m.id for m in (mon.moves or {}).values()) or "?"
        tera = getattr(mon, "tera_type", None)
        tera_str = f" | tera={getattr(tera, 'name', tera)}" if tera else ""
        hp = getattr(mon, "current_hp_fraction", 1.0)
        active_marker = " [ACTIVE]" if getattr(mon, "active", False) else ""
        lines.append(
            f"  {species} L{level}{active_marker}\n"
            f"    item: {item}\n"
            f"    ability: {ability}{tera_str}\n"
            f"    moves: {moves}\n"
            f"    hp: {hp*100:.0f}%"
        )
    return "\n".join(lines)


def announce_team(player, battle) -> None:
    """Print team info to terminal and write to file."""
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    text = format_team(battle, player.username)

    # Print to terminal (visible while watching battles)
    print(text, file=sys.stdout, flush=True)

    # Also write to a file for later review
    try:
        LOG_DIR.mkdir(exist_ok=True)
        battle_file = LOG_DIR / f"{battle.battle_tag.replace('/', '_')}.txt"
        with battle_file.open("a") as f:
            f.write(text + "\n\n")
    except Exception as e:
        print(f"[announce] file write failed: {e}", file=sys.stderr, flush=True)
