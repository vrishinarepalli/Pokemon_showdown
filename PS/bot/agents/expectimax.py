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


class ExpectimaxAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = HandcraftedValue()

    def choose_move(self, battle):
        type_chart = GenData.from_gen(battle.gen).type_chart

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

            is_setup = move.boosts and any(move.boosts.values()) and (move.base_power or 0) == 0
            is_recovery = _norm(move.id) in _RECOVERY_MOVES

            if is_setup:
                score = self._eval_setup_move(move, battle, type_chart)
            elif is_recovery:
                score = self._eval_recovery_move(move, battle, type_chart)
            else:
                score = self._eval_move(move, battle, type_chart)

            if score > best_score:
                best_score = score
                best_order = self.create_order(move)

        for switch in battle.available_switches:
            score = self._eval_switch(switch, battle, type_chart)
            if score > best_score:
                best_score = score
                best_order = self.create_order(switch)

        return best_order if best_order is not None else self.choose_random_move(battle)

    def _eval_move(self, move, battle, type_chart) -> float:
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon

        our_power = _move_power(move, attacker, defender, type_chart)
        opp_power = _opp_power_vs(defender, attacker, type_chart)

        our_damage = our_power / _NORM
        opp_damage = opp_power / _NORM

        our_hp = attacker.current_hp_fraction if attacker else 1.0
        opp_hp = defender.current_hp_fraction if defender else 1.0

        if _we_go_first(move, attacker, defender):
            opp_after = max(0.0, opp_hp - our_damage)
            our_after = max(0.0, our_hp - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_hp - opp_damage)
            opp_after = max(0.0, opp_hp - (our_damage if our_after > 0.0 else 0.0))

        return self._value.score_transition(battle, our_after, opp_after)

    def _eval_setup_move(self, move, battle, type_chart) -> float:
        """Evaluate setup moves via 2-turn virtual rollout.

        Turn 1: we set up, opp attacks. Turn 2: we attack with boost, opp attacks.
        M3 won't switch, setup, or Tera so the rollout is deterministic.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        opp_power = _opp_power_vs(defender, attacker, type_chart)
        opp_damage = opp_power / _NORM

        our_hp_t1 = attacker.current_hp_fraction if attacker else 1.0
        our_after_t1 = max(0.0, our_hp_t1 - opp_damage)
        if our_after_t1 <= 0.0:
            return self._value.score_transition(battle, 0.0, defender.current_hp_fraction)

        boost_factor = _setup_boost_multiplier(move, attacker)
        if boost_factor <= 1.0:
            return float("-inf")

        best_our_power = 0.0
        for m in battle.available_moves:
            if (m.base_power or 0) > 0:
                best_our_power = max(best_our_power, _move_power(m, attacker, defender, type_chart))

        boosted_power = best_our_power * boost_factor
        our_damage_t2 = boosted_power / _NORM

        if _effective_speed(attacker, use_actual=True) >= _effective_speed(defender, use_actual=False):
            opp_after = max(0.0, defender.current_hp_fraction - our_damage_t2)
            our_after = max(0.0, our_after_t1 - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_after_t1 - opp_damage)
            opp_after = max(0.0, defender.current_hp_fraction - (our_damage_t2 if our_after > 0.0 else 0.0))

        return self._value.score_transition(battle, our_after, opp_after)

    def _eval_recovery_move(self, move, battle, type_chart) -> float:
        """Evaluate recovery moves via stall/outlast logic.

        Value = our HP restored vs opponent's best damage per turn.
        Stall wins if we heal more than we take per turn.
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return float("-inf")

        opp_power = _opp_power_vs(defender, attacker, type_chart)
        opp_damage = opp_power / _NORM

        hp_recovered = (move.heal or [0, 0])[0] / (move.heal or [1, 0])[1] if move.heal else 0.0
        net_gain = hp_recovered - opp_damage

        our_hp = attacker.current_hp_fraction if attacker else 1.0
        our_after = min(1.0, max(0.0, our_hp - opp_damage + hp_recovered))
        opp_after = defender.current_hp_fraction

        base_score = self._value.score_transition(battle, our_after, opp_after)

        pp_penalty = 0.0
        if (move.current_pp or 0) < _MIN_PP_PENALTY:
            pp_penalty = -0.1

        stall_bonus = 0.2 if net_gain > 0.05 else 0.0

        return base_score + stall_bonus + pp_penalty

    def _eval_switch(self, pokemon, battle, type_chart) -> float:
        opp = battle.opponent_active_pokemon
        opp_power = _opp_power_vs(opp, pokemon, type_chart)
        hazard = _hazard_damage(pokemon, battle.side_conditions, type_chart)
        our_after = max(0.0, pokemon.current_hp_fraction - hazard - opp_power / _NORM)
        opp_after = opp.current_hp_fraction if opp else 1.0

        base_score = self._value.score_transition(battle, our_after, opp_after)

        offensive_bonus = _switch_offensive_bonus(pokemon, opp, type_chart)
        return base_score + offensive_bonus


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
        key=lambda p: p.current_hp_fraction - _hazard_damage(p, battle.side_conditions, type_chart) - _opp_power_vs(opp, p, type_chart) / _NORM,
    )


def _accuracy(move) -> float:
    val = move.accuracy
    if val is True or val is None:
        return 1.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    return float(val)


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
