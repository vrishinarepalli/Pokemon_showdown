"""Debug helper: announce full team info in battle chat for spectators.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots will post their team
(species, level, item, ability, moves, tera) to battle chat on turn 1,
making it easy to see both teams when spectating live.
"""

import asyncio
import os


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def format_team(battle, username: str) -> str:
    """Format own team info as a readable multi-line string for battle chat."""
    lines = [f"=== {username} TEAM ==="]
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
            f"{species} L{level} @{item} | {ability}{tera_str} | {moves}"
        )
    return "\n".join(lines)


def announce_team(player, battle) -> None:
    """Post team info to battle chat (async-safe fire-and-forget).

    Called synchronously from choose_move; schedules message on event loop.
    """
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    text = format_team(battle, player.username)
    try:
        # Send each line separately (Showdown chat handles short messages better)
        for line in text.split("\n"):
            asyncio.ensure_future(
                player.ps_client.send_message(line, room=battle.battle_tag)
            )
    except Exception:
        pass  # Don't crash battle on announce failure
