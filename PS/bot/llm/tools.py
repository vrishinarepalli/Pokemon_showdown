"""Decision tools for the M5 LLM agent — the "code does the heavy lifting" layer.

Each function pre-computes grounded facts (damage %, KO odds, speed, threats,
switch matchups) from the validated engine in bot.agents.expectimax, so the LLM
only chooses among analyzed candidates and never has to compute or guess numbers.
"""

from bot.agents.expectimax import (
    _accuracy,
    _damage_fraction,
    _effective_speed,
    _is_physical_move,
    _ko_probability,
    _max_threat_via_movepool,
    _norm,
    _trick_room_active,
)


def _pct(x: float) -> float:
    return round(100.0 * x, 1)


def _our_item_mult(mon, is_physical: bool) -> float:
    item = _norm(getattr(mon, "item", None)) if mon else ""
    if is_physical and item == "choiceband":
        return 1.5
    if (not is_physical) and item == "choicespecs":
        return 1.5
    if item == "lifeorb":
        return 1.3
    return 1.0


def analyze_move(move, battle, type_chart) -> dict:
    """Grounded outcome of using `move` this turn against the opponent's active."""
    atk = battle.active_pokemon
    dfn = battle.opponent_active_pokemon
    is_phys = _is_physical_move(move)
    is_status = (move.base_power or 0) == 0 and not getattr(move, "damage", None)

    boost = (atk.boosts or {}).get("atk" if is_phys else "spa", 0) if atk else 0
    dmg = _damage_fraction(move, atk, dfn, type_chart, atk_boost=boost, battle=battle)
    dmg *= _our_item_mult(atk, is_phys)

    opp_hp = dfn.current_hp_fraction if dfn else 1.0
    acc = _accuracy(move)
    on_hit = dmg / acc if acc > 0 else dmg
    p_ko = _ko_probability(on_hit, opp_hp) if not is_status else 0.0

    return {
        "name": move.id,
        "type": getattr(move.type, "name", str(move.type)).title(),
        "category": "status" if is_status else ("physical" if is_phys else "special"),
        "base_power": move.base_power or 0,
        "expected_dmg_pct": _pct(dmg),          # % of opponent's max HP
        "ko_chance": round(p_ko, 2),            # P(this move KOs the opponent now)
        "priority": getattr(move, "priority", 0),
        "accuracy": round(acc, 2),
        "pp_left": getattr(move, "current_pp", None),
    }


def analyze_switch(pokemon, battle, type_chart, tracker=None) -> dict:
    """Grounded matchup if we switch `pokemon` in against the opponent's active."""
    opp = battle.opponent_active_pokemon
    # Worst the opponent can do to this switch-in (revealed + likely movepool).
    incoming = _max_threat_via_movepool(opp, pokemon, type_chart, tracker=tracker) if opp else 0.0
    # Best this switch-in threatens back, across its known moves.
    out = 0.0
    for m in pokemon.moves.values():
        if (m.base_power or 0) <= 0:
            continue
        is_phys = _is_physical_move(m)
        boost = (pokemon.boosts or {}).get("atk" if is_phys else "spa", 0)
        d = _damage_fraction(m, pokemon, opp, type_chart, atk_boost=boost, battle=battle) if opp else 0.0
        out = max(out, d * _our_item_mult(pokemon, is_phys))
    return {
        "species": pokemon.species,
        "hp_pct": _pct(pokemon.current_hp_fraction or 0.0),
        "incoming_dmg_pct": _pct(incoming),     # what opp's best hit does to it
        "threatens_back_pct": _pct(out),        # best it threatens the opp with (known moves)
    }


def battle_summary(battle, type_chart, tracker=None) -> dict:
    """Compact, decision-relevant snapshot: HP, speed order, threats, KO reads."""
    atk = battle.active_pokemon
    opp = battle.opponent_active_pokemon
    our_speed = _effective_speed(atk, use_actual=True) if atk else 0.0
    opp_speed = _effective_speed(opp, use_actual=False) if opp else 0.0
    tr = _trick_room_active(battle)
    we_faster = (our_speed <= opp_speed) if tr else (our_speed >= opp_speed)

    opp_threat = _max_threat_via_movepool(opp, atk, type_chart, tracker=tracker) if (atk and opp) else 0.0
    our_hp = atk.current_hp_fraction if atk else 0.0

    return {
        "turn": battle.turn,
        "our_active": {
            "species": atk.species if atk else None,
            "hp_pct": _pct(our_hp),
            "types": [getattr(t, "name", str(t)).title() for t in (atk.type_1, atk.type_2) if t] if atk else [],
            "status": getattr(getattr(atk, "status", None), "name", None),
            "boosts": {k: v for k, v in (atk.boosts or {}).items() if v} if atk else {},
        },
        "opp_active": {
            "species": opp.species if opp else None,
            "hp_pct": _pct(opp.current_hp_fraction or 0.0) if opp else None,
            "types": [getattr(t, "name", str(t)).title() for t in (opp.type_1, opp.type_2) if t] if opp else [],
            "status": getattr(getattr(opp, "status", None), "name", None),
            "revealed_moves": [m.id for m in opp.moves.values()] if opp else [],
        },
        "we_move_first": bool(we_faster),
        "trick_room": tr,
        "opp_best_dmg_to_us_pct": _pct(opp_threat),
        "opp_can_ko_us": opp_threat >= our_hp > 0.0,
        "our_remaining": sum(1 for m in (battle.team or {}).values() if m and not m.fainted),
        "opp_remaining": 6 - len([m for m in (battle.opponent_team or {}).values() if m and m.fainted]),
    }
