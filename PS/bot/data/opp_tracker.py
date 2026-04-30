"""Opponent team tracker: 6 slots holding remaining possible sets per species.

As the battle progresses, we observe moves, abilities, and item-revealing
behaviors (e.g., Choice lock detected via repeated same-move usage). Each
observation prunes the set of possible builds that match.

Used by threat calculations to predict opp moves more accurately than the
full unfiltered movepool.
"""

import json
from typing import Dict, List, Optional, Set

_SETS_PATH = "/home/user/Pokemon_showdown/node_modules/pokemon-showdown/data/random-battles/gen9/sets.json"

_sets_cache: Optional[dict] = None


def _norm(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("-", "").replace("'", "")


def _load_sets_db() -> dict:
    global _sets_cache
    if _sets_cache is None:
        try:
            with open(_SETS_PATH) as f:
                _sets_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _sets_cache = {}
    return _sets_cache


def _lookup_sets(species: str) -> List[dict]:
    """Find all sets for a species using the same lookup rules as sets_db."""
    if not species:
        return []
    norm = _norm(species)
    db = _load_sets_db()

    entry = db.get(norm)
    if entry is None:
        # Stripping suffixes only — never match shorter input to longer key.
        # Pick longest matching prefix.
        best_key = None
        for key in db:
            if norm.startswith(key):
                if best_key is None or len(key) > len(best_key):
                    best_key = key
        if best_key is not None:
            entry = db[best_key]

    if entry is None or "sets" not in entry:
        return []
    return list(entry["sets"])


class OppTeamTracker:
    """Per-battle opponent team tracker.

    Each species slot holds:
      - sets: list of remaining possible sets (pruned as info is revealed)
      - observed_moves: set of move ids we've seen them use
      - observed_ability: ability name (if revealed)
      - choice_lock: 'choiceband' / 'choicespecs' / 'choicescarf' / None
    """

    def __init__(self):
        self._slots: Dict[str, dict] = {}

    def observe_pokemon(self, species: str) -> None:
        """Initialize a slot for this species if not already present."""
        key = _norm(species)
        if not key or key in self._slots:
            return
        self._slots[key] = {
            "species": species,
            "sets": _lookup_sets(species),
            "observed_moves": set(),
            "observed_ability": None,
            "choice_lock": None,
        }

    def observe_move(self, species: str, move_id: str) -> None:
        """Filter sets to those whose movepool includes move_id."""
        self.observe_pokemon(species)
        key = _norm(species)
        slot = self._slots.get(key)
        if slot is None:
            return
        mid = _norm(move_id)
        if not mid:
            return
        slot["observed_moves"].add(mid)
        slot["sets"] = [
            s for s in slot["sets"]
            if mid in {_norm(m) for m in s.get("movepool", [])}
        ]

    def observe_ability(self, species: str, ability: str) -> None:
        """Filter sets to those listing this ability."""
        self.observe_pokemon(species)
        key = _norm(species)
        slot = self._slots.get(key)
        if slot is None:
            return
        norm_ability = _norm(ability)
        slot["observed_ability"] = norm_ability
        slot["sets"] = [
            s for s in slot["sets"]
            if norm_ability in {_norm(a) for a in s.get("abilities", [])}
        ]

    def observe_choice_lock(self, species: str, lock_kind: str) -> None:
        """Mark a Choice item lock (band/specs/scarf).

        lock_kind: 'choiceband', 'choicespecs', or 'choicescarf'.
        Doesn't filter sets directly (sets.json doesn't carry item field per set
        in randbats), but downstream code can apply 1.5x atk/spa multiplier.
        """
        self.observe_pokemon(species)
        key = _norm(species)
        slot = self._slots.get(key)
        if slot is not None:
            slot["choice_lock"] = lock_kind

    def get_likely_moves(self, species: str) -> Set[str]:
        """Union of moves across remaining sets, plus observed moves.

        Returns empty set if species not tracked or all sets pruned.
        """
        key = _norm(species)
        slot = self._slots.get(key)
        if slot is None:
            return set()
        moves = set(slot["observed_moves"])
        for s in slot["sets"]:
            for m in s.get("movepool", []):
                moves.add(_norm(m))
        return moves

    def get_likely_abilities(self, species: str) -> Set[str]:
        key = _norm(species)
        slot = self._slots.get(key)
        if slot is None:
            return set()
        if slot["observed_ability"]:
            return {slot["observed_ability"]}
        abilities = set()
        for s in slot["sets"]:
            for a in s.get("abilities", []):
                abilities.add(_norm(a))
        return abilities

    def get_choice_lock(self, species: str) -> Optional[str]:
        key = _norm(species)
        slot = self._slots.get(key)
        return slot["choice_lock"] if slot else None

    def get_remaining_sets_count(self, species: str) -> int:
        """How many possible sets remain after pruning. Useful for confidence."""
        key = _norm(species)
        slot = self._slots.get(key)
        return len(slot["sets"]) if slot else 0

    def n_slots(self) -> int:
        return len(self._slots)
