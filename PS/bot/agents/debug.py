"""Debug helper: announce full team info in battle chat.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots post their team info
to battle chat on turn 1. Spectators must click "Join chat" at bottom of
the battle window to see the messages.
"""

import asyncio
import os
import sys


_pending_tasks = []  # Hold task refs to prevent garbage collection


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def format_team(battle, username: str) -> str:
    """Format own team info as a readable multi-line string."""
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
            f"  {species} L{level} @{item} | {ability}{tera_str} | {moves}"
        )
    return "\n".join(lines)


def _schedule(coro):
    """Schedule a coroutine and hold a reference to prevent GC."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    task = loop.create_task(coro)
    _pending_tasks.append(task)
    # Cleanup completed tasks to avoid leak
    _pending_tasks[:] = [t for t in _pending_tasks if not t.done()]
    return task


def announce_team(player, battle) -> None:
    """Post team info to battle chat."""
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    text = format_team(battle, player.username)

    # Print to terminal so we can confirm it ran
    print(f"[announce] sending team to {battle.battle_tag}", file=sys.stderr, flush=True)

    # Send each line separately to the battle chat room
    for line in text.split("\n"):
        try:
            _schedule(player.ps_client.send_message(line, room=battle.battle_tag))
        except Exception as e:
            print(f"[announce] send failed: {e}", file=sys.stderr, flush=True)
