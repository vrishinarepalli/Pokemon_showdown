"""Debug helper: announce full team info in battle chat.

Enable via env var BOT_ANNOUNCE_TEAM=1. Both bots post their team info
to battle chat on turn 1.
"""

import asyncio
import os
import sys


_pending_tasks = []


def should_announce() -> bool:
    return os.environ.get("BOT_ANNOUNCE_TEAM") == "1"


def format_team(battle, username: str) -> str:
    """Format own team info. Uses ';' separators (Showdown protocol uses '|')."""
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
            f"{species} L{level} @{item} ; {ability}{tera_str} ; {moves}"
        )
    return lines  # Return list of lines, not joined string


def _task_error_callback(task):
    """Print task errors so we can see what failed."""
    try:
        exc = task.exception()
        if exc:
            print(f"[announce] task failed: {exc}", file=sys.stderr, flush=True)
        else:
            print(f"[announce] task sent OK", file=sys.stderr, flush=True)
    except Exception:
        pass


def _schedule_send(player, room, message):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        task = loop.create_task(player.ps_client.send_message(message, room=room))
        task.add_done_callback(_task_error_callback)
        _pending_tasks.append(task)
        _pending_tasks[:] = [t for t in _pending_tasks if not t.done()]
    except Exception as e:
        print(f"[announce] schedule failed: {e}", file=sys.stderr, flush=True)


def announce_team(player, battle) -> None:
    """Post team info to battle chat."""
    if not should_announce():
        return
    if getattr(battle, "_team_announced", False):
        return
    battle._team_announced = True

    lines = format_team(battle, player.username)
    print(f"[announce] {player.username} posting {len(lines)} lines to {battle.battle_tag}",
          file=sys.stderr, flush=True)

    for line in lines:
        _schedule_send(player, battle.battle_tag, line)
