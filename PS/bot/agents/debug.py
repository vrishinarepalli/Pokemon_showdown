"""Debug helper: announce full team info for spectators.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots will:
1. Print team info to stderr (always visible in terminal)
2. Attempt to post to battle chat on turn 1

Prints to stderr so you see the teams immediately, plus tries chat
so spectators in browser can see it too.
"""

import asyncio
import os
import sys


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def format_team(battle, username: str) -> str:
    """Format own team info as a readable multi-line string."""
    lines = [f"=== {username} TEAM (battle={battle.battle_tag}) ==="]
    team = battle.team or {}
    for ident, mon in team.items():
        species = getattr(mon, "species", "?")
        level = getattr(mon, "level", "?")
        item = getattr(mon, "item", None) or "none"
        ability = getattr(mon, "ability", None) or "?"
        moves = ",".join(m.id for m in (mon.moves or {}).values()) or "?"
        tera = getattr(mon, "tera_type", None)
        tera_str = f" tera={getattr(tera, 'name', tera)}" if tera else ""
        lines.append(
            f"  {species} L{level} @{item} | {ability}{tera_str} | {moves}"
        )
    return "\n".join(lines)


def announce_team(player, battle) -> None:
    """Post team info to stderr and battle chat (fire-and-forget)."""
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    text = format_team(battle, player.username)

    # Always print to stderr (reliable)
    print(text, file=sys.stderr, flush=True)

    # Try to send to battle chat (best-effort)
    try:
        loop = asyncio.get_event_loop()
        for line in text.split("\n"):
            loop.create_task(
                player.ps_client.send_message(line, room=battle.battle_tag)
            )
    except Exception as e:
        print(f"[announce] chat send failed: {e}", file=sys.stderr, flush=True)
