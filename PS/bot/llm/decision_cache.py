"""Tiny persistent decision cache for the M5 LLM agent.

The LLM is only consulted on strategic forks, and (after the strategy-only
override) its effective decision is one of a few ABSTRACT actions:
anchor / switch / setup / stall. The same *abstracted* fork recurs across
battles, so we memoize action-by-fork-signature: a recurring fork becomes a
dict lookup instead of an LLM call — fewer tokens, faster, same decision.

Stored as a flat JSON map {signature: action}. Stdlib only, no deps. This is
also the seed of the M6 archetype knowledge store.

Disable with PS_CACHE_OFF=1; relocate with PS_CACHE_PATH=/some/file.json.
"""

import atexit
import json
import os
import tempfile

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_cache.json")
_FLUSH_EVERY = 25  # write to disk every N new/changed entries (crash insurance)


class DecisionCache:
    def __init__(self, path=None, autosave=True):
        self.path = os.path.abspath(path or os.environ.get("PS_CACHE_PATH", _DEFAULT_PATH))
        self._data = self._load()
        self._dirty = 0

    def _load(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get(self, signature):
        """Return the cached abstract action for this signature, or None."""
        return self._data.get(signature)

    def put(self, signature, action):
        """Record the effective action taken for this signature."""
        if self._data.get(signature) != action:
            self._data[signature] = action
            self._dirty += 1
            if self._dirty >= _FLUSH_EVERY:
                self.save()

    def save(self):
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, sort_keys=True, indent=0)  # one entry/line, stable order
            os.replace(tmp, self.path)  # atomic
            self._dirty = 0
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def __len__(self):
        return len(self._data)


# A process-wide singleton so multiple LLMAgent instances share one cache and one
# atexit flush (benchmarks build several agents). Created lazily on first use.
_SHARED = None


def shared_cache() -> "DecisionCache":
    global _SHARED
    if _SHARED is None:
        _SHARED = DecisionCache()
        atexit.register(_SHARED.save)
    return _SHARED
