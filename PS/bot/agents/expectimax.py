"""Expectimax planner for M4.

Depth-1 expectimax: for each of our legal actions (moves and switches),
simulate one turn of damage exchange under a deterministic opponent model
(opponent plays max-damage), then score the resulting state with the
hand-crafted value function.

The action with the highest expected value is chosen.

Opponent model: assume the opponent plays their highest-power move
(same heuristic we beat in M3). For unrevealed moves, damage is
estimated from the opponent's STAB types with an assumed 80 BP move.

Acceptance: >=60% winrate vs HeuristicAgent over 500 games.
"""

from poke_env.data import GenData
from poke_env.player import Player

from bot.value.handcrafted import HandcraftedValue


_NORM = 350.0  # move power score → HP fraction; 350 ≈ realistic damage range
_MIN_OPP_POWER = 40.0

# Stealth Rock damage = 1/8 * rock-type effectiveness against switch-in.
_SR_BASE = 0.125
# Spikes damage by layer count (grounded targets only).
_SPIKES_DAMAGE = {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}


class ExpectimaxAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = HandcraftedValue()

    def choose_move(self, battle):
        type_chart = GenData.from_gen(battle.gen).type_chart

        if not battle.available_moves and battle.available_switches:
            return self.create_order(_best_forced_switch(battle, type_chart))

        best_order = None
        best_score = float("-inf")

        for move in battle.available_moves:
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

    def _eval_switch(self, pokemon, battle, type_chart) -> float:
        opp = battle.opponent_active_pokemon
        opp_power = _opp_power_vs(opp, pokemon, type_chart)
        hazard = _hazard_damage(pokemon, battle.side_conditions, type_chart)
        our_after = max(0.0, pokemon.current_hp_fraction - hazard - opp_power / _NORM)
        opp_after = opp.current_hp_fraction if opp else 1.0
        return self._value.score_transition(battle, our_after, opp_after)


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
    if opp is None or our_pokemon is None:
        return _MIN_OPP_POWER

    best = 0.0
    for move in opp.moves.values():
        bp = move.base_power or 0
        if bp <= 0:
            continue
        stab = 1.5 if move.type in opp.types else 1.0
        eff = move.type.damage_multiplier(
            our_pokemon.type_1, our_pokemon.type_2, type_chart=type_chart
        )
        best = max(best, bp * stab * eff)

    if best == 0.0:
        for opp_type in (opp.type_1, opp.type_2):
            if opp_type is None:
                continue
            eff = opp_type.damage_multiplier(
                our_pokemon.type_1, our_pokemon.type_2, type_chart=type_chart
            )
            best = max(best, 80.0 * 1.5 * eff)

    return max(best, _MIN_OPP_POWER)


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
    """HP fraction lost switching into hazards on our side."""
    if not side_conditions:
        return 0.0

    sr_key = _match_condition(side_conditions, "stealthrock")
    spikes_key = _match_condition(side_conditions, "spikes")

    damage = 0.0

    if sr_key is not None:
        damage += _SR_BASE * _rock_effectiveness(pokemon, type_chart)

    if spikes_key is not None and _grounded(pokemon):
        layers = side_conditions[spikes_key] or 1
        damage += _SPIKES_DAMAGE.get(layers, _SPIKES_DAMAGE[3])

    return damage


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
    ability = (getattr(pokemon, "ability", None) or "").lower().replace(" ", "")
    if ability in ("levitate", "magnetrise"):
        return False
    item = (getattr(pokemon, "item", None) or "").lower().replace(" ", "")
    if item == "airballoon":
        return False
    return True


def _best_forced_switch(battle, type_chart):
    opp = battle.opponent_active_pokemon
    return max(
        battle.available_switches,
        key=lambda p: p.current_hp_fraction - _opp_power_vs(opp, p, type_chart) / _NORM,
    )


def _accuracy(move) -> float:
    val = move.accuracy
    if val is True or val is None:
        return 1.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    return float(val)
