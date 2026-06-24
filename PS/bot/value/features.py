"""Shared state featurizer for the learned value function.

ONE function, used by BOTH the offline dataset builder (replaying logs through a
poke-env Battle) and the live expectimax leaf evaluator. Sharing it is the
train/serve parity guarantee: identical Battle object -> identical features.

All features are from the perspective player's POV (battle.active_pokemon = "us")
and observable from a spectator log and a live battle alike, so
V(extract_features(battle)) estimates P(we win). Lean v1 set (~62 dims); add
type-matchup / speed-order / move features later if the net underfits.

Field/weather/side-condition flags are matched by enum .name (not by importing
members) so a poke-env enum rename degrades a feature to 0 instead of crashing.
"""

from poke_env.battle.status import Status

# Fixed orderings -> a stable feature layout. Append-only (never reorder) so a
# trained model stays compatible.
_STATUSES = [Status.BRN, Status.FRZ, Status.PAR, Status.PSN, Status.SLP, Status.TOX, Status.FNT]
_BOOSTS = ["atk", "def", "spa", "spd", "spe", "accuracy", "evasion"]
# (feature name, set of enum names that count as "on")
_WEATHERS = [
    ("sand", {"SANDSTORM"}),
    ("rain", {"RAINDANCE", "PRIMORDIALSEA"}),
    ("sun", {"SUNNYDAY", "DESOLATELAND"}),
    ("snow", {"SNOWSCAPE", "HAIL"}),
]
_TERRAINS = [
    ("electric_terrain", {"ELECTRIC_TERRAIN"}),
    ("grassy_terrain", {"GRASSY_TERRAIN"}),
    ("misty_terrain", {"MISTY_TERRAIN"}),
    ("psychic_terrain", {"PSYCHIC_TERRAIN"}),
    ("trick_room", {"TRICK_ROOM"}),
]
# (name, enum name, divisor) — stackable hazards divide by max stacks; flags use 1.
_SIDE = [
    ("stealth_rock", "STEALTH_ROCK", 1),
    ("spikes", "SPIKES", 3),
    ("toxic_spikes", "TOXIC_SPIKES", 2),
    ("sticky_web", "STICKY_WEB", 1),
    ("reflect", "REFLECT", 1),
    ("light_screen", "LIGHT_SCREEN", 1),
    ("aurora_veil", "AURORA_VEIL", 1),
    ("tailwind", "TAILWIND", 1),
]


def _active_features(mon):
    """hp(1) + status one-hot(7) + boosts(7) = 15. None active -> all zeros."""
    if mon is None:
        return [0.0] * (1 + len(_STATUSES) + len(_BOOSTS))
    hp = mon.current_hp_fraction
    feats = [hp if hp is not None else 0.0]
    feats += [1.0 if mon.status == s else 0.0 for s in _STATUSES]
    feats += [mon.boosts.get(b, 0) / 6.0 for b in _BOOSTS]
    return feats


def _team_features(team):
    """fainted/6, revealed/6, avg-hp-of-alive = 3."""
    mons = list(team.values())
    fainted = sum(1 for m in mons if m.fainted)
    alive = [m for m in mons if not m.fainted]
    avg_hp = sum((m.current_hp_fraction or 0.0) for m in alive) / len(alive) if alive else 0.0
    return [fainted / 6.0, len(mons) / 6.0, avg_hp]


def _side_features(conditions):
    """8 hazard/screen features for one side, by enum name (count or flag)."""
    by_name = {sc.name: val for sc, val in conditions.items()}
    return [min(by_name.get(name, 0), div) / div for _, name, div in _SIDE]


def extract_features(battle):
    """Battle -> flat list[float], length == len(FEATURE_NAMES). 'us' = the
    perspective player (battle.active_pokemon); the value target is P(us wins)."""
    f = []
    f += _active_features(battle.active_pokemon)            # 15
    f += _active_features(battle.opponent_active_pokemon)   # 15
    f += _team_features(battle.team)                        # 3
    f += _team_features(battle.opponent_team)               # 3

    wnames = {w.name for w in battle.weather}
    f += [1.0 if names & wnames else 0.0 for _, names in _WEATHERS]   # 4
    fldnames = {fl.name for fl in battle.fields}
    f += [1.0 if names & fldnames else 0.0 for _, names in _TERRAINS] # 5

    f += _side_features(battle.side_conditions)             # 8 (us)
    f += _side_features(battle.opponent_side_conditions)    # 8 (opp)

    f.append(min(battle.turn, 50) / 50.0)                   # 1
    assert len(f) == len(FEATURE_NAMES), (len(f), len(FEATURE_NAMES))
    return f


def _build_names():
    names = []
    for side in ("us", "opp"):
        names.append(f"{side}_hp")
        names += [f"{side}_status_{s.name}" for s in _STATUSES]
        names += [f"{side}_boost_{b}" for b in _BOOSTS]
    for side in ("us", "opp"):
        names += [f"{side}_team_fainted", f"{side}_team_revealed", f"{side}_team_avghp"]
    names += [f"weather_{n}" for n, _ in _WEATHERS]
    names += [f"field_{n}" for n, _ in _TERRAINS]
    for side in ("us", "opp"):
        names += [f"{side}_{n}" for n, _, _ in _SIDE]
    names.append("turn")
    return names


FEATURE_NAMES = _build_names()
N_FEATURES = len(FEATURE_NAMES)
