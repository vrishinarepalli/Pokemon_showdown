"""Expectimax planner for M4.

Depth-1 expectimax: for each of our legal actions (moves, switches, setup/recovery),
simulate one turn of damage exchange under a deterministic opponent model
(opponent plays max-damage), then score the resulting state with the
hand-crafted value function.

Opponent model: mirrors M3's behavior (max damage, no setup, no Tera, rare switches).
Setup and recovery moves use 2-turn rollouts to capture multi-turn strategies M3 cannot execute.

Acceptance: >=60% winrate vs HeuristicAgent over 500 games.
"""

from poke_env.data import GenData
from poke_env.player import Player

from bot.agents.debug import announce_team
from bot.value.handcrafted import HandcraftedValue


_NORM = 350.0  # move power score → HP fraction; 350 ≈ realistic damage range

# Stealth Rock damage = 1/8 * rock-type effectiveness against switch-in.
_SR_BASE = 0.125
# Spikes damage by layer count (grounded targets only).
_SPIKES_DAMAGE = {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}

# Setup move categories and their stat boosts (poke-env move.boosts dict).
# Used to evaluate setup moves via multi-turn rollout.
_RECOVERY_MOVES = {
    "recover", "roost", "slackoff", "milkdrink", "softboiled",
    "morningsun", "synthesis", "moonlight", "shoreupshoreupshorenup", "wish"
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


class ExpectimaxAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = HandcraftedValue()
        self._opp_power_cache = {}  # (opp_id, our_id, gen) → power

    def choose_move(self, battle):
        announce_team(self, battle)
        type_chart = GenData.from_gen(battle.gen).type_chart
        self._opp_power_cache.clear()  # Fresh cache per turn

        if not battle.available_moves and battle.available_switches:
            return self.create_order(_best_forced_switch(battle, type_chart))

        # Forced pseudo-moves (Recharge, Struggle, Outrage lock-in, Choice lock):
        # if the engine gives us exactly one option and no switches, there's no
        # decision to make — avoid evaluating the move since its data may be
        # incomplete (e.g. Recharge has no priority field).
        if len(battle.available_moves) == 1 and not battle.available_switches:
            return self.create_order(battle.available_moves[0])

        best_order = None
        best_score = float("-inf")

        for move in battle.available_moves:
            if (move.current_pp or 0) == 0:
                continue

            mid = _norm(move.id)
            is_setup = move.boosts and any(move.boosts.values()) and (move.base_power or 0) == 0
            is_recovery = mid in _RECOVERY_MOVES
            is_hazard = mid in _HAZARD_MOVES
            is_status = mid in _STATUS_MOVES and _STATUS_MOVES[mid] is not None

            if is_setup:
                score = self._eval_setup_move(move, battle, type_chart)
            elif is_recovery:
                score = self._eval_recovery_move(move, battle, type_chart)
            elif is_hazard:
                score = self._eval_hazard_move(move, battle, type_chart)
            elif is_status:
                score = self._eval_status_move(move, battle, type_chart)
            else:
                score = self._eval_move(move, battle, type_chart)

            if score > best_score:
                best_score = score
                best_order = self.create_order(move)
                if is_setup and score > 0.5:
                    break

        for switch in battle.available_switches:
            score = self._eval_switch(switch, battle, type_chart)
            if score > best_score:
                best_score = score
                best_order = self.create_order(switch)

        return best_order if best_order is not None else self.choose_random_move(battle)

    def _eval_move(self, move, battle, type_chart) -> float:
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon

        our_damage = _damage_fraction(move, attacker, defender, type_chart)
        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

        our_hp = attacker.current_hp_fraction if attacker else 1.0
        opp_hp = defender.current_hp_fraction if defender else 1.0

        if _we_go_first(move, attacker, defender):
            opp_after = max(0.0, opp_hp - our_damage)
            our_after = max(0.0, our_hp - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_hp - opp_damage)
            opp_after = max(0.0, opp_hp - (our_damage if our_after > 0.0 else 0.0))

        base_score = self._value.score_transition(battle, our_after, opp_after)

        # Early-game caution: penalize aggressive attacks when we don't know opp's team.
        # M3 switches aggressively to counter our reveals, so taking heavy damage
        # early invites a punish with a counter we haven't seen yet.
        info_deficit = _info_deficit(battle)
        if info_deficit > 0.3 and our_after < 0.55:
            # Risky play when we have limited information about opp team
            risk_penalty = info_deficit * (0.55 - our_after) * 0.6
            base_score -= risk_penalty

        return base_score

    def _eval_setup_move(self, move, battle, type_chart) -> float:
        """Evaluate setup moves via 2-turn virtual rollout.

        Turn 1: we set up, opp attacks. Turn 2: we attack with boost, opp attacks.
        M3 won't switch, setup, or Tera so the rollout is deterministic.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

        our_hp_t1 = attacker.current_hp_fraction if attacker else 1.0
        our_after_t1 = max(0.0, our_hp_t1 - opp_damage)
        if our_after_t1 <= 0.0:
            return self._value.score_transition(battle, 0.0, defender.current_hp_fraction)

        atk_boost = move.boosts.get("atk", 0) if move.boosts else 0
        spa_boost = move.boosts.get("spa", 0) if move.boosts else 0
        if atk_boost <= 0 and spa_boost <= 0:
            return float("-inf")

        best_our_damage_t2 = 0.0
        for m in battle.available_moves:
            if (m.base_power or 0) <= 0:
                continue
            boost = atk_boost if _is_physical_move(m) else spa_boost
            dmg = _damage_fraction(m, attacker, defender, type_chart, atk_boost=boost)
            best_our_damage_t2 = max(best_our_damage_t2, dmg)

        if _effective_speed(attacker, use_actual=True) >= _effective_speed(defender, use_actual=False):
            opp_after = max(0.0, defender.current_hp_fraction - best_our_damage_t2)
            our_after = max(0.0, our_after_t1 - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_after_t1 - opp_damage)
            opp_after = max(0.0, defender.current_hp_fraction - (best_our_damage_t2 if our_after > 0.0 else 0.0))

        return self._value.score_transition(battle, our_after, opp_after)

    def _eval_recovery_move(self, move, battle, type_chart) -> float:
        """Evaluate recovery moves considering actual effective healing.

        - Caps healing at 100% HP (no wasted heal reward)
        - Adds Leftovers passive heal (+1/16 per turn) if held
        - Rewards net-positive healing (heal > damage taken = stall win)
        - Skip healing if we'd faint this turn (use attack instead)
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)
        our_hp = attacker.current_hp_fraction if attacker else 1.0
        opp_hp = defender.current_hp_fraction

        # Raw heal amount (most recovery moves = 0.5)
        hp_recovered = float(move.heal) if move.heal else 0.5

        # Compute HP state: take damage first, then heal, then leftovers
        hp_after_damage = max(0.0, our_hp - opp_damage)

        # Don't heal if we'd faint this turn (better to attack)
        if hp_after_damage <= 0.0:
            return float("-inf")

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

        return base_score + stall_bonus + pp_penalty

    def _eval_hazard_move(self, move, battle, type_chart) -> float:
        """Evaluate hazard-setting moves (Stealth Rock, Spikes, Toxic Spikes, Sticky Web).

        Value scales with opponent's remaining Pokemon (more switches = more value)
        and hazard effectiveness. Don't set if already up or opponent low on mons.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        mid = _norm(move.id)
        opp_side = battle.opponent_side_conditions or {}

        # Don't re-set existing hazards
        if mid == "stealthrock":
            if _match_condition(opp_side, "stealthrock") is not None:
                return float("-inf")
            base_value = 0.35  # High value - works vs most mons
        elif mid == "spikes":
            existing = _match_condition(opp_side, "spikes")
            layers = opp_side.get(existing, 0) if existing else 0
            if layers >= 3:
                return float("-inf")
            base_value = 0.25 - layers * 0.08  # Diminishing returns
        elif mid == "toxicspikes":
            existing = _match_condition(opp_side, "toxicspikes")
            layers = opp_side.get(existing, 0) if existing else 0
            if layers >= 2:
                return float("-inf")
            # Check if opp has any revealed Poison-type (absorbs T-Spikes on switch-in)
            opp_team = battle.opponent_team or {}
            has_poison_absorber = any(
                p and "POISON" in _pokemon_type_names(p)
                for p in opp_team.values()
            )
            if has_poison_absorber:
                return float("-inf")  # Wasted turn - poison type will remove layers
            base_value = 0.20 - layers * 0.08
        elif mid == "stickyweb":
            if _match_condition(opp_side, "stickyweb") is not None:
                return float("-inf")
            base_value = 0.20
        else:
            return float("-inf")

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
            return float("-inf")

        opp_hp = defender.current_hp_fraction if defender else 1.0
        base_score = self._value.score_transition(battle, our_after, opp_hp)

        return base_score + value

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

        return base_score + base_value * acc

    def _eval_switch(self, pokemon, battle, type_chart) -> float:
        opp = battle.opponent_active_pokemon
        opp_damage = self._cached_opp_damage(opp, pokemon, type_chart)
        hazard = _hazard_damage(pokemon, battle.side_conditions, type_chart)
        our_after = max(0.0, pokemon.current_hp_fraction - hazard - opp_damage)
        opp_after = opp.current_hp_fraction if opp else 1.0

        base_score = self._value.score_transition(battle, our_after, opp_after)

        offensive_bonus = _switch_offensive_bonus(pokemon, opp, type_chart)

        # Early-game info-gathering bonus: reward pivots into hard resists when
        # we don't know much about opp's team. Less commit, more scouting.
        info_deficit = _info_deficit(battle)
        info_bonus = 0.0
        if info_deficit > 0.3 and opp_damage < 0.20:
            # Hard resist switch-in during low-info phase = valuable scouting
            info_bonus = info_deficit * 0.15

        return base_score + offensive_bonus + info_bonus

    def _cached_opp_damage(self, opp, our_pokemon, type_chart) -> float:
        """Memoized opponent damage fraction lookup."""
        if not opp or not our_pokemon:
            return 0.0
        key = (id(opp), id(our_pokemon))
        if key not in self._opp_power_cache:
            self._opp_power_cache[key] = _max_opp_damage_fraction(opp, our_pokemon, type_chart)
        return self._opp_power_cache[key]


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


def _we_go_first(move, attacker, defender) -> bool:
    if move.priority > 0:
        return True
    if move.priority < 0:
        return False
    return _effective_speed(attacker, use_actual=True) >= _effective_speed(
        defender, use_actual=False
    )


def _effective_speed(pokemon, use_actual: bool) -> float:
    if pokemon is None:
        return 100.0
    if use_actual and pokemon.stats and pokemon.stats.get("spe"):
        base = pokemon.stats["spe"]
    else:
        base_spe = (pokemon.base_stats or {}).get("spe") or 100
        level = getattr(pokemon, "level", None) or 80
        base = _estimate_actual_speed(base_spe, level)
    stage = (pokemon.boosts or {}).get("spe", 0)
    if stage >= 0:
        return base * (2 + stage) / 2.0
    return base * 2.0 / (2 - stage)


def _estimate_actual_speed(base_stat: int, level: int) -> float:
    """Rough max-EV/IV actual stat approximation.

    Level 80, 31 IV, 252 EV, neutral nature: ((2*base + 31 + 63) * 80) / 100 + 5.
    Good enough for speed comparisons in random battles where we don't know
    the opponent's exact EV spread.
    """
    return ((2 * base_stat + 94) * level) / 100.0 + 5.0


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


def _best_forced_switch(battle, type_chart):
    """Pick best switch-in after fainting, accounting for hazards."""
    opp = battle.opponent_active_pokemon
    return max(
        battle.available_switches,
        key=lambda p: p.current_hp_fraction - _hazard_damage(p, battle.side_conditions, type_chart) - _max_opp_damage_fraction(opp, p, type_chart),
    )


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


def _damage_fraction(move, attacker, defender, type_chart, atk_boost: int = 0) -> float:
    """Estimate damage as fraction of defender's HP using real Gen 9 formula.

    atk_boost: stage count to apply to attacker's attack stat (for setup rollouts).
    Returns fraction in [0, 1+] (may exceed 1 for OHKOs).
    """
    bp = move.base_power or 0
    if bp <= 0 or attacker is None or defender is None:
        return 0.0

    level = getattr(attacker, "level", None) or 80
    is_physical = _is_physical_move(move)
    atk_name = "atk" if is_physical else "spa"
    def_name = "def" if is_physical else "spd"

    A = _estimate_stat(attacker, atk_name)
    D = _estimate_stat(defender, def_name)
    hp = _estimate_hp(defender)

    if atk_boost > 0:
        A = int(A * _stage_to_multiplier(atk_boost))
    elif atk_boost < 0:
        A = int(A * 2 / (2 - atk_boost))

    stab = 1.5 if move.type in attacker.types else 1.0
    eff = move.type.damage_multiplier(defender.type_1, defender.type_2, type_chart=type_chart)
    acc = _accuracy(move)

    base_damage = ((2 * level / 5 + 2) * bp * A / D) / 50 + 2
    return base_damage * stab * eff * acc / hp


def _max_opp_damage_fraction(opp, our_pokemon, type_chart) -> float:
    """Estimate opponent's best damaging move as fraction of our HP.

    Uses real damage formula. Falls back to synthetic 80 BP STAB for unrevealed movesets.
    """
    if opp is None or our_pokemon is None:
        return 0.0

    best = 0.0
    has_moves = False
    for move in opp.moves.values():
        if (move.base_power or 0) <= 0:
            continue
        has_moves = True
        damage = _damage_fraction(move, opp, our_pokemon, type_chart)
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
    """Convert stat stage to damage multiplier. +1→1.5, +2→2.0, +3→2.5, etc."""
    if stage <= 0:
        return 1.0
    return 1.0 + stage * 0.5


def _switch_offensive_bonus(pokemon, opp, type_chart) -> float:
    """Bonus for switching to a mon that threatens the opponent back.

    Rewards pivots that gain offensive advantage (super-effective STAB, immunity to opp's moves).
    """
    if not opp:
        return 0.0

    bonus = 0.0
    for move in pokemon.moves.values():
        bp = move.base_power or 0
        if bp <= 0:
            continue
        stab = 1.5 if move.type in pokemon.types else 1.0
        eff = move.type.damage_multiplier(
            opp.type_1, opp.type_2, type_chart=type_chart
        )
        if eff >= 2.0 and stab == 1.5:
            bonus = max(bonus, 0.15)
        elif eff >= 2.0:
            bonus = max(bonus, 0.10)

    return bonus
