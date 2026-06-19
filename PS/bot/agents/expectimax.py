"""Expectimax planner for M4.

Depth-1 expectimax: for each of our legal actions (moves, switches, setup/recovery),
simulate one turn of damage exchange under a deterministic opponent model
(opponent plays max-damage), then score the resulting state with the
hand-crafted value function.

Opponent model: mirrors M3's behavior (max damage, no setup, no Tera, rare switches).
Setup and recovery moves use 2-turn rollouts to capture multi-turn strategies M3 cannot execute.

Acceptance: >=60% winrate vs HeuristicAgent over 500 games.
"""

import os

from poke_env.data import GenData
from poke_env.player import Player

from bot.agents.debug import announce_team
from bot.agents.battle_logger import BattleLogger
from bot.value.handcrafted import HandcraftedValue


_NORM = 350.0  # move power score → HP fraction; 350 ≈ realistic damage range

# Tunable knobs (defaults reproduce prior behavior; overridable for A/B sweeps).
# PS_SPE_CONST: IV+EV term in the actual-speed estimate. 94 = 31 IV + 252 EV
#   (old assumption); 52 = 31 IV + 85 EV (gen9 randbat default, matches _estimate_stat).
# PS_POOL_DISC: multiplier on damage from UNREVEALED movepool moves when estimating
#   opponent threat. 1.0 = treat as certain (paranoid); <1 = discount the guess.
_SPE_IV_EV = float(os.environ.get("PS_SPE_CONST", "94"))   # tuned: 94 (max-EV floor) beat 52
_POOL_DISC = float(os.environ.get("PS_POOL_DISC", "0.7"))  # tuned: discount unrevealed-move threat
# Move-eval bonus/penalty knobs (tuned via 1000–3000-game A/B sweeps vs M3).
_RISK_PEN = float(os.environ.get("PS_RISK_PEN", "0.0"))   # early-game caution hurt vs M3; disabled
_KO_BONUS = float(os.environ.get("PS_KO_BONUS", "0.45"))  # guaranteed-KO reward
_NEARKO_BONUS = float(os.environ.get("PS_NEARKO", "0.30"))  # near-KO (roll) reward (lowering hurt)
_SETUP_BONUS = float(os.environ.get("PS_SETUP_BONUS", "0.0"))  # extra reward for setup (sweep bet vs M3)
_FSWITCH_OFF = float(os.environ.get("PS_FSWITCH_OFF", "1.0"))  # weight of offense in forced-switch choice
# 2-ply lookahead: discount applied to the projected NEXT-turn value of attacking
# moves (KO timing — does our KO hand M3 a revenge-killer? does staying in win the
# follow-up?). M3 is near-deterministic, so depth-2 has branching factor ~1 and is
# cheap. A/B vs M3: small discount (0.3) is neutral-to-slightly-positive; >=0.5
# regresses sharply (a ROUGH evaluator can't carry more lookahead weight). The
# payoff scales with damage-model accuracy — pair with an accurate calculator to
# unlock it. 0.0 = pure depth-1.
_LOOKAHEAD = float(os.environ.get("PS_LOOKAHEAD", "0.3"))

# --- Accurate damage model knobs (defaults = new accurate behavior) ---
# PS_ROLL: "avg" uses the average damage roll (×0.925) so projected HP is honest
#   and KO bonuses scale with the TRUE roll-to-KO probability; "max" reproduces the
#   old behavior (compute the 100% roll, then treat any max-roll KO as guaranteed —
#   which over-committed the bot to "KOs" that only land on high rolls).
_ROLL_MODE = os.environ.get("PS_ROLL", "avg")
_AVG_ROLL = 0.925  # mean of the 16 uniform damage rolls (0.85, 0.86, ... 1.00)
# PS_MULTIHIT=1 (default) scales multi-hit moves (Bullet Seed, Icicle Spear,
#   Population Bomb, ...) by poke-env's expected_hits; 0 = single-hit (old behavior).
_MULTIHIT = os.environ.get("PS_MULTIHIT", "1") != "0"
# PS_CONTEXT=1 (default) applies weather/terrain/screen damage modifiers inside the
#   damage formula; 0 ignores them (old behavior).
_CONTEXT = os.environ.get("PS_CONTEXT", "1") != "0"

# --- Wall-mode exploit knobs (vs a no-switch, status-less M3) ---
# When we comfortably tank the opponent's best move AND can't just KO it quickly,
# M3 keeps spamming a move that barely dents us and has no way to cure status,
# recover, or escape. Reward the long-game tools M3 can't answer (status /
# recovery / setup) so we convert unbreakable matchups into wins instead of slow
# even trades. PS_WALL=0 disables (reproduces prior behavior).
_WALL = os.environ.get("PS_WALL", "0") != "0"  # neutral vs M3 (52.6 vs 52.7); off by default, kept for online/human play
_WALL_THRESH = float(os.environ.get("PS_WALL_THRESH", "0.18"))   # opp best dmg ≤ this ⇒ walling
_WALL_BONUS = float(os.environ.get("PS_WALL_BONUS", "0.25"))     # score bonus for stall tools
_WALL_OUR_MAX = float(os.environ.get("PS_WALL_OUR_MAX", "0.6"))  # skip if our best dmg ≥ this (KO fast instead)
_WALL_MIN_HP = float(os.environ.get("PS_WALL_MIN_HP", "0.45"))   # only stall when we're healthy enough

# Stealth Rock damage = 1/8 * rock-type effectiveness against switch-in.
_SR_BASE = 0.125
# Spikes damage by layer count (grounded targets only).
_SPIKES_DAMAGE = {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}

# Setup move categories and their stat boosts (poke-env move.boosts dict).
# Used to evaluate setup moves via multi-turn rollout.
_RECOVERY_MOVES = {
    "recover", "roost", "slackoff", "milkdrink", "softboiled",
    "morningsun", "synthesis", "moonlight", "shoreup", "wish"
}
_MIN_PP_PENALTY = 3  # Penalize moves with less than this much PP remaining

_HAZARD_MOVES = {"stealthrock", "spikes", "toxicspikes", "stickyweb"}

_STATUS_MOVES = {
    "willowisp": "burn",
    "toxic": "badpoison",
    "toxicthread": "poison",
    "thunderwave": "paralyze",
    "sleeppowder": "sleep",
    "spore": "sleep",
    "lovelykiss": "sleep",
    "hypnosis": "sleep",
    "glare": "paralyze",
    "bodyslam": None,  # 30% paralysis chance secondary - don't eval as status
    "stunspore": "paralyze",
    "poisonpowder": "poison",
    "poisongas": "poison",
    "willowish": "burn",
}


class _EvalResult:
    """Detailed result of move/switch evaluation for logging."""
    def __init__(self, score: float, damage_dealt: float = 0.0, damage_taken: float = 0.0,
                 expected_hp_after: float = 1.0, is_setup: bool = False, is_hazard: bool = False,
                 move_category: str = "", reasoning: str = ""):
        self.score = score
        self.damage_dealt = damage_dealt
        self.damage_taken = damage_taken
        self.expected_hp_after = expected_hp_after
        self.is_setup = is_setup
        self.is_hazard = is_hazard
        self.move_category = move_category
        self.reasoning = reasoning


def _mon_value(pokemon) -> float:
    """Calculate mon's strategic value: hp * (speed / 200).

    Used to identify which mon to sacrifice vs which to preserve.
    Low value = good sacrifice candidate (low HP or slow).
    High value = preserve, save for later.
    """
    if not pokemon:
        return 0.0
    hp = pokemon.current_hp_fraction if pokemon else 1.0
    base_speed = (pokemon.base_stats or {}).get("spe", 100)
    return hp * (base_speed / 200.0)


# Type immunity abilities: defender takes 0 damage from this move type
# (no healing, just immune — may have other effects like stat boosts)
_ABILITY_TYPE_IMMUNITY = {
    "flashfire": "FIRE",        # Immune to fire, boosts fire moves on hit
    "sapsipper": "GRASS",       # Immune to grass, +1 atk on hit
    "levitate": "GROUND",       # Immune to ground moves
    "motordrive": "ELECTRIC",   # Immune to electric, +1 speed on hit
    "lightningrod": "ELECTRIC", # Immune to electric, +1 spa on hit (NOT heal)
    "stormdrain": "WATER",      # Immune to water, +1 spa on hit (NOT heal)
    "wonderguard": "*",         # Only super-effective hits work
}

# Healing abilities: defender heals 25% HP instead of taking damage (0 damage)
_ABILITY_HEALING = {
    "waterabsorb": ("WATER",),    # 0 dmg + heals on water moves
    "voltabsorb": ("ELECTRIC",),  # 0 dmg + heals on electric moves
    "dryskin": ("WATER",),        # 0 dmg + heals on water moves
    "eartheater": ("GROUND",),    # 0 dmg + heals on ground moves
}

# Damage reduction/increase abilities: take less (or more) damage from specific types
# Format: ability -> {move_type: multiplier}
_ABILITY_DAMAGE_REDUCTION = {
    "thickfat": {
        "FIRE": 0.5,    # Halves fire damage
        "ICE": 0.5,     # Halves ice damage
    },
    "heatproof": {
        "FIRE": 0.5,    # Halves fire damage
    },
    "waterbubble": {
        "FIRE": 0.5,    # Halves fire damage (offensive: doubles water)
    },
    "dryskin": {
        "FIRE": 1.25,   # Dry Skin takes 25% MORE from fire (already heals on water)
    },
    "fluffy": {
        "FIRE": 2.0,    # Fluffy: takes 2x fire damage
    },
    "purifyingsalt": {
        "GHOST": 0.5,   # Halves ghost damage + status immunity
    },
}

# Contact move damage modifiers: ability -> multiplier
# Applied based on move.flags["contact"]
_ABILITY_CONTACT_MOD = {
    "fluffy": 0.5,  # Halves damage from contact moves (only ability that modifies dmg)
}

# Super-effective resistance abilities: reduce SE damage to 0.75x
_ABILITY_SE_RESIST = {
    "solidrock", "filter", "prismarmor",
}

# Multi-hit resistance abilities (less common in randbats but include for completeness)
_ABILITY_MULTI_HIT_REDUCE = {
    "shieldsdown",   # Minior in meteor form (status/secondary blocking)
}


def _move_makes_contact(move) -> bool:
    """Check if a move makes physical contact (for Fluffy, Rocky Helmet, etc.)."""
    if not move:
        return False
    # Status moves don't make contact
    if (move.base_power or 0) <= 0:
        return False
    # Check move flags - poke-env exposes flags dict on Move objects
    flags = getattr(move, "flags", None) or {}
    if isinstance(flags, dict):
        return bool(flags.get("contact"))
    # Fallback: physical moves typically make contact (most do, but not all)
    return _is_physical_move(move)


def _check_ability_matchup(defender, move_type, type_eff: float = 1.0, move=None) -> tuple:
    """Check if defender's ability affects damage from this move type.

    Returns (damage_multiplier, heals) where:
    - damage_multiplier: 0.0 = immune, 0.5 = halved, 1.0 = normal, etc.
    - heals: True if the defender heals instead of taking damage

    Args:
        defender: the defending Pokemon
        move_type: the type of the incoming move
        type_eff: type effectiveness (for Solid Rock-like abilities)
        move: the full move object (for contact-based abilities like Fluffy)
    """
    ability = _norm(getattr(defender, "ability", None))
    if not ability:
        return (1.0, False)

    # Get the move type as a string (poke-env types have a 'name' attribute)
    type_name = getattr(move_type, "name", str(move_type)).upper()

    # Healing abilities: 0 damage + heals 25% HP
    if ability in _ABILITY_HEALING:
        if type_name in _ABILITY_HEALING[ability]:
            return (0.0, True)

    # Type immunity (no healing)
    if ability in _ABILITY_TYPE_IMMUNITY:
        immune_type = _ABILITY_TYPE_IMMUNITY[ability]
        if immune_type == type_name or immune_type == "*":
            # Wonder Guard: only SE damage gets through
            if ability == "wonderguard" and type_eff > 1.0:
                return (1.0, False)
            return (0.0, False)

    # Start with a 1.0 multiplier and stack reductions
    mult = 1.0

    # Damage reduction abilities (Thick Fat, Heatproof, Dry Skin fire bonus)
    if ability in _ABILITY_DAMAGE_REDUCTION:
        reductions = _ABILITY_DAMAGE_REDUCTION[ability]
        if type_name in reductions:
            mult *= reductions[type_name]

    # Super-effective resistance (Solid Rock, Filter, Prism Armor)
    if ability in _ABILITY_SE_RESIST and type_eff > 1.0:
        mult *= 0.75

    # Contact move modifiers (Fluffy halves contact damage)
    if move is not None and ability in _ABILITY_CONTACT_MOD:
        if _move_makes_contact(move):
            mult *= _ABILITY_CONTACT_MOD[ability]

    return (mult, False)


def _find_least_valuable_mon(battle) -> tuple:
    """Find the mon we should sacrifice in a sweep scenario.

    Returns (mon, value) — the mon with lowest strategic value to let take the hit.
    Preserves high-value mons for later in the game.
    """
    our_team = battle.team or {}
    active = battle.active_pokemon
    least_valuable = None
    least_value = float("inf")

    for mon in our_team.values():
        if mon is None or mon.fainted:
            continue
        # Don't sacrifice the active mon yet (it's already in)
        if active and mon.species == active.species:
            continue
        value = _mon_value(mon)
        if value < least_value:
            least_value = value
            least_valuable = mon

    return (least_valuable, least_value) if least_valuable else (None, float("inf"))


class ExpectimaxAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ablation hook (no effect unless PS_ABLATE is set): comma-list of
        # strategic categories to neutralize for A/B experiments, e.g.
        # PS_ABLATE="recovery,setup". An ablated move is scored as a plain
        # damaging move (_eval_move) so its strategic bonus is removed.
        import os as _os
        self._ablate = {c.strip() for c in _os.environ.get("PS_ABLATE", "").split(",") if c.strip()}
        self._value = HandcraftedValue()
        self._opp_power_cache = {}  # (opp_id, our_id, gen) → power
        self._battle_logger = None  # Created per battle
        self._battle_logs = []  # All completed battle logs
        self._strategic_ctx = None  # Per-turn strategic state (set in choose_move)
        self._opp_tracker = None    # Per-battle opp set tracker (created on first turn)
        # Sweep state: tracks opponent attack pattern across turns
        self._sweep_state = {
            "consecutive_attacks": 0,  # Turns opponent has attacked in a row (no switch)
            "last_opp_action": None,   # "move" or "switch"
            "last_opp_species": None,  # Track if opponent's mon changed
            "our_hp_lost": 0.0,        # Total HP we've lost in the streak
        }

    def choose_move(self, battle):
        announce_team(self, battle)
        type_chart = GenData.from_gen(battle.gen).type_chart
        self._opp_power_cache.clear()  # Fresh cache per turn

        # Initialize per-battle opp tracker on first turn
        if self._opp_tracker is None or self._battle_logger is None:
            from bot.data.opp_tracker import OppTeamTracker
            self._opp_tracker = OppTeamTracker()

        # Update tracker with currently-revealed opp info each turn.
        # Each new species = a slot; revealed moves prune possible sets.
        opp_team = battle.opponent_team or {}
        for opp_mon in opp_team.values():
            if opp_mon is None:
                continue
            self._opp_tracker.observe_pokemon(opp_mon.species)
            for move in opp_mon.moves.values():
                self._opp_tracker.observe_move(opp_mon.species, move.id)
            ability = getattr(opp_mon, "ability", None)
            if ability:
                self._opp_tracker.observe_ability(opp_mon.species, ability)

        # Compute once per turn: aggregate threat assessment + opp action prediction.
        # Used by move/switch evaluators to apply strategic context (SAFE/TRADEOFF/DANGER).
        if battle.active_pokemon is not None:
            self._strategic_ctx = _strategic_context(
                battle, battle.active_pokemon, type_chart, tracker=self._opp_tracker
            )
        else:
            self._strategic_ctx = None

        # Initialize logger on first turn of each battle
        if self._battle_logger is None:
            self._battle_logger = BattleLogger(
                battle_id=battle.battle_tag,
                our_name=self.username,
                opp_name=battle.opponent_username,
            )
            self._prev_opp_pokemon = None  # Track opponent's pokemon for switch detection

        # Record teams on first turn
        if battle.turn == 1:
            our_team = {
                p.species: {"level": p.level, "current_hp": p.current_hp_fraction}
                for p in battle.team.values() if p
            }
            opp_team = {
                p.species: {"level": p.level}
                for p in battle.opponent_team.values() if p
            }
            self._battle_logger.set_teams(our_team, opp_team)

        # Start turn logging
        our_pokemon = battle.active_pokemon.species if battle.active_pokemon else "?"
        opp_pokemon = battle.opponent_active_pokemon.species if battle.opponent_active_pokemon else "?"
        our_hp = battle.active_pokemon.current_hp_fraction if battle.active_pokemon else 1.0
        opp_hp = battle.opponent_active_pokemon.current_hp_fraction if battle.opponent_active_pokemon else 1.0

        # Detect what opponent did last turn
        opp_last_move = None
        opp_last_action = None
        opp_prev_pokemon = None
        if battle.opponent_active_pokemon:
            last_move = getattr(battle.opponent_active_pokemon, "last_move", None)
            if last_move:
                opp_last_move = last_move.id if hasattr(last_move, "id") else str(last_move)
                opp_last_action = "move"
            # Detect if opponent switched (their pokemon changed since last turn)
            if self._prev_opp_pokemon and self._prev_opp_pokemon != opp_pokemon:
                opp_last_action = "switch"
                opp_prev_pokemon = self._prev_opp_pokemon

        # Record switch-in pattern: track which opp mon comes in vs our active mon.
        # Used to predict clodsire-vs-jolteon style pivots in future turns.
        if opp_last_action == "switch" and self._opp_tracker is not None:
            self._opp_tracker.observe_switch_in(our_pokemon, opp_pokemon)

        # Update sweep state: consecutive attacks from opponent indicate a sweep
        if opp_last_action == "switch":
            # Opponent pivoted: reset sweep counter
            self._sweep_state["consecutive_attacks"] = 0
            self._sweep_state["our_hp_lost"] = 0.0
        elif opp_last_action == "move":
            # Opponent attacked: increment streak
            self._sweep_state["consecutive_attacks"] += 1
            # Track damage dealt to our active mon (rough estimate)
            prev_hp = getattr(self, "_prev_our_hp", 1.0)
            damage_taken = max(0.0, prev_hp - our_hp)
            self._sweep_state["our_hp_lost"] += damage_taken
        self._sweep_state["last_opp_action"] = opp_last_action
        self._sweep_state["last_opp_species"] = opp_pokemon
        self._prev_our_hp = our_hp

        # Extract strategic context for logging
        strategic_state = ""
        active_threat = 0.0
        bench_threat = 0.0
        unknown_threat = 0.0
        we_go_first = False
        opp_predicted_action = ""
        opp_predicted_damage = 0.0
        # Include sweep state for debugging the sacrifice logic
        is_real_sweep = (
            self._sweep_state["consecutive_attacks"] >= 2
            and self._sweep_state["our_hp_lost"] > 0.30
        )
        opp_set_predictions = {
            "sweep_consecutive_attacks": self._sweep_state["consecutive_attacks"],
            "sweep_hp_lost": round(self._sweep_state["our_hp_lost"], 3),
            "sweep_active": is_real_sweep,
        }

        if self._strategic_ctx:
            strategic_state = self._strategic_ctx["state"]
            active_threat = self._strategic_ctx["threat_breakdown"].get("active_threat", 0.0)
            bench_threat = self._strategic_ctx["threat_breakdown"].get("bench_threat", 0.0)
            unknown_threat = self._strategic_ctx["threat_breakdown"].get("unknown_threat", 0.0)
            opp_predicted_action = self._strategic_ctx["predicted_action"]["action"]
            opp_predicted_damage = self._strategic_ctx["predicted_action"]["expected_damage"]
            # For logging: check if we generally go first (without considering move priority)
            if battle.active_pokemon and battle.opponent_active_pokemon:
                our_speed = _effective_speed(battle.active_pokemon, use_actual=True)
                opp_speed = _effective_speed(battle.opponent_active_pokemon, use_actual=False)
                if _trick_room_active(battle):
                    we_go_first = our_speed <= opp_speed
                else:
                    we_go_first = our_speed >= opp_speed
            else:
                we_go_first = False

        # Get speed stages for logging (boosts dict uses "spe" key)
        our_speed_stage = (battle.active_pokemon.boosts or {}).get("spe", 0) if battle.active_pokemon else 0
        opp_speed_stage = (battle.opponent_active_pokemon.boosts or {}).get("spe", 0) if battle.opponent_active_pokemon else 0

        self._battle_logger.start_turn(
            battle.turn, our_pokemon, opp_pokemon, our_hp, opp_hp,
            opp_last_move=opp_last_move,
            opp_last_action=opp_last_action,
            opp_prev_pokemon=opp_prev_pokemon,
            strategic_state=strategic_state,
            active_threat=active_threat,
            bench_threat=bench_threat,
            unknown_threat=unknown_threat,
            our_speed_stage=our_speed_stage,
            opp_speed_stage=opp_speed_stage,
            we_go_first=we_go_first,
            opp_predicted_action=opp_predicted_action,
            opp_predicted_damage=opp_predicted_damage,
            opp_set_predictions=opp_set_predictions,
        )
        self._prev_opp_pokemon = opp_pokemon

        if not battle.available_moves and battle.available_switches:
            chosen_switch = _best_forced_switch(battle, type_chart, tracker=self._opp_tracker)
            order = self.create_order(chosen_switch)
            self._battle_logger.log_decision("switch", chosen_switch.species, 0.0, our_hp, opp_hp, chosen=True)
            self._battle_logger.end_turn()
            return order

        # Forced pseudo-moves (Recharge, Struggle, Outrage lock-in, Choice lock):
        # if the engine gives us exactly one option and no switches, there's no
        # decision to make — avoid evaluating the move since its data may be
        # incomplete (e.g. Recharge has no priority field).
        if len(battle.available_moves) == 1 and not battle.available_switches:
            move = battle.available_moves[0]
            order = self.create_order(move)
            self._battle_logger.log_decision("move", move.id, 0.0, our_hp, opp_hp, chosen=True)
            self._battle_logger.end_turn()
            return order

        best_order = None
        best_score = float("-inf")
        chosen_action = None

        # Wall-mode exploit (vs M3): if we comfortably tank the opponent's best
        # move and can't just KO it quickly, M3 will keep spamming a move that
        # barely dents us — and it can't status, recover, or escape. Reward the
        # long-game tools M3 has no answer to (status / recovery / setup) so we
        # convert unbreakable matchups into wins instead of slow even trades.
        wall_bonus = 0.0
        if _WALL and battle.active_pokemon is not None and battle.opponent_active_pokemon is not None:
            _opp_best = self._cached_opp_damage(
                battle.opponent_active_pokemon, battle.active_pokemon, type_chart
            )
            _our_best = self._best_damage_against(
                battle.active_pokemon, battle.opponent_active_pokemon, battle, type_chart
            )
            _our_hp_now = battle.active_pokemon.current_hp_fraction or 0.0
            if _opp_best <= _WALL_THRESH and _our_hp_now >= _WALL_MIN_HP and _our_best < _WALL_OUR_MAX:
                # Scale up the weaker their hit is (the more turns we can safely stall).
                strength = min(1.0, (_WALL_THRESH - _opp_best) / max(_WALL_THRESH, 1e-6))
                wall_bonus = _WALL_BONUS * (0.5 + 0.5 * strength)

        for move in battle.available_moves:
            if (move.current_pp or 0) == 0:
                continue

            mid = _norm(move.id)
            # Only POSITIVE boosts count as setup; Memento/Parting Shot/etc.
            # have negative boosts and shouldn't run a 2-turn setup rollout.
            is_setup = (
                move.boosts
                and any(v > 0 for v in move.boosts.values())
                and (move.base_power or 0) == 0
            )
            is_recovery = mid in _RECOVERY_MOVES
            is_hazard = mid in _HAZARD_MOVES
            is_status = mid in _STATUS_MOVES and _STATUS_MOVES[mid] is not None

            if is_setup and "setup" not in self._ablate:
                result = self._eval_setup_move(move, battle, type_chart)
            elif is_recovery and "recovery" not in self._ablate:
                result = self._eval_recovery_move(move, battle, type_chart)
            elif is_hazard and "hazard" not in self._ablate:
                result = self._eval_hazard_move(move, battle, type_chart)
            elif is_status and "status" not in self._ablate:
                result = self._eval_status_move(move, battle, type_chart)
            else:
                result = self._eval_move(move, battle, type_chart)

            # Ensure result is _EvalResult; convert float if needed
            if isinstance(result, float):
                result = _EvalResult(result)

            # Wall-mode: nudge status / recovery / setup above plain trading when
            # we're walling the opponent. Skips moves the evaluator already vetoed
            # (-inf), so unsafe setup/status don't get falsely promoted.
            if (
                wall_bonus
                and (is_status or is_recovery or is_setup)
                and result.score > float("-inf")
            ):
                result.score += wall_bonus

            self._battle_logger.log_decision(
                "move", move.id, result.score, our_hp, opp_hp, chosen=False,
                base_score=result.score,
                damage_dealt=result.damage_dealt,
                damage_taken=result.damage_taken,
                expected_hp_after=result.expected_hp_after,
                is_setup=is_setup,
                is_hazard=is_hazard,
                move_category=result.move_category,
                reasoning=result.reasoning,
            )
            if result.score > best_score:
                best_score = result.score
                best_order = self.create_order(move)
                chosen_action = ("move", move.id)

        for switch in battle.available_switches:
            result = self._eval_switch(switch, battle, type_chart)

            # Ensure result is _EvalResult; convert float if needed
            if isinstance(result, float):
                result = _EvalResult(result)

            self._battle_logger.log_decision(
                "switch", switch.species, result.score, our_hp, opp_hp, chosen=False,
                base_score=result.score,
                damage_dealt=result.damage_dealt,
                damage_taken=result.damage_taken,
                expected_hp_after=result.expected_hp_after,
                move_category="switch",
                reasoning=result.reasoning,
            )

            if result.score > best_score:
                best_score = result.score
                best_order = self.create_order(switch)
                chosen_action = ("switch", switch.species)

        # NOTE: an M3-style "switch gate" (require a switch to beat the best move
        # by a margin) was tested here and REGRESSED winrate at every margin
        # (0.10→48.3%, 0.15→46.1%, 0.20→45.5%). With the item-multiplier fix the
        # value model already justifies most switches, so gating them away just
        # forfeits good pivots. Left ungated deliberately.

        # Mark chosen action
        if chosen_action:
            for decision in self._battle_logger.current_turn.decisions:
                if decision.action_name == chosen_action[1]:
                    decision.chosen = True
                    break

        self._battle_logger.end_turn()
        return best_order if best_order is not None else self.choose_random_move(battle)

    def finalize_battle_log(self, battle):
        """Call after a battle ends to save the outcome to the log."""
        if self._battle_logger is not None:
            # Determine winner from battle state
            if battle.won:
                winner = "us"
            elif battle.lost:
                winner = "them"
            else:
                winner = None
            self._battle_logger.set_winner(winner)
            self._battle_logs.append(self._battle_logger.get_log())
            self._battle_logger = None
            self._prev_opp_pokemon = None
            self._opp_tracker = None  # Reset per-battle opp set tracker
            # Reset sweep state for next battle
            self._sweep_state = {
                "consecutive_attacks": 0,
                "last_opp_action": None,
                "last_opp_species": None,
                "our_hp_lost": 0.0,
            }
            self._prev_our_hp = 1.0

    def save_battle_logs(self, filename: str):
        """Save all battle logs to a JSON file."""
        from bot.agents.battle_logger import BattleLogCollector
        collector = BattleLogCollector()
        for log in self._battle_logs:
            collector.add_log(log)
        collector.save_to_file(filename)

    def get_battle_logs(self):
        """Get all battle logs."""
        return self._battle_logs

    def _eval_move(self, move, battle, type_chart):
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon

        # Determine move category
        move_category = ""
        if defender is None:
            # Turn 0: opp lead not yet visible. Score moves by their inherent
            # power (BP * STAB * accuracy) so we pick our strongest STAB attack.
            # This reflects: we have no info, so commit to the best move our
            # lead offers. Switches also score 0 here — both sides are blind.
            bp = move.base_power or 0
            if bp <= 0:
                return _EvalResult(0.0)
            stab = 1.5 if attacker and move.type in attacker.types else 1.0
            acc = _accuracy(move)
            # Normalize: a 120 BP STAB move ~= 0.36 baseline
            score = (bp * stab * acc) / 500.0
            move_category = "status"
            return _EvalResult(score, reasoning="Turn 0: blind lead evaluation")

        # Determine move category (physical/special/status)
        if move.base_power and move.base_power > 0:
            move_category = "physical" if _is_physical_move(move) else "special"
        else:
            move_category = "status"

        # Never use a move that heals the opponent (Water Absorb, Volt Absorb, etc.)
        if (move.base_power or 0) > 0:
            _, heals_opp = _check_ability_matchup(defender, move.type, move=move)
            if heals_opp:
                return _EvalResult(
                    float("-inf"),
                    damage_dealt=0.0,
                    damage_taken=0.0,
                    expected_hp_after=attacker.current_hp_fraction if attacker else 1.0,
                    move_category=move_category,
                    reasoning="Move heals opponent — never use",
                )

        # Read our active boosts so Swords Dance, Nasty Plot, etc. are reflected
        boosts = (attacker.boosts if attacker else None) or {}
        is_physical = _is_physical_move(move)
        atk_boost = boosts.get("atk" if is_physical else "spa", 0)

        our_damage = _damage_fraction(move, attacker, defender, type_chart, atk_boost=atk_boost)

        # Symmetry fix: opponent threat (_max_threat_via_movepool) already applies
        # Choice Band/Specs/Life Orb multipliers, but our own damage didn't — so the
        # bot systematically undervalued attacking (especially with Choice users) and
        # over-preferred switching/healing. Mirror the same item multipliers here.
        our_item = _norm(getattr(attacker, "item", None)) if attacker else ""
        if is_physical and our_item == "choiceband":
            our_damage *= 1.5
        elif (not is_physical) and our_item == "choicespecs":
            our_damage *= 1.5
        elif our_item == "lifeorb":
            our_damage *= 1.3

        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

        # Apply Stakeout ability bonus (2x damage if opponent switches)
        # Stakeout (and similar abilities) reward switching predictions
        if attacker and _norm(getattr(attacker, "ability", None)) == "stakeout":
            # Check if opponent is predicted to switch (from strategic context)
            ctx = self._strategic_ctx
            if ctx and ctx.get("predicted_action", {}).get("action") == "switch":
                our_damage *= 2.0

        our_hp = attacker.current_hp_fraction if attacker else 1.0
        opp_hp = defender.current_hp_fraction if defender else 1.0

        if _we_go_first(move, attacker, defender, battle):
            opp_after = max(0.0, opp_hp - our_damage)
            our_after = max(0.0, our_hp - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_hp - opp_damage)
            opp_after = max(0.0, opp_hp - (our_damage if our_after > 0.0 else 0.0))

        # Stay-in score: opp commits to attacking with their best move.
        # Don't penalize for predicted switches here — over-discounting damage
        # caused a death spiral of constant switching. Switch prediction is
        # better used to BOOST setup/recovery (free turn value) elsewhere.
        base_score = self._value.score_transition(battle, our_after, opp_after)

        # Early-game caution: penalize aggressive attacks when we don't know opp's team.
        # BUT: Don't penalize if we have a clear advantage (high damage, STAB, type coverage).
        # Type advantage moves should never be penalized for being risky.
        info_deficit = _info_deficit(battle)
        if info_deficit > 0.3 and our_after < 0.55:
            # Only apply risk penalty if we don't have clear damage advantage
            # If we're dealing decent damage (>0.3) relative to opponent, it's not risky
            damage_ratio = our_damage / max(opp_damage, 0.01) if opp_damage > 0 else 1.0

            # Don't penalize if: (1) we go first and damage is significant, or
            # (2) our damage is much higher than theirs (winning the trade)
            goes_first = _we_go_first(move, attacker, defender, battle)
            is_clearly_winning = our_damage > 0.3 and (goes_first or damage_ratio > 1.5)

            if not is_clearly_winning:
                # Risky play when we have limited information about opp team
                risk_penalty = info_deficit * (0.55 - our_after) * _RISK_PEN
                base_score -= risk_penalty

        # KO value: expected reward for securing the kill THIS turn, scaled by the
        # TRUE roll-to-KO probability. This replaces both (a) the old binary
        # trigger (opp_after <= 0), which fired on the 100% roll and over-committed
        # the bot to "KOs" that only land on high rolls, and (b) the separate
        # near-KO heuristic. p_ko = 1.0 only for a guaranteed KO (even the min roll
        # kills); partial otherwise. Only counts if we actually land the hit: if we
        # move second and faint first, we deal no damage.
        goes_first = _we_go_first(move, attacker, defender, battle)
        acc = _accuracy(move)
        on_hit = our_damage / acc if acc > 0 else our_damage
        deals_hit = goes_first or our_after > 0.0
        p_ko = acc * _ko_probability(on_hit, opp_hp) if deals_hit else 0.0
        ko_bonus = _KO_BONUS * p_ko
        near_ko_bonus = 0.0  # subsumed by the p_ko-scaled ko_bonus above

        # Doomed-mon bonus: if our active mon will die regardless this turn (opp goes
        # first AND opp_damage >= our_hp), then dying-while-dealing-damage is strictly
        # better than switching out a still-alive but doomed mon. Reward priority moves
        # / any damage we can squeeze out of our active mon before fainting.
        # Without this, switching to a "fresh" mon scores higher even though that mon
        # also can't beat the opponent — wasting the dying mon's free attack.
        doomed_bonus = 0.0
        is_doomed = (not goes_first) and opp_damage >= our_hp and our_hp > 0
        if is_doomed and our_damage > 0:
            # Active mon is doomed; if this move has priority, we DO get a hit in.
            # Damage dealt before dying is bonus value (opp loses HP, we lose nothing extra).
            move_priority = getattr(move, "priority", 0) or 0
            if move_priority > 0:
                # Priority move sneaks in damage before fainting — high value
                doomed_bonus = 0.25 + our_damage * 0.20
            else:
                # Non-priority move: we die without dealing damage, but staying in
                # at least doesn't waste a different mon's HP on the switch-in.
                # Small bonus so we don't over-prefer switching to a sacrificial pivot.
                doomed_bonus = 0.05

        # Tiebreakers (small bonuses, won't affect non-tied decisions):
        # 1. Prefer STAB moves (more reliable damage, harder to resist)
        # 2. Prefer higher raw damage (overkill = safety vs miscalculation)
        if attacker and move.type in attacker.types:
            base_score += 0.002  # STAB tiebreaker
        base_score += our_damage * 0.001  # Damage tiebreaker

        # 2-ply lookahead: value the position this move leaves us in next turn
        # (KO timing — does our KO bring in a revenge-killer? does staying in win
        # the follow-up exchange?). No-op when _LOOKAHEAD == 0.
        lookahead = self._lookahead_term(battle, attacker, our_after, defender, opp_after, type_chart)

        reasoning = f"damage_to_opp={our_damage:.3f}, damage_from_opp={opp_damage:.3f}, ko_bonus={ko_bonus:.3f}, doomed_bonus={doomed_bonus:.3f}, near_ko_bonus={near_ko_bonus:.3f}, lookahead={lookahead:.3f}"
        return _EvalResult(
            base_score + ko_bonus + doomed_bonus + near_ko_bonus + lookahead,
            damage_dealt=our_damage,
            damage_taken=opp_damage,
            expected_hp_after=our_after,
            move_category=move_category,
            reasoning=reasoning,
        )

    def _best_damage_against(self, attacker, defender, battle, type_chart) -> float:
        """Best damage fraction we can deal with our currently-available moves."""
        if not attacker or not defender:
            return 0.0
        boosts = attacker.boosts or {}
        best = 0.0
        for m in battle.available_moves:
            if (m.base_power or 0) <= 0:
                continue
            boost = boosts.get("atk" if _is_physical_move(m) else "spa", 0)
            d = _damage_fraction(m, attacker, defender, type_chart, atk_boost=boost)
            best = max(best, d)
        return best

    def _eval_setup_move(self, move, battle, type_chart):
        """Evaluate setup moves via 2-turn virtual rollout.

        Turn 1: we set up, opp attacks. Turn 2: we attack with boost, opp attacks.
        M3 won't switch, setup, or Tera so the rollout is deterministic.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return _EvalResult(float("-inf"), reasoning="No attacker or defender")

        # CRITICAL: Reject locking moves (No Retreat) unless we guarantee a KO.
        # No Retreat locks you in, making you unable to switch next turn.
        move_id = _norm(getattr(move, "id", ""))
        if move_id == "noretreat":
            # Only allow No Retreat if we'll KO the opponent after boosting
            # Check if we can KO with best move after stat boosts
            atk_boost = move.boosts.get("atk", 0) if move.boosts else 0
            spa_boost = move.boosts.get("spa", 0) if move.boosts else 0

            best_ko_damage = 0.0
            for m in battle.available_moves:
                if (m.base_power or 0) <= 0:
                    continue
                boost = atk_boost if _is_physical_move(m) else spa_boost
                dmg = _damage_fraction(m, attacker, defender, type_chart, atk_boost=boost)
                best_ko_damage = max(best_ko_damage, dmg)

            # Only allow No Retreat if we can KO (damage >= 1.0)
            if best_ko_damage < 1.0:
                return _EvalResult(float("-inf"), is_setup=True, reasoning="No Retreat locks you in but won't KO opponent")

        # CRITICAL: Never setup when we're weak to opponent's type.
        # Check if opponent's type is super-effective against our types.
        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

        # Worst-case threat for setup planning: if opp is predicted to switch,
        # we'll face their switch-in at +stages. Use the predicted switch-in's
        # damage so we don't underestimate the cost of staying in to use the boost.
        # When opp stays, the current active's damage is the right estimate.
        ctx = self._strategic_ctx
        worst_opp_damage = opp_damage
        if ctx is not None:
            predicted = ctx.get("predicted_action", {})
            if predicted.get("action") == "switch":
                worst_opp_damage = max(opp_damage, predicted.get("expected_damage", 0.0))

        # Check type advantage: for each opponent type, see if moves of that type
        # are super-effective against us.
        for opp_type in [defender.type_1, defender.type_2]:
            if opp_type:
                dmg_mult = opp_type.damage_multiplier(attacker.type_1, attacker.type_2, type_chart=type_chart)
                # If opponent's type is 2x effective or higher against us, setup is risky
                if dmg_mult >= 2.0:
                    return _EvalResult(float("-inf"), is_setup=True, reasoning=f"We're weak to {opp_type} (opponent's type), cannot setup safely")

        our_hp_t1 = attacker.current_hp_fraction if attacker else 1.0
        # Use worst_opp_damage for the survival check: if the bench can OHKO us at
        # +stages, setup is wasted (boost dies with us).
        our_after_t1 = max(0.0, our_hp_t1 - worst_opp_damage)
        if our_after_t1 <= 0.0:
            # Setup with no payoff: we faint without using the boost. Strictly worse
            # than any damaging move (which at least might land if we have priority
            # or speed). Return -inf so we never set up while in KO range.
            return _EvalResult(float("-inf"), damage_taken=worst_opp_damage, expected_hp_after=0.0, is_setup=True, reasoning=f"Setup would result in KO — worst threat does {worst_opp_damage:.2f} (active does {opp_damage:.2f})")

        atk_boost = move.boosts.get("atk", 0) if move.boosts else 0
        spa_boost = move.boosts.get("spa", 0) if move.boosts else 0
        if atk_boost <= 0 and spa_boost <= 0:
            return _EvalResult(float("-inf"), is_setup=True, reasoning="No positive boosts")

        best_our_damage_t2 = 0.0
        for m in battle.available_moves:
            if (m.base_power or 0) <= 0:
                continue
            boost = atk_boost if _is_physical_move(m) else spa_boost
            dmg = _damage_fraction(m, attacker, defender, type_chart, atk_boost=boost)
            best_our_damage_t2 = max(best_our_damage_t2, dmg)

        # T2 damage: use worst-case (active or bench), since by then opp may have
        # switched to a stronger threat. Otherwise we systematically underestimate
        # the cost of staying in to use the boost.
        t2_opp_damage = worst_opp_damage
        if _effective_speed(attacker, use_actual=True) >= _effective_speed(defender, use_actual=False):
            opp_after = max(0.0, defender.current_hp_fraction - best_our_damage_t2)
            our_after = max(0.0, our_after_t1 - (t2_opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_after_t1 - t2_opp_damage)
            opp_after = max(0.0, defender.current_hp_fraction - (best_our_damage_t2 if our_after > 0.0 else 0.0))

        score = self._value.score_transition(battle, our_after, opp_after)

        # If opp will likely switch, setup is a free turn — bonus.
        # We'd boost without taking damage, then face their counter at +stages.
        our_best_damage = self._best_damage_against(attacker, defender, battle, type_chart)
        info_deficit = _info_deficit(battle)
        switch_prob = _estimate_opp_switch_probability(opp_damage, our_best_damage, info_deficit)
        if switch_prob > 0.0:
            # Setup is much better when opp switches: free boost + opp uses turn switching
            score += switch_prob * 0.15

        # Strategic context: SAFE state = aggregate threat is low across opp's
        # whole team, so setting up is much safer (we can survive multiple turns).
        ctx = self._strategic_ctx
        if ctx is not None:
            if ctx["state"] == "SAFE":
                score += 0.15  # Strong bonus: opp can't hurt us much
            elif ctx["state"] == "DANGER":
                score -= 0.10  # Avoid setup when threats loom

        # Setup-sweep bet: M3 can't punish setup (no phazing/priority coordination),
        # so leaning into boosts when we survive the turn can snowball into a sweep.
        if _SETUP_BONUS and our_after_t1 > 0.0:
            score += _SETUP_BONUS

        reasoning = f"2-turn setup: +{atk_boost}atk/+{spa_boost}spa, t2_damage={best_our_damage_t2:.3f}, opp_dmg={opp_damage:.3f}, worst_opp_dmg={worst_opp_damage:.3f}"
        return _EvalResult(
            score,
            damage_taken=opp_damage * 2,
            damage_dealt=best_our_damage_t2,
            expected_hp_after=our_after,
            is_setup=True,
            move_category="status",
            reasoning=reasoning,
        )

    def _eval_recovery_move(self, move, battle, type_chart):
        """Evaluate recovery moves considering actual effective healing.

        - Caps healing at 100% HP (no wasted heal reward)
        - Handles delayed healing (Wish): penalizes since healing isn't instant
        - Adds Leftovers passive heal (+1/16 per turn) if held
        - Rewards net-positive healing (heal > damage taken = stall win)
        - Skip healing if we'd faint this turn (use attack instead)
        - Special: Rest + Sleep Talk combo (3-turn rollout: Rest → Sleep Talk → Sleep Talk → Wake)
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return _EvalResult(float("-inf"), reasoning="No attacker or defender")

        # SPECIAL: Rest + Sleep Talk combo evaluation
        # Rest heals to 100% but puts us asleep for 2 turns, then Sleep Talk randomizes moves
        move_id = _norm(getattr(move, "id", ""))
        if move_id == "rest":
            # Check if we have Sleep Talk available
            has_sleep_talk = any(_norm(getattr(m, "id", "")) == "sleeptalk" for m in battle.available_moves)
            if has_sleep_talk:
                # 3-turn rollout: Rest (heal to 100%), then 2 turns of Sleep Talk (random moves)
                opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

                # Turn 0: Rest heals us to 100%, we fall asleep
                our_after_turn0 = max(0.0, 1.0 - opp_damage)  # Opponent attacks after we Rest

                # Turns 1-2: Sleep Talk (forced while asleep)
                # Assume Sleep Talk randomly uses one of our damage moves (avg damage)
                our_best_damage = self._best_damage_against(attacker, defender, battle, type_chart)
                sleep_talk_damage = our_best_damage * 0.75  # Sleep Talk uses random move, assume 75% of best

                # Turn 1: Sleep Talk → opponent attacks
                opp_after_t1 = max(0.0, defender.current_hp_fraction - sleep_talk_damage) if sleep_talk_damage > 0 else defender.current_hp_fraction
                our_after_t1 = max(0.0, our_after_turn0 - opp_damage)

                # Turn 2: Sleep Talk → opponent attacks (we wake up after this turn)
                opp_after_t2 = max(0.0, opp_after_t1 - sleep_talk_damage) if sleep_talk_damage > 0 else opp_after_t1
                our_after_t2 = max(0.0, our_after_t1 - opp_damage)

                # Evaluate the 3-turn sequence
                if our_after_t2 > 0:
                    # We survived Rest + 2x Sleep Talk cycle
                    score = self._value.score_transition(battle, our_after_t2, opp_after_t2)
                    # Bonus for healing combo that lets us survive and deal damage
                    if sleep_talk_damage > 0:
                        score += 0.15  # Combo bonus
                    reasoning = f"Rest+Sleep Talk: heal=1.0, 2x Sleep Talk dmg~{sleep_talk_damage:.2f}, survive={our_after_t2:.2f}"
                    return _EvalResult(score, damage_taken=opp_damage * 3, expected_hp_after=our_after_t2,
                                     move_category="status", reasoning=reasoning)

        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)
        our_hp = attacker.current_hp_fraction if attacker else 1.0
        opp_hp = defender.current_hp_fraction

        # Raw heal amount (most recovery moves = 0.5)
        hp_recovered = float(move.heal) if move.heal else 0.5

        # Wish is delayed healing — only 1/8 effective this turn (we may switch/faint)
        if _norm(move.id) == "wish":
            hp_recovered *= 0.125

        # Compute HP state: take damage first, then heal, then leftovers
        hp_after_damage = max(0.0, our_hp - opp_damage)

        # Don't heal if we'd faint this turn (better to attack)
        if hp_after_damage <= 0.0:
            return _EvalResult(float("-inf"), reasoning="Would faint this turn")

        # At high HP, only heal if opponent's threat justifies it
        if our_hp >= 0.80:
            # Threat must be significant (opponent deals >= 30% damage to justify healing at high HP)
            if opp_damage < 0.30:
                return _EvalResult(float("-inf"), reasoning="High HP + low threat = wasteful healing")

            # Healing must meaningfully mitigate opponent's damage (heal >= 75% of threat)
            if hp_recovered < opp_damage * 0.75:
                return _EvalResult(float("-inf"), reasoning=f"Healing ({hp_recovered:.2f}) doesn't mitigate threat ({opp_damage:.2f})")

            # We must be dealing enough damage to not create a stall loop
            # If we can't deal >15% damage, we're just wasting PP healing indefinitely
            our_best_damage = self._best_damage_against(attacker, defender, battle, type_chart)
            if our_best_damage < 0.15:
                return _EvalResult(float("-inf"), reasoning="Not threatening opponent enough, healing creates PP stall loop")

        hp_after_heal = min(1.0, hp_after_damage + hp_recovered)

        # Leftovers adds 1/16 on end of turn
        if _norm(getattr(attacker, "item", None)) == "leftovers":
            hp_after_heal = min(1.0, hp_after_heal + 1 / 16)

        # Effective heal (accounts for waste if capped at 1.0)
        effective_heal = hp_after_heal - hp_after_damage

        base_score = self._value.score_transition(battle, hp_after_heal, opp_hp)

        # Stall win: net HP gain (heal - damage) > threshold
        net_gain = effective_heal - opp_damage
        stall_bonus = 0.0
        if net_gain > 0.05:
            stall_bonus = min(0.2, net_gain * 0.4)  # Scaled by magnitude

        # PP penalty for low PP (finite healing)
        pp_penalty = 0.0
        if (move.current_pp or 0) < _MIN_PP_PENALTY:
            pp_penalty = -0.1

        score = base_score + stall_bonus + pp_penalty
        reasoning = f"heal={hp_recovered:.3f}, opp_dmg={opp_damage:.3f}, final_hp={hp_after_heal:.3f}"
        return _EvalResult(
            score,
            damage_taken=opp_damage,
            expected_hp_after=hp_after_heal,
            move_category="status",
            reasoning=reasoning,
        )

    def _eval_hazard_move(self, move, battle, type_chart):
        """Evaluate hazard-setting moves (Stealth Rock, Spikes, Toxic Spikes, Sticky Web).

        Value scales with opponent's remaining Pokemon (more switches = more value)
        and hazard effectiveness. Don't set if already up or opponent low on mons.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return _EvalResult(float("-inf"), reasoning="No attacker or defender")

        mid = _norm(move.id)
        opp_side = battle.opponent_side_conditions or {}

        # Don't re-set existing hazards
        if mid == "stealthrock":
            if _match_condition(opp_side, "stealthrock") is not None:
                return _EvalResult(float("-inf"), reasoning="Stealth Rock already set")
            base_value = 0.35  # High value - works vs most mons
        elif mid == "spikes":
            existing = _match_condition(opp_side, "spikes")
            layers = opp_side.get(existing, 0) if existing else 0
            if layers >= 3:
                return _EvalResult(float("-inf"), reasoning="Spikes already at max layers")
            base_value = 0.25 - layers * 0.08  # Diminishing returns
        elif mid == "toxicspikes":
            existing = _match_condition(opp_side, "toxicspikes")
            layers = opp_side.get(existing, 0) if existing else 0
            if layers >= 2:
                return _EvalResult(float("-inf"), reasoning="Toxic Spikes already at max")
            # Check if opp has any revealed Poison-type (absorbs T-Spikes on switch-in)
            opp_team = battle.opponent_team or {}
            has_poison_absorber = any(
                p and "POISON" in _pokemon_type_names(p)
                for p in opp_team.values()
            )
            if has_poison_absorber:
                return _EvalResult(float("-inf"), reasoning="Poison-type absorber present")
            base_value = 0.20 - layers * 0.08
        elif mid == "stickyweb":
            if _match_condition(opp_side, "stickyweb") is not None:
                return _EvalResult(float("-inf"), reasoning="Sticky Web already set")
            base_value = 0.20
        else:
            return _EvalResult(float("-inf"), reasoning="Unknown hazard move")

        # Count opp mons with HP remaining (each future switch = more value)
        opp_team = battle.opponent_team or {}
        opp_mons_left = sum(
            1 for p in opp_team.values()
            if p and (p.current_hp_fraction or 0) > 0
        )
        opp_mons_left = max(opp_mons_left, 2)  # Always assume at least 2 left

        # Scale value by number of remaining switches we expect
        value = base_value * min(1.0, (opp_mons_left - 1) / 4.0)

        # Pay the cost of taking a hit while setting up
        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)
        our_hp = attacker.current_hp_fraction if attacker else 1.0
        our_after = max(0.0, our_hp - opp_damage)

        # If we faint setting up, it's only worth it if we'd lose anyway
        if our_after <= 0.0 and our_hp < 0.3:
            return _EvalResult(float("-inf"), reasoning="Would faint setting hazard")

        opp_hp = defender.current_hp_fraction if defender else 1.0
        base_score = self._value.score_transition(battle, our_after, opp_hp)

        # Strategic context: hazards are gold when opp has many switches AND
        # we're safe (won't lose HP setting them). They're also more valuable
        # when opp is predicted to switch (the switch eats hazard damage).
        ctx = self._strategic_ctx
        if ctx is not None:
            if ctx["state"] == "SAFE" and opp_mons_left >= 4:
                value *= 1.4  # Early-game safe hazards are highest-EV play
            if ctx["opp_will_switch"]:
                value *= 1.2  # Opp switching = immediate hazard payoff

        # Future-value discount: hazards only pay off if we live long enough to
        # see opp switch into them. When we're losing badly (few mons left + in
        # DANGER), prefer immediate damage over setup. Setting SR with our 5th
        # mon at low HP while losing the game = wasted turn vs. a damage move
        # that has any chance of pressuring opp.
        our_team = (battle.team or {}).values()
        our_mons_alive = sum(
            1 for p in our_team
            if p and (p.current_hp_fraction or 0) > 0
        )
        if our_mons_alive <= 2 and ctx is not None and ctx["state"] == "DANGER":
            # Down to last 1-2 mons under pressure: hazard value collapses.
            # Damage moves should win if they have any chance of helping.
            value *= 0.3

        score = base_score + value
        reasoning = f"{mid}: opp_mons_left={opp_mons_left}, value={value:.3f}, opp_dmg={opp_damage:.3f}"
        return _EvalResult(
            score,
            damage_taken=opp_damage,
            expected_hp_after=our_after,
            is_hazard=True,
            move_category="status",
            reasoning=reasoning,
        )

    def _eval_status_move(self, move, battle, type_chart) -> float:
        """Evaluate status-inflicting moves (Will-O-Wisp, Toxic, Thunder Wave, etc.).

        Value based on target's vulnerability and expected residual damage
        over remaining turns.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        mid = _norm(move.id)
        status_type = _STATUS_MOVES.get(mid)
        if not status_type:
            return float("-inf")

        # Don't re-apply if opp already statused
        if defender.status is not None:
            return float("-inf")

        # Immunity checks
        if status_type == "burn" and "FIRE" in _pokemon_type_names(defender):
            return float("-inf")
        if status_type in ("poison", "badpoison"):
            types = _pokemon_type_names(defender)
            if "POISON" in types or "STEEL" in types:
                return float("-inf")
        if status_type == "paralyze" and "ELECTRIC" in _pokemon_type_names(defender):
            return float("-inf")
        if status_type == "sleep":
            # Sleep Powder etc. miss Grass types and Overcoat/Safety Goggles mons
            if mid in ("sleeppowder", "spore", "stunspore", "poisonpowder"):
                if "GRASS" in _pokemon_type_names(defender):
                    return float("-inf")
            if _norm(getattr(defender, "ability", None)) in ("overcoat", "insomnia", "vitalspirit"):
                return float("-inf")
            # Sleep Clause: only one opp mon can be asleep at a time
            opp_team = battle.opponent_team or {}
            for p in opp_team.values():
                if p and p.status is not None:
                    status_name = getattr(p.status, "name", str(p.status)).upper()
                    if "SLP" in status_name or "SLEEP" in status_name:
                        return float("-inf")

        # Accuracy
        acc = _accuracy(move)

        # Value by status type
        if status_type == "burn":
            # Halves physical damage + 1/16 residual.
            # Value scales with how physically inclined the target is.
            base_atk = (defender.base_stats or {}).get("atk") or 100
            base_spa = (defender.base_stats or {}).get("spa") or 100
            if base_atk > base_spa * 1.3:
                base_value = 0.40  # Strongly physical - huge value
            elif base_spa > base_atk * 1.3:
                base_value = 0.05  # Strongly special - nearly useless (residual only)
            else:
                base_value = 0.20  # Balanced/mixed
            base_value += 0.08  # Residual burn damage component
        elif status_type == "badpoison":
            # Toxic: escalating damage, value scales with target's bulk.
            # Bulk = HP * (Def + SpDef) / 100000 (normalized to ~0-1 range)
            base_hp = (defender.base_stats or {}).get("hp") or 100
            base_def = (defender.base_stats or {}).get("def") or 100
            base_spd = (defender.base_stats or {}).get("spd") or 100
            bulk = (base_hp * (base_def + base_spd)) / 100000.0
            # Scale: 0.15 minimum, up to 0.45 for ultra-bulky (Blissey-tier)
            base_value = min(0.45, 0.15 + bulk * 0.25)
        elif status_type == "poison":
            # Regular poison: 1/8 per turn, similar bulk-scaling but less impactful
            base_hp = (defender.base_stats or {}).get("hp") or 100
            base_def = (defender.base_stats or {}).get("def") or 100
            base_spd = (defender.base_stats or {}).get("spd") or 100
            bulk = (base_hp * (base_def + base_spd)) / 100000.0
            base_value = min(0.30, 0.10 + bulk * 0.15)
        elif status_type == "paralyze":
            # 25% skip turn + 50% speed drop. Value scales with opp's speed -
            # paralyzing a fast threat is huge, paralyzing a slow mon is minor.
            base_spe = (defender.base_stats or {}).get("spe") or 100
            if base_spe >= 120:
                base_value = 0.30  # Fast threat - paralysis neuters it
            elif base_spe >= 100:
                base_value = 0.22  # Moderately fast
            elif base_spe >= 80:
                base_value = 0.15  # Middling
            else:
                base_value = 0.08  # Already slow, paralysis less valuable
        elif status_type == "sleep":
            # 1-3 turns of no action - always high value regardless of target.
            base_value = 0.35
        else:
            base_value = 0.10

        # Pay the cost of taking a hit while statusing
        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)
        our_hp = attacker.current_hp_fraction if attacker else 1.0
        our_after = max(0.0, our_hp - opp_damage)

        if our_after <= 0.0 and our_hp < 0.3:
            return float("-inf")

        opp_hp = defender.current_hp_fraction if defender else 1.0
        base_score = self._value.score_transition(battle, our_after, opp_hp)

        # Role-aware boost: defensive Pokemon (Mandibuzz, Toxapex) survive long
        # enough to make residual damage really pay off. Scale value by how many
        # turns we'll likely live to apply pressure.
        if _is_defensive_role(attacker) and opp_damage > 0.0:
            turns_to_survive = our_hp / max(opp_damage, 0.05)
            # 3+ turns survival ≈ 1.5x value, capped at 2x for ultra-tanks
            survivability = min(2.0, max(1.0, turns_to_survive / 3.0))
            base_value *= survivability

        score = base_score + base_value * acc
        reasoning = f"{status_type}: acc={acc:.2f}, value={base_value * acc:.3f}, opp_dmg={opp_damage:.3f}"
        return _EvalResult(
            score,
            damage_taken=opp_damage,
            expected_hp_after=our_after,
            move_category="status",
            reasoning=reasoning,
        )

    def _eval_switch(self, pokemon, battle, type_chart):
        opp = battle.opponent_active_pokemon

        # CRITICAL: Never switch into a type that opponent is super-effective against.
        # If opponent's type is 2x+ effective against our switch-in, this is a terrible idea.
        if opp is not None:
            for opp_type in [opp.type_1, opp.type_2]:
                if opp_type:
                    dmg_mult = opp_type.damage_multiplier(pokemon.type_1, pokemon.type_2, type_chart=type_chart)
                    # If opponent's type is 2x+ effective against our switch-in, heavily penalize
                    if dmg_mult >= 2.0:
                        return _EvalResult(float("-inf"), reasoning=f"Switch target {pokemon.species} is weak to {opp_type}")

        # If opp is fainted, they're sending in a fresh mon at full HP — we
        # can't claim credit for an already-dead Pokemon. Otherwise every
        # switch would score +1.0 (free KO bonus) and we'd pivot needlessly.
        opp_is_fainted = opp is not None and (opp.fainted or opp.current_hp_fraction <= 0.0)
        if opp_is_fainted:
            # Fresh mon coming. Use unknown-mon threat as expected damage and
            # the worst threat from opp's revealed bench (sets DB movepool).
            opp_damage = max(
                _unknown_mon_threat(pokemon) if _info_deficit(battle) > 0.0 else 0.0,
                self._max_bench_threat(battle, pokemon, type_chart),
            )
            opp_after = 1.0   # Fresh mon will be at full HP
        else:
            # Active opp's damage, but also consider that a still-unrevealed
            # mon could come in to punish our switch-in.
            current_threat = self._cached_opp_damage(opp, pokemon, type_chart)
            unknown_threat = _unknown_mon_threat(pokemon) * _info_deficit(battle)
            bench_threat = self._max_bench_threat(battle, pokemon, type_chart)
            # Worst-case: weight bench/unknown threats less since opp picks one path
            opp_damage = max(current_threat, 0.5 * max(unknown_threat, bench_threat))
            opp_after = opp.current_hp_fraction if opp else 1.0
        hazard = _hazard_damage(pokemon, battle.side_conditions, type_chart)
        our_after = max(0.0, pokemon.current_hp_fraction - hazard - opp_damage)

        base_score = self._value.score_transition(battle, our_after, opp_after)

        offensive_bonus = _switch_offensive_bonus(pokemon, opp, type_chart)

        # Ability matchup bonus: if switching into a mon with ability that counters
        # opponent's move type (e.g., Water Absorb vs Wave Crash), huge bonus.
        ability_bonus = 0.0
        if opp is not None:
            # Find opponent's likely move type (best damaging move)
            best_move = None
            best_bp = 0
            for move in opp.moves.values():
                bp = move.base_power or 0
                if bp > best_bp:
                    best_bp = bp
                    best_move = move
            if best_move:
                # Compute type effectiveness for this move vs the switch-in pokemon
                eff = best_move.type.damage_multiplier(
                    pokemon.type_1, pokemon.type_2, type_chart=type_chart
                )
                ability_mult, heals = _check_ability_matchup(
                    pokemon, best_move.type, type_eff=eff, move=best_move
                )
                if heals:
                    ability_bonus = 0.25  # Huge bonus: we heal from their move
                elif ability_mult == 0.0:
                    ability_bonus = 0.20  # Big bonus: type immunity (Levitate, Flash Fire)
                elif ability_mult < 1.0:
                    ability_bonus = 0.10  # Minor bonus: damage reduction

        # Early-game info-gathering bonus: reward pivots into hard resists when
        # we don't know much about opp's team. Less commit, more scouting.
        # IMPORTANT: only when opp is actually visible — Turn 0 has no opp,
        # so blind switching is just gambling, not "scouting".
        info_deficit = _info_deficit(battle)
        info_bonus = 0.0
        if opp is not None and info_deficit > 0.3 and opp_damage < 0.20:
            # Hard resist switch-in during low-info phase = valuable scouting
            info_bonus = info_deficit * 0.15

        # Strategic context adjustments:
        # 1. SAFE state: active mon isn't threatened, switching wastes momentum
        # 2. DANGER + switch-in dies: this is a wasted switch (sacrifice cycle)
        # 3. DANGER + sweep: reward sacrificing low-value mons, penalize wasting high-value ones
        ctx = self._strategic_ctx
        ctx_adj = 0.0
        if ctx is not None:
            active = battle.active_pokemon
            if ctx["state"] == "SAFE" and active is not None:
                # Active is safe — switching forfeits a turn for no reason
                ctx_adj -= 0.10

            # Sweep detection: opponent attacking repeatedly (2+ turns) AND we lost HP.
            # In a real sweep, prefer to sacrifice low-value mons to break momentum.
            # This stops the "spam-switch into a sweep" death spiral.
            is_real_sweep = (
                self._sweep_state["consecutive_attacks"] >= 2
                and self._sweep_state["our_hp_lost"] > 0.30
            )
            if ctx["state"] == "DANGER" and is_real_sweep:
                least_valuable, least_value = _find_least_valuable_mon(battle)
                active_value = _mon_value(active) if active else 0.0
                switch_value = _mon_value(pokemon)

                # If this is the least valuable mon, bonus for sacrificing it
                if least_valuable and pokemon.species == least_valuable.species:
                    ctx_adj += 0.15  # Bonus: good sacrifice choice
                # If this is a high-value mon and active is low-value, penalty
                # (don't waste the good mon to save the bad one)
                elif active is not None and switch_value > active_value * 1.5:
                    ctx_adj -= 0.15  # Penalty: wasting a good mon

            # Sacrifice cycle prevention: heavy penalty for switching INTO a KO.
            # If switch target gets OHKO'd by predicted opp action, this is throwing
            # the mon away. Better to stay and extract value with active.
            if our_after <= 0.0:
                ctx_adj -= 0.30

        # (Removed the old "team resource advantage" term: it summed over the whole
        # bench and so was identical for every switch candidate in a turn — a flat
        # switch-vs-move bias that also double-counted team HP already reflected by
        # score_transition. It only encouraged unwarranted switching.)
        score = base_score + offensive_bonus + info_bonus + ability_bonus + ctx_adj
        reasoning = f"switch_to {pokemon.species}: hazard_dmg={hazard:.3f}, opp_dmg={opp_damage:.3f}, value={_mon_value(pokemon):.3f}, ability_bonus={ability_bonus:.3f}"
        return _EvalResult(
            score,
            damage_taken=opp_damage + hazard,
            expected_hp_after=our_after,
            move_category="switch",
            reasoning=reasoning,
        )

    def _max_bench_threat(self, battle, our_pokemon, type_chart) -> float:
        """Max damage opp's revealed bench mons can do to our switch-in.

        Used to assess whether opp could pivot to punish our switch.
        """
        opp_team = battle.opponent_team or {}
        active = battle.opponent_active_pokemon
        best = 0.0
        for opp_mon in opp_team.values():
            if opp_mon is None or opp_mon.fainted:
                continue
            if active is not None and opp_mon.species == active.species:
                continue
            threat = _max_threat_via_movepool(opp_mon, our_pokemon, type_chart, tracker=self._opp_tracker)
            best = max(best, threat)
        return best

    def _cached_opp_damage(self, opp, our_pokemon, type_chart) -> float:
        """Memoized opponent damage fraction lookup.

        Uses sets DB to fill in unrevealed moves so we correctly account for
        coverage moves opp hasn't shown yet (e.g., a Sinistcha with unseen
        Shadow Ball that would hit our Psychic switch-in for SE).
        """
        if not opp or not our_pokemon:
            return 0.0
        # Cache key uses species (stable across switch-in/out) — id() can be reused.
        key = (
            getattr(opp, "species", None) or id(opp),
            getattr(our_pokemon, "species", None) or id(our_pokemon),
        )
        if key not in self._opp_power_cache:
            # Use revealed moves first, fall back to movepool for unrevealed slots
            best_revealed = _max_opp_damage_fraction(opp, our_pokemon, type_chart)
            best_with_pool = _max_threat_via_movepool(opp, our_pokemon, type_chart, tracker=self._opp_tracker)
            self._opp_power_cache[key] = max(best_revealed, best_with_pool)
        return self._opp_power_cache[key]

    def _projected_value(self, battle, our_mon, our_hp, opp_mon, opp_hp, type_chart) -> float:
        """Depth-1 value of a PROJECTED position: our_mon (at our_hp) facing
        opp_mon (at opp_hp), assuming we play our best damaging move and M3 plays
        max-damage. Used as the next-ply estimate for 2-ply lookahead. M3 is
        near-deterministic so a single projected exchange is a good continuation.
        """
        if our_mon is None or opp_mon is None:
            return 0.0
        our_dmg = _best_our_damage_with_item(our_mon, opp_mon, type_chart)
        opp_dmg = _max_threat_via_movepool(opp_mon, our_mon, type_chart, tracker=self._opp_tracker)
        our_spe = _effective_speed(our_mon, use_actual=True)
        opp_spe = _effective_speed(opp_mon, use_actual=False)
        we_first = our_spe <= opp_spe if _trick_room_active(battle) else our_spe >= opp_spe
        if we_first:
            opp_after = max(0.0, opp_hp - our_dmg)
            our_after = max(0.0, our_hp - (opp_dmg if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_hp - opp_dmg)
            opp_after = max(0.0, opp_hp - (our_dmg if our_after > 0.0 else 0.0))
        val = self._value.score_transition(battle, our_after, opp_after)
        if opp_after <= 0.0:
            val += 0.15
        if our_after <= 0.0:
            val -= 0.10
        return val

    def _lookahead_term(self, battle, attacker, our_after, defender, opp_after, type_chart) -> float:
        """2-ply continuation value for an attacking move that leaves us at
        our_after HP and the opponent at opp_after HP. Models what happens NEXT:
          - opp fainted  → M3 sends in its best matchup mon; do we survive/threaten it?
          - both survive → the next exchange vs the same (damaged) opponent.
          - we fainted   → we bring in our best switch-in to face the opponent.
        Returns the discounted projected value (0 when lookahead disabled)."""
        if _LOOKAHEAD <= 0.0 or attacker is None or defender is None:
            return 0.0
        if opp_after <= 0.0:
            if our_after <= 0.0:
                return 0.0  # mutual KO — even trade, neutral continuation
            send_in = _predict_opp_switch_in(battle, attacker, type_chart, tracker=self._opp_tracker)
            if send_in is None:
                return 0.0  # opp has no bench left → we're cleaning up, no penalty
            cont = self._projected_value(
                battle, attacker, our_after, send_in,
                send_in.current_hp_fraction if send_in.current_hp_fraction else 1.0, type_chart)
            return _LOOKAHEAD * cont
        if our_after > 0.0:
            cont = self._projected_value(battle, attacker, our_after, defender, opp_after, type_chart)
            return _LOOKAHEAD * cont
        # our active faints, opp survives → our best switch-in faces the opponent
        if battle.available_switches:
            sw = _best_forced_switch(battle, type_chart, tracker=self._opp_tracker)
            cont = self._projected_value(battle, sw, sw.current_hp_fraction, defender, opp_after, type_chart)
            return _LOOKAHEAD * cont
        return 0.0


def _move_power(move, attacker, defender, type_chart) -> float:
    bp = move.base_power or 0
    if bp <= 0:
        return 0.0
    stab = 1.5 if (attacker and move.type in attacker.types) else 1.0
    eff = (
        move.type.damage_multiplier(
            defender.type_1, defender.type_2, type_chart=type_chart
        )
        if defender
        else 1.0
    )
    acc = _accuracy(move)
    return bp * stab * eff * acc


def _opp_power_vs(opp, our_pokemon, type_chart) -> float:
    """Opponent's max damage move against our_pokemon.

    Uses revealed moves with accuracy factored in. Falls back to 80 BP STAB
    for unrevealed movesets. Returns 0 for immunities, honest values for resists.
    """
    if opp is None or our_pokemon is None:
        return 0.0

    best = 0.0
    for move in opp.moves.values():
        bp = move.base_power or 0
        if bp <= 0:
            continue
        stab = 1.5 if move.type in opp.types else 1.0
        eff = move.type.damage_multiplier(
            our_pokemon.type_1, our_pokemon.type_2, type_chart=type_chart
        )
        acc = _accuracy(move)
        best = max(best, bp * stab * eff * acc)

    if best == 0.0:
        for opp_type in (opp.type_1, opp.type_2):
            if opp_type is None:
                continue
            eff = opp_type.damage_multiplier(
                our_pokemon.type_1, our_pokemon.type_2, type_chart=type_chart
            )
            best = max(best, 80.0 * 1.5 * eff)

    return best


def _we_go_first(move, attacker, defender, battle=None) -> bool:
    if move.priority > 0:
        return True
    if move.priority < 0:
        return False
    our_speed = _effective_speed(attacker, use_actual=True)
    opp_speed = _effective_speed(defender, use_actual=False)
    # Trick Room reverses turn order at priority 0
    if battle is not None and _trick_room_active(battle):
        return our_speed <= opp_speed
    return our_speed >= opp_speed


def _trick_room_active(battle) -> bool:
    try:
        from poke_env.battle.field import Field
        return Field.TRICK_ROOM in (battle.fields or {})
    except Exception:
        return False


def _effective_speed(pokemon, use_actual: bool) -> float:
    if pokemon is None:
        return 100.0
    # Always compute the level-based estimate as a sanity floor — random battles
    # use max-EV speed for any mon expected to be fast (96+ base spe runs 252).
    # Without this floor, poke_env's reported pokemon.stats can be 0/None for
    # newly-revealed mons, making us think we're slower than we actually are.
    base_spe = (pokemon.base_stats or {}).get("spe") or 100
    level = getattr(pokemon, "level", None) or 80
    estimated = _estimate_actual_speed(base_spe, level)
    if use_actual and pokemon.stats and pokemon.stats.get("spe"):
        # Use the larger of actual stat vs estimate. For our mon, actual is
        # usually correct, but if it's missing/zero we shouldn't assume we're slow.
        base = max(pokemon.stats["spe"], estimated)
    else:
        base = estimated
    speed = base * _stage_to_multiplier((pokemon.boosts or {}).get("spe", 0))
    # Paralysis: 50% Speed in Gen 9 (was 25% pre-Gen 7).
    try:
        from poke_env.battle.status import Status
        if getattr(pokemon, "status", None) == Status.PAR:
            speed *= 0.5
    except Exception:
        pass
    return speed


def _estimate_actual_speed(base_stat: int, level: int) -> float:
    """Rough max-EV/IV actual stat approximation.

    31 IV + EV term (_SPE_IV_EV; 94≈252 EV, 52≈85 EV randbat default), neutral
    nature: ((2*base + _SPE_IV_EV) * level) / 100 + 5.
    Good enough for speed comparisons in random battles where we don't know
    the opponent's exact EV spread.
    """
    return ((2 * base_stat + _SPE_IV_EV) * level) / 100.0 + 5.0


def _hazard_damage(pokemon, side_conditions, type_chart) -> float:
    """HP fraction lost switching into hazards on our side.

    Covers Stealth Rock, Spikes, Toxic Spikes (passive poison), Sticky Web (speed drop).
    Heavy-Duty Boots and Magic Guard ignore all.
    """
    if not side_conditions:
        return 0.0

    item = _norm(getattr(pokemon, "item", None))
    ability = _norm(getattr(pokemon, "ability", None))
    if item == "heavydutyboots" or ability == "magicguard":
        return 0.0

    sr_key = _match_condition(side_conditions, "stealthrock")
    spikes_key = _match_condition(side_conditions, "spikes")
    tspikes_key = _match_condition(side_conditions, "toxicspikes")
    sticky_key = _match_condition(side_conditions, "stickyweb")

    damage = 0.0

    if sr_key is not None:
        damage += _SR_BASE * _rock_effectiveness(pokemon, type_chart)

    if spikes_key is not None and _grounded(pokemon):
        layers = side_conditions[spikes_key] or 1
        damage += _SPIKES_DAMAGE.get(layers, _SPIKES_DAMAGE[3])

    if tspikes_key is not None:
        type_1 = getattr(pokemon.type_1, "name", str(pokemon.type_1)).lower() if pokemon.type_1 else ""
        type_2 = getattr(pokemon.type_2, "name", str(pokemon.type_2)).lower() if pokemon.type_2 else ""
        is_poison = type_1 == "poison" or type_2 == "poison"
        is_steel = type_1 == "steel" or type_2 == "steel"
        if not is_poison and not is_steel:
            layers = side_conditions[tspikes_key] or 1
            damage += 0.125 if layers == 1 else 0.25

    return min(damage, 1.0)


def _norm(value) -> str:
    return (value or "").lower().replace(" ", "").replace("-", "")


def _match_condition(side_conditions, name: str):
    for key in side_conditions:
        label = getattr(key, "name", str(key)).lower().replace("_", "")
        if label == name:
            return key
    return None


def _info_deficit(battle) -> float:
    """Return how little we know about opp's team, from 1.0 (nothing) to 0.0 (all revealed).

    Used to encourage reserved play early game: M3 switches aggressively to counter
    what we reveal, so taking big risks before we know their team is dangerous.
    """
    opp_team = battle.opponent_team or {}
    revealed = len(opp_team)
    return max(0.0, (6 - revealed) / 6.0)


def _estimate_opp_switch_probability(opp_damage_to_us: float, our_best_damage: float,
                                      info_deficit: float) -> float:
    """Estimate probability M3 switches this turn given the matchup.

    M3's actual logic: switch only if `switch_score > best_move_score * 1.5`,
    where score = base_power * STAB * effectiveness. So M3 only switches when
    something on the bench is DRAMATICALLY better — usually only on full
    immunities (Ground vs Electric, Flying vs Ground, etc.).

    Returns 0.0 (stays) to ~0.85 (definitely swaps).
    """
    # Strong signal: we're effectively immune. M3 will almost certainly swap.
    if opp_damage_to_us <= 0.03:
        return 0.75

    # CRITICAL: If opponent can OHKO us, they will NEVER switch.
    # They have a winning position so they'll stay and attack.
    if opp_damage_to_us >= 1.0:
        return 0.0

    # Otherwise M3 stays in — its switch threshold is too strict.
    return 0.0


def _predict_opp_switch_in(battle, our_active, type_chart, tracker=None):
    """Predict which Pokemon opp would switch to, given M3's heuristic.

    M3 picks the bench mon with max (offense - defense_penalty) vs our active.
    We mirror that calculation across opp's revealed team to find the most
    likely switch target. Returns None if no revealed bench is available.

    Uses sets DB to fill in unrevealed moves so we can estimate offense even
    when the bench mon hasn't shown moves yet.
    """
    if not our_active:
        return None
    opp_team = battle.opponent_team or {}
    if not opp_team:
        return None

    active = battle.opponent_active_pokemon
    best = None
    best_score = float("-inf")
    for opp_mon in opp_team.values():
        if opp_mon is None or opp_mon.fainted:
            continue
        # Skip the active Pokemon itself
        if active is not None and opp_mon.species == active.species:
            continue

        # Estimate offense: max damage opp_mon can do to our active
        offense = _max_threat_via_movepool(opp_mon, our_active, type_chart, tracker=tracker)

        # Defense penalty: how much our active threatens opp_mon
        defense_penalty = 0.0
        for atk_type in our_active.types:
            if atk_type is None:
                continue
            eff = atk_type.damage_multiplier(
                opp_mon.type_1, opp_mon.type_2, type_chart=type_chart
            )
            defense_penalty = max(defense_penalty, eff)

        # M3-style score: offense - 0.4 * defense_penalty (normalized)
        score = offense - 0.4 * defense_penalty

        # Historical pattern bonus: if opp has repeatedly pivoted this mon in
        # against our active species, weight it above pure matchup math.
        if tracker is not None and our_active is not None:
            history_w = tracker.get_switch_in_weight(
                _norm(our_active.species), _norm(opp_mon.species)
            )
            if history_w > 0:
                score += history_w * 0.8

        if score > best_score:
            best_score = score
            best = opp_mon

    return best


# Average attacking stats for an unknown gen9 randbat Pokemon
# (computed from sets.json: 507 species)
_AVG_ATK = 96
_AVG_SPA = 88


def _unknown_mon_threat(our_pokemon) -> float:
    """Estimate damage from an unknown opp mon against our active Pokemon.

    Uses an 80 BP neutral hit with average gen9 metagame attacking stats,
    100% accuracy, unboosted, no STAB. Returns the higher of physical/special.

    Used to assess threat level of unrevealed slots on opp's team — when we're
    deciding whether to commit to a matchup, we should consider "any of their
    5 unknown mons could come in and hit me with this baseline."
    """
    if our_pokemon is None:
        return 0.0
    level = getattr(our_pokemon, "level", None) or 80
    hp = _estimate_hp(our_pokemon)

    # Physical hit using avg atk vs our def
    D_phys = _estimate_stat(our_pokemon, "def")
    phys_dmg = ((2 * level / 5 + 2) * 80 * _AVG_ATK / D_phys) / 50 + 2

    # Special hit using avg spa vs our spd
    D_spec = _estimate_stat(our_pokemon, "spd")
    spec_dmg = ((2 * level / 5 + 2) * 80 * _AVG_SPA / D_spec) / 50 + 2

    return max(phys_dmg, spec_dmg) / hp


# ──────────────────────────────────────────────────────────────────────────
# Strategic prediction layer
#
# These helpers aggregate information about the opponent's likely actions
# and damage potential, exploiting M3's predictable behavior:
#   - M3 picks max-damage move OR switches if a bench mon does ≥1.5× more
#   - No setup, no recovery, no hazards
# ──────────────────────────────────────────────────────────────────────────


def _compute_opp_max_threat(battle, our_pokemon, type_chart, tracker=None):
    """Aggregate max damage opp can deal to our_pokemon across their entire team.

    Considers:
      - All revealed opp mons (active + bench), using revealed moves + movepool
      - Unknown mons (synthetic 80 BP baseline)

    Returns dict:
      - max_damage: float (fraction of our HP)
      - source: species name or "unknown"
      - active_threat: damage from currently-active opp mon
      - bench_threat: max damage from any revealed bench mon
      - unknown_threat: synthetic baseline (0 if all 6 revealed)
    """
    if our_pokemon is None:
        return {"max_damage": 0.0, "source": None, "active_threat": 0.0,
                "bench_threat": 0.0, "unknown_threat": 0.0}

    opp_team = battle.opponent_team or {}
    active = battle.opponent_active_pokemon

    # Active mon threat
    active_threat = 0.0
    active_species = None
    if active is not None and not active.fainted:
        active_threat = _max_threat_via_movepool(active, our_pokemon, type_chart, tracker=tracker)
        active_species = active.species

    # Bench threats (revealed but not active)
    bench_threat = 0.0
    bench_species = None
    for opp_mon in opp_team.values():
        if opp_mon is None or opp_mon.fainted:
            continue
        if active is not None and opp_mon.species == active.species:
            continue
        threat = _max_threat_via_movepool(opp_mon, our_pokemon, type_chart, tracker=tracker)
        if threat > bench_threat:
            bench_threat = threat
            bench_species = opp_mon.species

    # Unknown mon synthetic threat (only if not all 6 revealed)
    unknown_threat = 0.0
    n_revealed = sum(1 for m in opp_team.values() if m is not None)
    if n_revealed < 6:
        unknown_threat = _unknown_mon_threat(our_pokemon)

    # Pick worst case across all sources
    candidates = [
        (active_threat, active_species),
        (bench_threat, bench_species),
        (unknown_threat, "unknown" if unknown_threat > 0 else None),
    ]
    max_damage, source = max(candidates, key=lambda x: x[0])

    return {
        "max_damage": max_damage,
        "source": source,
        "active_threat": active_threat,
        "bench_threat": bench_threat,
        "unknown_threat": unknown_threat,
    }


def _predict_opp_action(battle, our_pokemon, type_chart, tracker=None):
    """Predict M3-style opponent's action this turn.

    M3's logic (from heuristic.py):
      - matchup_score = max_BP_offense - max_BP_defense_threat
      - switch if best_bench.matchup > active.matchup * 1.5

    Returns dict:
      - action: "attack" or "switch"
      - target: species (if switch) or None
      - expected_damage: best damage they'll deal to our_pokemon
    """
    active = battle.opponent_active_pokemon
    if active is None or active.fainted:
        # Forced switch (active fainted)
        target = _predict_opp_switch_in(battle, our_pokemon, type_chart, tracker=tracker)
        target_species = target.species if target else None
        target_damage = _max_threat_via_movepool(target, our_pokemon, type_chart, tracker=tracker) if target else 0.0
        return {"action": "switch", "target": target_species, "expected_damage": target_damage}

    active_damage = _max_threat_via_movepool(active, our_pokemon, type_chart, tracker=tracker)

    # CRITICAL: Check if opponent has a significantly better threat on bench.
    # Opponent should switch if any bench mon does more damage than active.
    # This is pure max-damage optimization on the opponent's side.
    opp_team = battle.opponent_team or {}
    best_bench_damage = 0.0
    best_bench_mon = None
    for opp_mon in opp_team.values():
        if opp_mon is None or opp_mon.fainted:
            continue
        if active is not None and opp_mon.species == active.species:
            continue
        threat = _max_threat_via_movepool(opp_mon, our_pokemon, type_chart, tracker=tracker)
        if threat > best_bench_damage:
            best_bench_damage = threat
            best_bench_mon = opp_mon

    # If bench threat > active threat, opponent switches to maximize damage
    if best_bench_damage > active_damage and best_bench_mon is not None:
        return {"action": "switch", "target": best_bench_mon.species, "expected_damage": best_bench_damage}

    # Use existing M3 switch probability to decide stay vs switch (for marginal cases)
    info_deficit = _info_deficit(battle)
    our_best = 0.0  # We don't need exact, just check switch-prob threshold
    switch_prob = _estimate_opp_switch_probability(active_damage, our_best, info_deficit)

    if switch_prob >= 0.5:
        target = _predict_opp_switch_in(battle, our_pokemon, type_chart, tracker=tracker)
        if target is not None:
            target_damage = _max_threat_via_movepool(target, our_pokemon, type_chart, tracker=tracker)
            return {"action": "switch", "target": target.species, "expected_damage": target_damage}

    return {"action": "attack", "target": None, "expected_damage": active_damage}


# Strategic state thresholds (fraction of our HP opp can deal in a turn)
_THREAT_SAFE = 0.33    # below this: we can setup/attack freely
_THREAT_DANGER = 0.50  # above this: we should consider defensive play


def _strategic_context(battle, our_pokemon, type_chart, tracker=None):
    """Classify the current matchup state and predict opp behavior.

    Returns dict:
      - state: "SAFE" / "TRADEOFF" / "DANGER"
      - opp_max_damage: max damage opp can deal across their team
      - opp_will_switch: bool — is opp likely to switch this turn?
      - threat_breakdown: dict from _compute_opp_max_threat
      - predicted_action: dict from _predict_opp_action
    """
    threat = _compute_opp_max_threat(battle, our_pokemon, type_chart, tracker=tracker)
    action = _predict_opp_action(battle, our_pokemon, type_chart, tracker=tracker)

    if threat["max_damage"] < _THREAT_SAFE:
        state = "SAFE"
    elif threat["max_damage"] < _THREAT_DANGER:
        state = "TRADEOFF"
    else:
        state = "DANGER"

    return {
        "state": state,
        "opp_max_damage": threat["max_damage"],
        "opp_will_switch": action["action"] == "switch",
        "threat_breakdown": threat,
        "predicted_action": action,
    }


def _max_threat_via_movepool(opp_mon, our_pokemon, type_chart, tracker=None) -> float:
    """Estimate opp_mon's max damage to us, using sets DB for unrevealed moves.

    Uses revealed moves first; if fewer than 4 are revealed, fills in from
    the species' randbat movepool (we don't know their exact 4, but we know
    the pool of possibilities).

    If a tracker is provided, uses the pruned movepool (filtered by observations)
    instead of the full sets DB. This narrows predictions as the battle progresses.
    """
    from poke_env.battle.move import Move
    from bot.data.sets_db import get_movepool

    if opp_mon is None or our_pokemon is None:
        return 0.0

    revealed = {m.id for m in opp_mon.moves.values()}
    best = 0.0

    # Apply opp's current offensive boosts/drops. Critical for moves like
    # Draco Meteor / Overheat / Leaf Storm that self-drop SpA: the next turn,
    # all the opponent's special moves are at -2 SpA and hit far less.
    opp_boosts = opp_mon.boosts or {}

    # Get possible items to apply correct damage multiplier. Conservative: pick
    # the highest plausible multiplier per move category (physical/special).
    # Choice Band/Specs = 1.5x for the matching category; Life Orb = 1.3x for both.
    from bot.data.sets_db import get_items
    possible_items = get_items(opp_mon.species)

    def _item_mult(is_phys: bool) -> float:
        if is_phys and "choiceband" in possible_items:
            return 1.5
        if (not is_phys) and "choicespecs" in possible_items:
            return 1.5
        if "lifeorb" in possible_items:
            return 1.3
        return 1.0

    # Revealed damaging moves
    for m in opp_mon.moves.values():
        if (m.base_power or 0) > 0:
            boost = opp_boosts.get("atk" if _is_physical_move(m) else "spa", 0)
            d = _damage_fraction(m, opp_mon, our_pokemon, type_chart, atk_boost=boost)
            d *= _item_mult(_is_physical_move(m))
            best = max(best, d)

    # Fill in unknown slots from movepool. Prefer tracker's pruned pool if available.
    if len(revealed) < 4:
        if tracker is not None:
            movepool = tracker.get_likely_moves(opp_mon.species)
            if not movepool:  # Tracker may return empty if all sets pruned
                movepool = get_movepool(opp_mon.species)
        else:
            movepool = get_movepool(opp_mon.species)
        for move_id in movepool:
            if move_id in revealed:
                continue
            try:
                m = Move(move_id, gen=9)
            except Exception:
                continue
            if (m.base_power or 0) <= 0:
                continue
            try:
                boost = opp_boosts.get("atk" if _is_physical_move(m) else "spa", 0)
                d = _damage_fraction(m, opp_mon, our_pokemon, type_chart, atk_boost=boost)
                d *= _item_mult(_is_physical_move(m))
                d *= _POOL_DISC  # discount: this move is a guess, not revealed
                best = max(best, d)
            except Exception:
                continue

    return best


def _is_defensive_role(pokemon) -> bool:
    """Heuristic: Pokemon is a defensive pivot rather than an attacker.

    A defensive mon's bulk (HP+Def+SpD) significantly exceeds its best
    offensive stat. Mandibuzz, Toxapex, Ferrothorn → True. Garchomp,
    Dragapult, Cinderace → False.
    """
    if pokemon is None:
        return False
    base = pokemon.base_stats or {}
    atk = base.get("atk") or 100
    spa = base.get("spa") or 100
    hp = base.get("hp") or 100
    defs = base.get("def") or 100
    spd = base.get("spd") or 100
    offensive_max = max(atk, spa)
    bulk_total = hp + defs + spd
    # Defensive if total bulk > 2.5x best offensive stat
    return bulk_total > offensive_max * 2.5


def _pokemon_type_names(pokemon) -> set:
    """Return uppercase type names for a Pokemon (e.g. {'FIRE', 'FLYING'})."""
    if pokemon is None:
        return set()
    names = set()
    for t in (pokemon.type_1, pokemon.type_2):
        if t is not None:
            names.add(getattr(t, "name", str(t)).upper())
    return names


def _rock_effectiveness(pokemon, type_chart) -> float:
    row = type_chart.get("ROCK") or {}
    mult = 1.0
    for t in (pokemon.type_1, pokemon.type_2):
        if t is None:
            continue
        mult *= row.get(getattr(t, "name", str(t)).upper(), 1.0)
    return mult


def _grounded(pokemon) -> bool:
    for t in (pokemon.type_1, pokemon.type_2):
        if t is not None and getattr(t, "name", str(t)).upper() == "FLYING":
            return False
    if _norm(getattr(pokemon, "ability", None)) in ("levitate", "magnetrise"):
        return False
    if _norm(getattr(pokemon, "item", None)) == "airballoon":
        return False
    return True


def _best_forced_switch(battle, type_chart, tracker=None):
    """Pick best switch-in after fainting, accounting for hazards.

    Uses _max_threat_via_movepool (not just revealed moves) so we account for
    unrevealed coverage moves and Choice Band/Specs/Life Orb item multipliers.
    Without this, we'd pick switch-ins that look safe by revealed-data alone
    and routinely get OHKO'd by an unrevealed coverage move.
    """
    opp = battle.opponent_active_pokemon

    def score(p):
        hazard = _hazard_damage(p, battle.side_conditions, type_chart)
        threat = _max_threat_via_movepool(opp, p, type_chart, tracker=tracker)
        # Also consider type matchup: penalize switching into something the
        # opp's type is super-effective against (mirrors _eval_switch's gate).
        type_penalty = 0.0
        if opp is not None:
            for opp_type in [opp.type_1, opp.type_2]:
                if opp_type:
                    mult = opp_type.damage_multiplier(p.type_1, p.type_2, type_chart=type_chart)
                    if mult >= 2.0:
                        type_penalty = 1.0  # Hard penalty: don't pick a 2x weak mon if avoidable
                        break
        # Offense matters too: a mon that merely SURVIVES but can't threaten the
        # opponent loses the 1v1 by attrition. Reward switch-ins that can hit back
        # (super-effective STAB, or faster + can KO). Reuses _switch_offensive_bonus.
        offense = _switch_offensive_bonus(p, opp, type_chart) if opp is not None else 0.0
        return p.current_hp_fraction - hazard - threat - type_penalty + _FSWITCH_OFF * offense

    return max(battle.available_switches, key=score)


def _accuracy(move) -> float:
    val = move.accuracy
    if val is True or val is None:
        return 1.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    return float(val)


def _is_physical_move(move) -> bool:
    """Check if move is physical category. False for special/status."""
    cat = getattr(move, "category", None)
    if cat is None:
        return False
    name = getattr(cat, "name", str(cat)).lower()
    return "physical" in name


def _estimate_hp(pokemon) -> int:
    """Estimate max HP using Gen 9 random battle formula (85 EV, 31 IV)."""
    if pokemon is None:
        return 300
    if pokemon.stats and pokemon.stats.get("hp"):
        return pokemon.stats["hp"]
    base_hp = (pokemon.base_stats or {}).get("hp") or 100
    level = getattr(pokemon, "level", None) or 80
    return int((2 * base_hp + 52) * level / 100) + level + 10


def _estimate_stat(pokemon, stat_name: str) -> int:
    """Estimate a stat using Gen 9 random battle formula (85 EV, 31 IV, neutral nature).

    Handles edge cases: if no physical moves, Atk EV/IV = 0.
    If Trick Room or Gyro Ball, Speed EV/IV = 0.
    """
    if pokemon is None:
        return 100
    if pokemon.stats and pokemon.stats.get(stat_name):
        return pokemon.stats[stat_name]

    base = (pokemon.base_stats or {}).get(stat_name) or 100
    level = getattr(pokemon, "level", None) or 80

    if stat_name == "atk" and pokemon.moves:
        has_physical = any(_is_physical_move(m) and (m.base_power or 0) > 0 for m in pokemon.moves.values())
        if not has_physical:
            return int(2 * base * level / 100) + 5

    if stat_name == "spe" and pokemon.moves:
        for m in pokemon.moves.values():
            mid = _norm(m.id)
            if mid in ("trickroom", "gyroball"):
                return int(2 * base * level / 100) + 5

    return int((2 * base + 52) * level / 100) + 5


def _ability_status_multiplier(attacker, is_physical: bool, move_id: str = "") -> float:
    """Multiplier on attacker's offensive stat from ability + status interactions.

    - Guts + (BRN/PAR/PSN/TOX): Atk × 1.5, ignores burn Atk halving
    - Toxic Boost + (PSN/TOX): physical Atk × 1.5
    - Flare Boost + BRN: special SpA × 1.5
    - Burned physical attacker (no Guts, not Facade): Atk × 0.5
    """
    if attacker is None:
        return 1.0
    ability = (getattr(attacker, "ability", "") or "").lower().replace(" ", "").replace("-", "")
    status = getattr(attacker, "status", None)
    status_name = getattr(status, "name", "") if status else ""

    is_burned = status_name == "BRN"
    is_poisoned = status_name in ("PSN", "TOX")
    is_paralyzed = status_name == "PAR"
    has_status = is_burned or is_poisoned or is_paralyzed

    mult = 1.0

    # Status-loving abilities
    if ability == "guts" and has_status:
        mult *= 1.5
    elif ability == "toxicboost" and is_poisoned and is_physical:
        mult *= 1.5
    elif ability == "flareboost" and is_burned and not is_physical:
        mult *= 1.5
    # Burn penalty for physical attackers without Guts (Facade ignores it too)
    elif is_burned and is_physical and move_id != "facade":
        mult *= 0.5

    return mult


def _damage_fraction(move, attacker, defender, type_chart, atk_boost: int = 0, battle=None) -> float:
    """Estimate damage as fraction of defender's HP using real Gen 9 formula.

    atk_boost: stage count to apply to attacker's attack stat (for setup rollouts
    where we're projecting future state). Defender's current defensive boost
    is read automatically from defender.boosts. Attacker's ability + status
    interactions (Guts, burn penalty, Toxic Boost, Flare Boost) are applied
    automatically.

    battle: when provided (and PS_CONTEXT enabled), weather/terrain/screen
    modifiers are applied. Defaults to None for callers that don't have it.

    Damage roll: returns the AVERAGE-roll expected damage (×0.925) by default so
    projected HP is honest; PS_ROLL="max" reproduces the old 100%-roll value.
    Multi-hit moves are scaled by expected hits; fixed-damage moves (Seismic
    Toss/Night Shade/Super Fang) are handled explicitly.

    Critical hits: ignores base 6.25% crit rate (random anomaly). Only accounts
    for high-crit moves (12.5%+) or guaranteed crits.

    Returns fraction in [0, 1+] (may exceed 1 for OHKOs).
    """
    if attacker is None or defender is None:
        return 0.0

    level = getattr(attacker, "level", None) or 80
    is_physical = _is_physical_move(move)
    move_id = _norm(getattr(move, "id", ""))

    # Fixed-damage moves: base_power is 0 in the data but they still deal damage.
    # They respect type immunity (Fighting Seismic Toss misses Ghost; Ghost Night
    # Shade misses Normal). Super Fang deals 50% of the target's CURRENT HP.
    fixed = getattr(move, "damage", None)
    if fixed or move_id == "superfang":
        eff_im = move.type.damage_multiplier(
            defender.type_1, defender.type_2, type_chart=type_chart
        )
        if eff_im == 0:
            return 0.0
        acc = _accuracy(move)
        if move_id == "superfang":
            return 0.5 * (defender.current_hp_fraction or 1.0) * acc
        hp = _estimate_hp(defender)
        if fixed == "level":
            return (level / hp) * acc
        if isinstance(fixed, (int, float)):
            return (float(fixed) / hp) * acc

    bp = move.base_power or 0
    if bp <= 0:
        return 0.0

    atk_name = "atk" if is_physical else "spa"
    def_name = "def" if is_physical else "spd"

    A = _estimate_stat(attacker, atk_name)
    D = _estimate_stat(defender, def_name)
    hp = _estimate_hp(defender)

    if atk_boost != 0:
        A = int(A * _stage_to_multiplier(atk_boost))

    # Apply attacker's ability + status interactions (Guts boost, burn penalty,
    # Toxic Boost, Flare Boost). Critical for Conkeldurr-Guts-burned dealing
    # 1.5× damage instead of 0.5× (and Dialga's Draco Meteor SpA drop is
    # already handled via atk_boost, applied by callers).
    ability_mult = _ability_status_multiplier(attacker, is_physical, _norm(getattr(move, "id", "")))
    if ability_mult != 1.0:
        A = max(1, int(A * ability_mult))

    # Apply defender's current defensive boost/drop. Critical for cases like
    # Shell Smash (-1 Def/SpD) where the user becomes more vulnerable, or
    # Iron Defense / Calm Mind / Cosmic Power where they become tankier.
    def_boost = (defender.boosts or {}).get(def_name, 0)
    if def_boost != 0:
        D = max(1, int(D * _stage_to_multiplier(def_boost)))

    stab = 1.5 if move.type in attacker.types else 1.0
    eff = move.type.damage_multiplier(defender.type_1, defender.type_2, type_chart=type_chart)
    acc = _accuracy(move)

    base_damage = ((2 * level / 5 + 2) * bp * A / D) / 50 + 2

    # High-crit rate handling, as an EXPECTED-VALUE multiplier (not a flat 1.5x,
    # which overvalued high-crit moves by ~41%). A crit deals 1.5x, so EV uplift =
    # 1 + 0.5 * P(crit). Elevated-crit moves (~12.5%) → ~1.0625x; near-guaranteed
    # high-crit tiers → ~1.125x.
    crit_mult = 1.0
    crit_rate = getattr(move, "crit_ratio", 0) or 0
    if crit_rate >= 3:
        crit_mult = 1.125
    elif crit_rate >= 2:
        crit_mult = 1.0625

    # Ability interactions: immunity, healing, damage reduction
    # E.g., Water Absorb on water moves = 0 damage + heal
    # E.g., Fluffy halves contact moves (needs full move object)
    ability_mult, heals = _check_ability_matchup(
        defender, move.type, type_eff=eff, move=move
    )

    if heals:
        # Defender heals: effectively 0 damage (actually benefits them)
        return 0.0

    damage = base_damage * stab * eff * acc * crit_mult * ability_mult / hp

    # Multi-hit moves (Bullet Seed, Icicle Spear, Population Bomb, ...): base_power
    # is per-hit, so scale by the expected number of hits (poke-env exposes this).
    if _MULTIHIT:
        hits = getattr(move, "expected_hits", 1) or 1
        if hits != 1:
            damage *= hits

    # Weather / terrain / screen modifiers (only when battle context is supplied).
    if _CONTEXT and battle is not None:
        damage *= _context_damage_mult(move, attacker, defender, battle, is_physical, eff)

    # Average damage roll → honest expected damage. "max" keeps the old 100% roll.
    if _ROLL_MODE == "avg":
        damage *= _AVG_ROLL

    return damage


def _ko_probability(on_hit_avg_frac: float, target_hp_frac: float) -> float:
    """P(KO | the move hits), scanning the 16 uniform damage rolls (0.85..1.00).

    on_hit_avg_frac: average-roll damage as a fraction of the target's MAX HP
        (i.e. _damage_fraction output with the accuracy factor divided back out).
    target_hp_frac: the target's CURRENT remaining HP fraction.

    Returns 1.0 for a guaranteed KO (even the min roll kills), down to 0.0.
    """
    if on_hit_avg_frac <= 0.0 or target_hp_frac <= 0.0:
        return 0.0
    max_roll = on_hit_avg_frac / _AVG_ROLL  # damage at the 1.00 roll
    kos = sum(1 for i in range(16) if max_roll * (0.85 + i * 0.01) >= target_hp_frac)
    return kos / 16.0


def _has_type(mon, type_name_upper: str) -> bool:
    if not mon:
        return False
    for t in (mon.type_1, mon.type_2):
        if t is not None and getattr(t, "name", str(t)).upper() == type_name_upper:
            return True
    return False


def _context_damage_mult(move, attacker, defender, battle, is_physical: bool, type_eff: float) -> float:
    """Weather / terrain / screen damage multiplier for the current field state."""
    mult = 1.0
    mtype = getattr(move.type, "name", str(move.type)).upper()
    move_id = _norm(getattr(move, "id", ""))

    # --- Weather ---
    try:
        from poke_env.battle.weather import Weather
        weather = set((battle.weather or {}).keys())
    except Exception:
        weather = set()
    if weather:
        if Weather.SUNNYDAY in weather or Weather.DESOLATELAND in weather:
            if mtype == "FIRE":
                mult *= 1.5
            elif mtype == "WATER":
                mult *= 0.5
        if Weather.RAINDANCE in weather or Weather.PRIMORDIALSEA in weather:
            if mtype == "WATER":
                mult *= 1.5
            elif mtype == "FIRE":
                mult *= 0.5
        # Sandstorm: Rock-types get +50% SpD (special damage to them ×0.667).
        if Weather.SANDSTORM in weather and not is_physical and _has_type(defender, "ROCK"):
            mult *= 1.0 / 1.5
        # Snow: Ice-types get +50% Def (physical damage to them ×0.667).
        if Weather.SNOWSCAPE in weather and is_physical and _has_type(defender, "ICE"):
            mult *= 1.0 / 1.5

    # --- Terrain ---
    try:
        from poke_env.battle.field import Field
        fields = set((battle.fields or {}).keys())
    except Exception:
        fields = set()
    if fields:
        if _grounded(attacker):
            if Field.ELECTRIC_TERRAIN in fields and mtype == "ELECTRIC":
                mult *= 1.3
            if Field.GRASSY_TERRAIN in fields and mtype == "GRASS":
                mult *= 1.3
            if Field.PSYCHIC_TERRAIN in fields and mtype == "PSYCHIC":
                mult *= 1.3
        if _grounded(defender):
            if Field.MISTY_TERRAIN in fields and mtype == "DRAGON":
                mult *= 0.5
            if Field.GRASSY_TERRAIN in fields and move_id in ("earthquake", "bulldoze", "magnitude"):
                mult *= 0.5

    # --- Screens (on the DEFENDER's side; singles → halve the relevant category) ---
    side = None
    try:
        if defender is battle.opponent_active_pokemon:
            side = battle.opponent_side_conditions
        elif defender is battle.active_pokemon:
            side = battle.side_conditions
        else:
            oa = battle.opponent_active_pokemon
            side = (battle.opponent_side_conditions
                    if (oa and defender.species == oa.species)
                    else battle.side_conditions)
    except Exception:
        side = None
    if side:
        try:
            from poke_env.battle.side_condition import SideCondition
            keys = set(side.keys())
            veil = SideCondition.AURORA_VEIL in keys
            if (is_physical and (SideCondition.REFLECT in keys or veil)) or \
               ((not is_physical) and (SideCondition.LIGHT_SCREEN in keys or veil)):
                mult *= 0.5
        except Exception:
            pass

    return mult


def _item_damage_mult(mon, is_physical: bool) -> float:
    """Damage multiplier from OUR mon's KNOWN held item (Choice Band/Specs, Life Orb)."""
    item = _norm(getattr(mon, "item", None)) if mon else ""
    if is_physical and item == "choiceband":
        return 1.5
    if (not is_physical) and item == "choicespecs":
        return 1.5
    if item == "lifeorb":
        return 1.3
    return 1.0


def _best_our_damage_with_item(our_mon, opp_mon, type_chart) -> float:
    """Best damage fraction our_mon can deal to opp_mon across its (known) moves,
    applying our item multiplier and current offensive boosts."""
    if not our_mon or not opp_mon:
        return 0.0
    boosts = our_mon.boosts or {}
    best = 0.0
    for m in our_mon.moves.values():
        if (m.base_power or 0) <= 0:
            continue
        is_phys = _is_physical_move(m)
        boost = boosts.get("atk" if is_phys else "spa", 0)
        d = _damage_fraction(m, our_mon, opp_mon, type_chart, atk_boost=boost) * _item_damage_mult(our_mon, is_phys)
        best = max(best, d)
    return best


def _max_opp_damage_fraction(opp, our_pokemon, type_chart) -> float:
    """Estimate opponent's best damaging move as fraction of our HP.

    Uses real damage formula. Falls back to synthetic 80 BP STAB for unrevealed movesets.
    """
    if opp is None or our_pokemon is None:
        return 0.0

    # Read opponent boosts so their Swords Dance / Nasty Plot is reflected
    opp_boosts = opp.boosts or {}

    best = 0.0
    has_moves = False
    for move in opp.moves.values():
        if (move.base_power or 0) <= 0:
            continue
        has_moves = True
        is_physical = _is_physical_move(move)
        boost = opp_boosts.get("atk" if is_physical else "spa", 0)
        damage = _damage_fraction(move, opp, our_pokemon, type_chart, atk_boost=boost)
        best = max(best, damage)

    if not has_moves:
        level = getattr(opp, "level", None) or 80
        hp = _estimate_hp(our_pokemon)
        for opp_type in (opp.type_1, opp.type_2):
            if opp_type is None:
                continue
            eff = opp_type.damage_multiplier(
                our_pokemon.type_1, our_pokemon.type_2, type_chart=type_chart
            )
            A = max(_estimate_stat(opp, "atk"), _estimate_stat(opp, "spa"))
            D = min(_estimate_stat(our_pokemon, "def"), _estimate_stat(our_pokemon, "spd"))
            base_damage = ((2 * level / 5 + 2) * 80 * A / D) / 50 + 2
            fallback = base_damage * 1.5 * eff / hp
            best = max(best, fallback)

    return best


def _setup_boost_multiplier(move, attacker) -> float:
    """Compute damage multiplier from a setup move's stat boosts.

    Applies boosts when we have relevant moves. Stages map to multipliers: 1→1.5, 2→2.0, 3→2.5.
    """
    if not move.boosts:
        return 1.0

    mult = 1.0
    boost_atk = move.boosts.get("atk", 0)
    boost_spa = move.boosts.get("spa", 0)

    has_damaging_moves = any((m.base_power or 0) > 0 for m in attacker.moves.values())
    if has_damaging_moves:
        if boost_atk > 0:
            mult *= _stage_to_multiplier(boost_atk)
        if boost_spa > 0:
            mult *= _stage_to_multiplier(boost_spa)

    return mult


def _stage_to_multiplier(stage: int) -> float:
    """Convert stat stage to multiplier (Gen 9 formula).

    Positive: (2 + stage) / 2  →  +1=1.5, +2=2.0, +3=2.5
    Negative: 2 / (2 - stage)  →  -1=0.667, -2=0.5, -3=0.4
    Clamped to ±6 (game limit).
    """
    stage = max(-6, min(6, stage))
    if stage >= 0:
        return (2 + stage) / 2.0
    return 2.0 / (2 - stage)


def _switch_offensive_bonus(pokemon, opp, type_chart) -> float:
    """Bonus for switching to a mon that threatens the opponent back.

    Considers speed — a faster switch-in that can KO is much more valuable
    than a slower one with the same firepower, since it removes the opp
    before taking another hit. Pikachu vs Oricorio is the canonical case:
    fragile but faster + super-effective STAB = clean trade.
    """
    if not opp or not pokemon:
        return 0.0

    from poke_env.battle.move import Move as PEMove
    from bot.data.sets_db import get_movepool

    revealed_ids = {m.id for m in pokemon.moves.values()}

    # Find best damaging move from switch-in's revealed moves
    best_dmg = 0.0
    has_se_stab = False
    for move in pokemon.moves.values():
        bp = move.base_power or 0
        if bp <= 0:
            continue
        stab = 1.5 if move.type in pokemon.types else 1.0
        eff = move.type.damage_multiplier(opp.type_1, opp.type_2, type_chart=type_chart)
        try:
            d = _damage_fraction(move, pokemon, opp, type_chart)
        except Exception:
            d = 0.0
        best_dmg = max(best_dmg, d)
        if eff >= 2.0 and stab == 1.5:
            has_se_stab = True

    # Fill unrevealed move slots from sets DB — mirrors _max_threat_via_movepool.
    # Discounted vs confirmed moves since it's a worst-case estimate, not guaranteed.
    if len(revealed_ids) < 4:
        for move_id in get_movepool(pokemon.species):
            if move_id in revealed_ids:
                continue
            try:
                m = PEMove(move_id, gen=9)
            except Exception:
                continue
            if (m.base_power or 0) <= 0:
                continue
            try:
                stab = 1.5 if m.type in pokemon.types else 1.0
                eff = m.type.damage_multiplier(opp.type_1, opp.type_2, type_chart=type_chart)
                d = _damage_fraction(m, pokemon, opp, type_chart) * 0.7  # discount: not confirmed
                best_dmg = max(best_dmg, d)
                if eff >= 2.0 and stab == 1.5:
                    has_se_stab = True
            except Exception:
                continue

    bonus = 0.0
    if has_se_stab:
        bonus = 0.15  # Has super-effective STAB (confirmed or likely from pool)

    # Speed check: faster switch-in that can KO is huge — opp dies before they
    # get another turn. We outspeed = first move = guaranteed damage applied.
    our_speed = _effective_speed(pokemon, use_actual=True)
    opp_speed = _effective_speed(opp, use_actual=False)
    is_faster = our_speed > opp_speed
    opp_hp = opp.current_hp_fraction if opp else 1.0

    if is_faster:
        # Faster + can KO opponent's remaining HP → very valuable
        if best_dmg >= opp_hp:
            bonus += 0.25  # Pivot KOs before getting hit
        elif best_dmg >= opp_hp * 0.5:
            bonus += 0.10  # Significant damage with speed advantage

    return bonus
