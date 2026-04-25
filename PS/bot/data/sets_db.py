"""Gen 9 random battle sets database.

Loads Pokemon Showdown's published random battle sets and exposes:
- get_movepool(species): all possible moves a species can have in randbats
- get_levels(species): random battle level for the species

Used to predict opponent moves and switching behavior even when their
moveset isn't fully revealed yet.
"""

import json
import os
from typing import Set, List, Optional

_SETS_PATH = "/home/user/Pokemon_showdown/node_modules/pokemon-showdown/data/random-battles/gen9/sets.json"

_sets_cache: Optional[dict] = None
_movepool_cache: dict = {}


def _load() -> dict:
    global _sets_cache
    if _sets_cache is None:
        try:
            with open(_SETS_PATH) as f:
                _sets_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _sets_cache = {}
    return _sets_cache


def _normalize_species(species: str) -> str:
    """Normalize species name to sets.json key format.

    sets.json uses lowercase, no spaces, no hyphens, no special chars.
    "Sinistcha-Masterpiece" → "sinistchamasterpiece"
    "Tauros-Paldea-Combat" → "tauropaldeacombat"  (some forms are merged)
    """
    if not species:
        return ""
    return species.lower().replace("-", "").replace(" ", "").replace("'", "")


def get_movepool(species: str) -> Set[str]:
    """Return union of all possible moves for this species in gen9 randbats.

    Returns empty set if species not found. Moves are in showdown id format
    (lowercase, no spaces): 'thunderbolt', 'matchagotcha', etc.
    """
    if not species:
        return set()

    cached = _movepool_cache.get(species)
    if cached is not None:
        return cached

    norm = _normalize_species(species)
    sets = _load()

    # Try direct match
    entry = sets.get(norm)
    if entry is None:
        # Try without form suffix (sinistchamasterpiece → sinistcha)
        for key in sets:
            if norm.startswith(key) or key.startswith(norm):
                entry = sets[key]
                break

    if entry is None or "sets" not in entry:
        _movepool_cache[species] = set()
        return set()

    moves = set()
    for s in entry["sets"]:
        for m in s.get("movepool", []):
            # Normalize: "Thunder Bolt" → "thunderbolt"
            moves.add(m.lower().replace(" ", "").replace("-", "").replace("'", ""))

    _movepool_cache[species] = moves
    return moves


def get_roles(species: str) -> List[str]:
    """Return possible role names for this species (e.g. 'Wallbreaker', 'Setup Sweeper')."""
    if not species:
        return []

    norm = _normalize_species(species)
    sets = _load()
    entry = sets.get(norm)
    if entry is None:
        return []

    return [s.get("role", "") for s in entry.get("sets", [])]
