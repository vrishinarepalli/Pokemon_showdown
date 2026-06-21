#!/usr/bin/env python3
"""Scrape gen9randombattle replays from the public Showdown replay archive.

This is the DATA step for the M5->BC pivot: a learned value function trained
by behavioral cloning on real human play needs real human replays. We pull raw
replays to a local JSONL and stop there — parsing logs into (state, action)
training pairs is a separate downstream step (don't conflate scrape with parse).

API (verified 2026-06-21):
  search.json?format=gen9randombattle[&before=<uploadtime>]  -> 51 newest, paged backward
  <id>.json                                                  -> full replay {log, inputlog, rating, ...}

Stdlib only (urllib/json) — no deps. Polite (rate-limited) and resumable:
re-running skips replays already in the output file, so you accumulate over days.

Usage (from PS/):
    python scrape_replays.py --max 500
    python scrape_replays.py --max 2000 --min-rating 1500   # skilled play only
    python scrape_replays.py --demo                          # offline self-check
"""

import argparse
import gzip
import json
import os
import time
import urllib.error
import urllib.request

FORMAT = "gen9randombattle"
SEARCH_URL = "https://replay.pokemonshowdown.com/search.json"
REPLAY_URL = "https://replay.pokemonshowdown.com/{id}.json"
# gzipped by default — text compresses ~5x, so a big dataset stays tens of MB.
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "data", "replays", f"{FORMAT}.jsonl.gz")
_KEEP = ("id", "format", "players", "rating", "uploadtime", "log", "inputlog")


def _open(path, mode):
    """Open plain or gzipped by extension, always text (utf-8)."""
    return gzip.open(path, mode + "t", encoding="utf-8") if path.endswith(".gz") else open(path, mode)


def _fetch(url, retries=3, delay=0.4):
    """GET + parse JSON, with a couple of retries on transient network errors."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ps-bot-research/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 2))  # ponytail: linear backoff, exponential if it matters


def _load_seen(path):
    """Resume support: ids already saved, so a re-run only fetches new replays."""
    seen = set()
    if os.path.exists(path):
        with _open(path, "r") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue  # skip a torn last line from an interrupted run
    return seen


def _select(results, min_rating, seen):
    """Filter a search page to the replays worth fetching: new + rated >= floor.
    rating can be None (unrated) -> treated as 0, dropped when a floor is set."""
    out = []
    for r in results:
        if r["id"] in seen:
            continue
        if (r.get("rating") or 0) < min_rating:
            continue
        out.append(r)
    return out


def scrape(out_path, max_replays, min_rating, delay):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    seen = _load_seen(out_path)
    print(f"{len(seen)} replays already saved at {out_path}")

    saved = 0
    before = None  # pagination cursor: uploadtime of the oldest result so far
    with _open(out_path, "a") as out:
        while saved < max_replays:
            url = f"{SEARCH_URL}?format={FORMAT}"
            if before is not None:
                url += f"&before={before}"
            page = _fetch(url)
            if not page:
                print("No more results from the archive — stopping.")
                break
            before = page[-1]["uploadtime"]  # next page is strictly older

            for meta in _select(page, min_rating, seen):
                if saved >= max_replays:
                    break
                try:
                    full = _fetch(REPLAY_URL.format(id=meta["id"]))
                except urllib.error.URLError as e:
                    print(f"  [skip] {meta['id']}: {e}")
                    continue
                rec = {k: full.get(k) for k in _KEEP}
                rec["rating"] = meta.get("rating")  # search metadata is authoritative; replay json rating is often null
                out.write(json.dumps(rec) + "\n")
                out.flush()
                seen.add(meta["id"])
                saved += 1
                if saved % 25 == 0:
                    print(f"  saved {saved}/{max_replays} (rating {meta.get('rating')})")
                time.sleep(delay)  # ponytail: be a good citizen on a community server

    print(f"Done: +{saved} replays this run, {len(seen)} total at {out_path}")


def _demo():
    """Offline self-check of the pure logic (no network): dedup + rating filter."""
    page = [
        {"id": "a", "rating": 1800},
        {"id": "b", "rating": None},   # unrated
        {"id": "c", "rating": 1200},
        {"id": "d", "rating": 2000},
    ]
    # no floor, nothing seen -> all new pass
    assert [r["id"] for r in _select(page, 0, set())] == ["a", "b", "c", "d"]
    # floor 1500 drops unrated + low
    assert [r["id"] for r in _select(page, 1500, set())] == ["a", "d"]
    # already-seen is skipped
    assert [r["id"] for r in _select(page, 0, {"a", "c"})] == ["b", "d"]
    print("demo OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max", type=int, default=500, help="replays to fetch this run (default 500)")
    ap.add_argument("--min-rating", type=int, default=0, help="skip replays below this rating (0 = keep all)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output JSONL (appended to; resumable)")
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between replay fetches")
    ap.add_argument("--demo", action="store_true", help="run offline self-check and exit")
    args = ap.parse_args()
    if args.demo:
        _demo()
        return
    scrape(args.out, args.max, args.min_rating, args.delay)


if __name__ == "__main__":
    main()
