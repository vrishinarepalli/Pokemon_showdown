#!/usr/bin/env python3
"""Build the BC value-function dataset from scraped replays.

For each replay we replay its log through a poke-env Battle (the same parser the
live bot uses -> train/serve parity) from BOTH players' POV, snapshot
extract_features() at the start of every turn, and label it with whether THAT
POV's player won. Two POVs per game = swapped features + flipped label = free
symmetry and 2x samples; both POVs share a `group` id so a train/val split by
group never leaks one game across the split.

Output: a .npz with X (float32 [N, F]), y (int8 win label), group (int32 replay
index), and feature_names. Stop here — training is the next, separate step.

Usage (from PS/, venv python for poke-env):
    .venv/bin/python build_value_dataset.py                 # all replays
    .venv/bin/python build_value_dataset.py --limit 200     # quick subset
    .venv/bin/python build_value_dataset.py --demo          # tiny self-check
"""

import argparse
import json
import logging
import os

import numpy as np
from poke_env.battle.battle import Battle

from bot.value.features import FEATURE_NAMES, N_FEATURES, extract_features

logging.disable(logging.CRITICAL)  # poke-env logs noisy warnings on replay quirks

DEFAULT_REPLAYS = os.path.join(os.path.dirname(__file__), "data", "replays", "gen9randombattle.jsonl")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "data", "value_dataset.npz")
_GEN = 9


def _winner(log):
    """The winning username, or None for a tie / unfinished replay."""
    for ln in log.split("\n"):
        if ln.startswith("|win|"):
            return ln[5:].strip()
    return None


def _states_from_pov(log, username):
    """Replay the log as `username`, yielding a feature vector at each turn start.
    Best-effort: a parse error on an exotic message is skipped, not fatal."""
    battle = Battle("replay", username, logging.getLogger("ds"), _GEN)
    for line in log.split("\n"):
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        try:
            battle.parse_message(parts)
        except Exception:
            continue
        if len(parts) > 1 and parts[1] == "turn":
            yield extract_features(battle)


def build(replays_path, out_path, limit=None):
    X, y, group = [], [], []
    n_replays = skipped = 0
    with open(replays_path) as f:
        for gi, line in enumerate(f):
            if limit is not None and n_replays >= limit:
                break
            rec = json.loads(line)
            players, log = rec["players"], rec["log"]
            win = _winner(log)
            if win is None or win not in players or len(players) != 2:
                skipped += 1
                continue
            n_replays += 1
            for username in players:                       # both POVs
                label = 1 if username == win else 0
                for feats in _states_from_pov(log, username):
                    X.append(feats)
                    y.append(label)
                    group.append(gi)
            if n_replays % 250 == 0:
                print(f"  {n_replays} replays -> {len(X)} states", flush=True)

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.int8)
    group = np.asarray(group, dtype=np.int32)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.savez_compressed(out_path, X=X, y=y, group=group, feature_names=np.array(FEATURE_NAMES))
    print(f"Done: {len(X)} states from {n_replays} replays ({skipped} skipped), "
          f"{X.shape[1]} features, win rate {y.mean():.3f}")
    print(f"Saved {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)")
    return X, y, group


def _demo():
    """Self-check on a few real replays: feature width, label balance, grouping."""
    X, y, group = build(DEFAULT_REPLAYS, "/tmp/_value_demo.npz", limit=10)
    assert X.shape[1] == N_FEATURES == len(FEATURE_NAMES), X.shape
    assert X.ndim == 2 and len(y) == len(X) == len(group)
    assert set(np.unique(y)).issubset({0, 1})
    # both POVs of each game -> labels within a group must be balanced (one won, one lost)
    for g in np.unique(group):
        labs = y[group == g]
        assert 0 in labs and 1 in labs, f"group {g} not balanced across POVs"
    assert not np.isnan(X).any(), "NaN in features"
    print("demo OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replays", default=DEFAULT_REPLAYS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=None, help="only process the first N replays")
    ap.add_argument("--demo", action="store_true", help="tiny self-check and exit")
    args = ap.parse_args()
    if args.demo:
        _demo()
        return
    build(args.replays, args.out, args.limit)


if __name__ == "__main__":
    main()
