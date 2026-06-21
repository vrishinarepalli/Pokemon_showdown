"""M5 LLM agent: a Groq-backed bot that *judges* among pre-analyzed candidates.

Division of labor (by design):
  - Background code (bot/llm/tools.py) computes every fact — damage %, KO odds,
    speed order, threats, switch matchups — and narrows the choice set.
  - The LLM only picks the best candidate for winning the GAME (not just the turn).
  - A fast-path skips the LLM entirely on forced/obvious turns.
  - Any LLM error/timeout falls back to a sound heuristic, so battles never crash.

Acceptance (M5): beat M4 (the ~52% ExpectimaxAgent).
"""

import os
import re

from poke_env.data import GenData
from poke_env.player import Player

from bot.agents.expectimax import (
    _RECOVERY_MOVES,
    _STATUS_MOVES,
    _norm,
    _we_go_first,
)
from bot.llm.client import GroqClient
from bot.llm.decision_cache import shared_cache
from bot.llm.tools import analyze_move, analyze_switch, battle_summary

# Take a KO without asking the LLM if it's this likely AND we move first.
_KO_FAST = 0.9

_SYSTEM = (
    "Expert gen9 randbattle player. Goal: win the GAME, not just the turn. All "
    "numbers (dmg%, KO chance, speed, threats) are correct—trust them. Secure KOs; "
    "switch out of losing matchups to a wall; set up/status vs passive foes; don't "
    "die if you can avoid it; preserve win conditions. Reply with ONE action number."
)

# Set PS_LLM_OFF=1 to run the harness on the heuristic fallback only (no API calls).
_LLM_OFF = os.environ.get("PS_LLM_OFF", "0") != "0"
# Set PS_CACHE_OFF=1 to bypass the decision cache (every fork re-queries the LLM).
_CACHE_OFF = os.environ.get("PS_CACHE_OFF", "0") != "0"


class LLMAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None if _LLM_OFF else GroqClient()
        self._cache = None if _CACHE_OFF else shared_cache()
        self._opp_tracker = None
        self.n_llm = 0          # fork turns the LLM decided
        self.n_cache = 0        # fork turns answered from the decision cache (no LLM)
        self.n_fastpath = 0     # forced / obvious-KO turns
        self.n_gate = 0         # non-fork turns played by the heuristic (no LLM)
        self.n_fallback = 0     # fork turns where the LLM errored -> heuristic

    # ---- main entry ----
    def choose_move(self, battle):
        type_chart = GenData.from_gen(battle.gen).type_chart
        self._update_tracker(battle)

        moves = [m for m in battle.available_moves if (m.current_pp or 0) != 0] or list(battle.available_moves)
        switches = list(battle.available_switches)

        # Fast-path: nothing to deliberate.
        if not moves and switches:
            return self.create_order(self._fallback_switch(battle, type_chart, switches))
        if not moves and not switches:
            return self.choose_random_move(battle)
        if len(moves) == 1 and not switches:
            self.n_fastpath += 1
            return self.create_order(moves[0])

        # Build pre-analyzed candidates.
        candidates = []
        for m in moves:
            candidates.append({"kind": "move", "order": m,
                               "info": analyze_move(m, battle, type_chart)})
        for p in switches:
            candidates.append({"kind": "switch", "order": p,
                               "info": analyze_switch(p, battle, type_chart, tracker=self._opp_tracker)})

        # Obvious-KO fast-path: if we can KO this turn and move first, just do it
        # (don't give the LLM a chance to fumble a free kill).
        ko = self._obvious_ko(candidates, battle)
        if ko is not None:
            self.n_fastpath += 1
            return self.create_order(ko)

        # Strategic-fork gate: only spend an LLM call where judgment can beat the
        # heuristic (escape danger, set up, pivot off a walled matchup, or stall).
        # On the ~80% of turns where "use the best move" is correct, play the
        # heuristic — no LLM call, downside bounded to the ~50% floor, tokens saved.
        summary = battle_summary(battle, type_chart, tracker=self._opp_tracker)
        feats = self._fork_features(candidates, summary)
        fork = self._fork_type(feats)
        if self._client is None or not fork:
            self.n_gate += 1
            return self.create_order(self._heuristic_choice(candidates, battle, type_chart))

        anchor = self._heuristic_index(candidates)

        # Decision cache: a recurring abstracted fork is a dict lookup, not an LLM
        # call. We cache the EFFECTIVE abstract action (anchor/switch/setup/stall)
        # and re-resolve it to a concrete candidate in the current battle. If the
        # cached action isn't available now, fall through and ask the LLM.
        sig = self._fork_signature(fork, feats, summary)
        if self._cache is not None:
            cached = self._cache.get(sig)
            if cached is not None:
                order = self._resolve_action(cached, candidates, anchor)
                if order is not None:
                    self.n_cache += 1
                    return self.create_order(order)

        idx = self._ask_llm(battle, type_chart, candidates, anchor, summary)
        if idx is None or not (0 <= idx < len(candidates)):
            self.n_fallback += 1
            return self.create_order(self._heuristic_choice(candidates, battle, type_chart))
        chosen = candidates[idx]
        # Strategy-only override: the heuristic owns ATTACK selection (already at the
        # ~50% floor). The LLM may only pull us toward a SWITCH or a setup/status/
        # recovery move — its strategic value-add. If it picks a different plain
        # attack, defer to the damage-maximizer so the LLM can't pick a worse hit.
        if (chosen["kind"] == "move" and idx != anchor
                and not (self._is_setup(chosen["order"]) or self._is_stall(chosen["order"]))):
            self.n_gate += 1
            action, order = "anchor", self._heuristic_choice(candidates, battle, type_chart)
        else:
            self.n_llm += 1
            action, order = self._abstract_action(chosen), chosen["order"]
        if self._cache is not None:
            self._cache.put(sig, action)  # remember the effective action for this fork
        return self.create_order(order)

    @staticmethod
    def _is_setup(move) -> bool:
        return bool(
            move.boosts
            and any(v > 0 for v in move.boosts.values())
            and (move.base_power or 0) == 0
        )

    @staticmethod
    def _is_stall(move) -> bool:
        mid = _norm(getattr(move, "id", ""))
        return mid in _RECOVERY_MOVES or (mid in _STATUS_MOVES and _STATUS_MOVES[mid] is not None)

    def _fork_features(self, candidates, summary) -> dict:
        """Decision-relevant features of the current spot, computed once and used
        by BOTH the fork gate and the cache signature (so they never disagree)."""
        moves = [c for c in candidates if c["kind"] == "move"]
        switches = [c for c in candidates if c["kind"] == "switch"]
        dmg = [c["info"]["expected_dmg_pct"] for c in moves if c["info"]["category"] != "status"]
        return {
            "our_best": max(dmg) if dmg else 0.0,
            "has_setup": any(self._is_setup(c["order"]) for c in moves),
            "has_stall": any(self._is_stall(c["order"]) for c in moves),
            "safe_switch": any(c["info"]["incoming_dmg_pct"] < 35 for c in switches),
            "opp_can_ko": summary["opp_can_ko_us"],
            "opp_hit": summary["opp_best_dmg_to_us_pct"],
        }

    @staticmethod
    def _fork_type(f) -> int:
        """0 = not a fork (use heuristic, no LLM); 1-4 = which strategic fork fired
        — the spots where the myopic expectimax is weak. Returns an id (not a bool)
        so the decision cache can key on the fork kind."""
        if f["opp_can_ko"] and f["safe_switch"]:                          # (1) flee danger to a wall
            return 1
        if f["has_setup"] and f["opp_hit"] < 25 and f["our_best"] < 70:   # (2) safe setup window
            return 2
        if f["our_best"] < 25 and (f["safe_switch"] or f["has_stall"]):   # (3) walled / stuck
            return 3
        if f["has_stall"] and f["opp_hit"] < 30 and f["our_best"] < 45:   # (4) stall window
            return 4
        return 0

    # ---- decision-cache helpers ----
    @staticmethod
    def _bucket(x, edges) -> int:
        for i, e in enumerate(edges):
            if x < e:
                return i
        return len(edges)

    def _fork_signature(self, fork, feats, summary) -> str:
        """Canonical, coarse key for an abstracted fork. Two situations with the
        same signature get the same cached action — coarse enough to recur often,
        specific enough to stay safe (carries every decision-relevant feature)."""
        ob = self._bucket(feats["our_best"], (25, 45, 70, 100))
        oh = self._bucket(feats["opp_hit"], (25, 30, 35, 60))
        our_hp = self._bucket(summary["our_active"]["hp_pct"], (33, 66))
        opp_hp = self._bucket(summary["opp_active"]["hp_pct"] or 0, (33, 66))
        ours, theirs = summary["our_remaining"], summary["opp_remaining"]
        team = (ours > theirs) - (ours < theirs)  # -1 behind / 0 even / +1 ahead
        return (f"f{fork}|ko{int(feats['opp_can_ko'])}|fst{int(summary['we_move_first'])}"
                f"|ob{ob}|oh{oh}|sw{int(feats['safe_switch'])}|set{int(feats['has_setup'])}"
                f"|stl{int(feats['has_stall'])}|hp{our_hp}{opp_hp}|t{team}")

    def _abstract_action(self, candidate) -> str:
        """Classify a chosen candidate into the LLM's value-add buckets."""
        if candidate["kind"] == "switch":
            return "switch"
        if self._is_setup(candidate["order"]):
            return "setup"
        if self._is_stall(candidate["order"]):
            return "stall"
        return "anchor"

    def _resolve_action(self, action, candidates, anchor):
        """Map a cached abstract action back to a concrete candidate in THIS battle.
        Returns None if that action isn't available now (caller falls back to LLM)."""
        if action == "anchor":
            return candidates[anchor]["order"] if anchor is not None else None
        moves = [c for c in candidates if c["kind"] == "move"]
        if action == "switch":
            switches = [c for c in candidates if c["kind"] == "switch"]
            return min(switches, key=lambda c: c["info"]["incoming_dmg_pct"])["order"] if switches else None
        if action == "setup":
            cs = [c for c in moves if self._is_setup(c["order"])]
            return cs[0]["order"] if cs else None
        if action == "stall":
            cs = [c for c in moves if self._is_stall(c["order"])]
            return cs[0]["order"] if cs else None
        return None

    def _obvious_ko(self, candidates, battle):
        """A move we move first with that almost certainly KOs — no judgment needed."""
        atk, opp = battle.active_pokemon, battle.opponent_active_pokemon
        if not atk or not opp:
            return None
        best, best_dmg = None, -1.0
        for c in candidates:
            if c["kind"] != "move":
                continue
            info = c["info"]
            if info["ko_chance"] >= _KO_FAST and _we_go_first(c["order"], atk, opp, battle):
                if info["expected_dmg_pct"] > best_dmg:
                    best, best_dmg = c["order"], info["expected_dmg_pct"]
        return best

    def _heuristic_index(self, candidates):
        """Index of the damage-maximizer's pick (anchor for the LLM)."""
        best_i, best_key = None, None
        for i, c in enumerate(candidates):
            if c["kind"] != "move":
                continue
            info = c["info"]
            key = (info["ko_chance"], info["expected_dmg_pct"])
            if best_key is None or key > best_key:
                best_i, best_key = i, key
        return best_i

    # ---- LLM path ----
    def _ask_llm(self, battle, type_chart, candidates, anchor=None, summary=None):
        s = summary if summary is not None else battle_summary(battle, type_chart, tracker=self._opp_tracker)
        ours, opp = s["our_active"], s["opp_active"]
        order = "we-first" if s["we_move_first"] else "opp-first"
        danger = " OPP-CAN-KO-US" if s["opp_can_ko_us"] else ""
        state = (
            f"T{s['turn']} {ours['species']} {ours['hp_pct']}%"
            f"{('/'+ours['status']) if ours['status'] else ''} vs "
            f"{opp['species']} {opp['hp_pct']}%{('/'+opp['status']) if opp['status'] else ''}; "
            f"{order}; opp-best-hit {s['opp_best_dmg_to_us_pct']}%{danger}; "
            f"team {s['our_remaining']}v{s['opp_remaining']}"
        )
        lines = []
        for i, c in enumerate(candidates):
            info = c["info"]
            if c["kind"] == "move":
                lines.append(
                    f"{i} {info['name']} {info['category'][:4]} {info['expected_dmg_pct']}% "
                    f"KO{info['ko_chance']} pr{info['priority']}"
                )
            else:
                lines.append(
                    f"{i} >{info['species']} take{info['incoming_dmg_pct']}% hit{info['threatens_back_pct']}%"
                )
        anchor_line = ""
        if anchor is not None and 0 <= anchor < len(candidates):
            anchor_line = f"\nmax-dmg pick=#{anchor}; pick it unless a switch/setup clearly wins more."
        user = state + "\n" + "\n".join(lines) + anchor_line + "\nBest action number:"
        try:
            reply = self._client.ask(_SYSTEM, user, max_tokens=16, temperature=0.2)
        except Exception as e:  # network/timeout/rate-limit → heuristic fallback
            print(f"[llm-fallback] {type(e).__name__}: {e}")
            return None
        match = re.search(r"\d+", reply or "")
        return int(match.group()) if match else None

    # ---- heuristic fallback (no LLM) ----
    def _heuristic_choice(self, candidates, battle, type_chart):
        moves = [c for c in candidates if c["kind"] == "move"]
        if moves:
            best = max(moves, key=lambda c: (c["info"]["ko_chance"], c["info"]["expected_dmg_pct"]))
            return best["order"]
        return candidates[0]["order"]

    def _fallback_switch(self, battle, type_chart, switches):
        # Pick the switch that takes the least and threatens the most.
        def score(p):
            info = analyze_switch(p, battle, type_chart, tracker=self._opp_tracker)
            return info["threatens_back_pct"] - info["incoming_dmg_pct"]
        return max(switches, key=score)

    # ---- opponent tracking (feeds set-prediction tool) ----
    def _update_tracker(self, battle):
        if self._opp_tracker is None:
            from bot.data.opp_tracker import OppTeamTracker
            self._opp_tracker = OppTeamTracker()
        for opp_mon in (battle.opponent_team or {}).values():
            if opp_mon is None:
                continue
            self._opp_tracker.observe_pokemon(opp_mon.species)
            for move in opp_mon.moves.values():
                self._opp_tracker.observe_move(opp_mon.species, move.id)
            ability = getattr(opp_mon, "ability", None)
            if ability:
                self._opp_tracker.observe_ability(opp_mon.species, ability)
