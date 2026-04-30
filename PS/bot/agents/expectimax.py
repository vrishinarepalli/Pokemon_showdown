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
from bot.agents.battle_logger import BattleLogger
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


class ExpectimaxAgent(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = HandcraftedValue()
        self._opp_power_cache = {}  # (opp_id, our_id, gen) → power
        self._battle_logger = None  # Created per battle
        self._battle_logs = []  # All completed battle logs
        self._strategic_ctx = None  # Per-turn strategic state (set in choose_move)
        self._opp_tracker = None    # Per-battle opp set tracker (created on first turn)

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

        # Extract strategic context for logging
        strategic_state = ""
        active_threat = 0.0
        bench_threat = 0.0
        unknown_threat = 0.0
        we_go_first = False
        opp_predicted_action = ""
        opp_predicted_damage = 0.0
        opp_set_predictions = {}

        if self._strategic_ctx:
            strategic_state = self._strategic_ctx["state"]
            active_threat = self._strategic_ctx["threat_breakdown"].get("active_threat", 0.0)
            bench_threat = self._strategic_ctx["threat_breakdown"].get("bench_threat", 0.0)
            unknown_threat = self._strategic_ctx["threat_breakdown"].get("unknown_threat", 0.0)
            opp_predicted_action = self._strategic_ctx["predicted_action"]["action"]
            opp_predicted_damage = self._strategic_ctx["predicted_action"]["expected_damage"]
            we_go_first = self._we_go_first(battle) if battle.active_pokemon else False

        # Get speed stages for logging
        our_speed_stage = battle.active_pokemon.speed_boosts if battle.active_pokemon else 0
        opp_speed_stage = battle.opponent_active_pokemon.speed_boosts if battle.opponent_active_pokemon else 0

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
            chosen_switch = _best_forced_switch(battle, type_chart)
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
        best_move_score = float("-inf")

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

            if is_setup:
                result = self._eval_setup_move(move, battle, type_chart)
            elif is_recovery:
                result = self._eval_recovery_move(move, battle, type_chart)
            elif is_hazard:
                result = self._eval_hazard_move(move, battle, type_chart)
            elif is_status:
                result = self._eval_status_move(move, battle, type_chart)
            else:
                result = self._eval_move(move, battle, type_chart)

            # Ensure result is _EvalResult; convert float if needed
            if isinstance(result, float):
                result = _EvalResult(result)

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
            best_move_score = max(best_move_score, result.score)

            if result.score > best_score:
                best_score = result.score
                best_order = self.create_order(move)
                chosen_action = ("move", move.id)
                if is_setup and result.score > 0.5:
                    break

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

        # Read our active boosts so Swords Dance, Nasty Plot, etc. are reflected
        boosts = (attacker.boosts if attacker else None) or {}
        is_physical = _is_physical_move(move)
        atk_boost = boosts.get("atk" if is_physical else "spa", 0)

        our_damage = _damage_fraction(move, attacker, defender, type_chart, atk_boost=atk_boost)
        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

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
        # M3 switches aggressively to counter our reveals, so taking heavy damage
        # early invites a punish with a counter we haven't seen yet.
        info_deficit = _info_deficit(battle)
        if info_deficit > 0.3 and our_after < 0.55:
            # Risky play when we have limited information about opp team
            risk_penalty = info_deficit * (0.55 - our_after) * 0.6
            base_score -= risk_penalty

        # Tiebreakers (small bonuses, won't affect non-tied decisions):
        # 1. Prefer STAB moves (more reliable damage, harder to resist)
        # 2. Prefer higher raw damage (overkill = safety vs miscalculation)
        if attacker and move.type in attacker.types:
            base_score += 0.002  # STAB tiebreaker
        base_score += our_damage * 0.001  # Damage tiebreaker

        reasoning = f"damage_to_opp={our_damage:.3f}, damage_from_opp={opp_damage:.3f}"
        return _EvalResult(
            base_score,
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

        opp_damage = self._cached_opp_damage(defender, attacker, type_chart)

        our_hp_t1 = attacker.current_hp_fraction if attacker else 1.0
        our_after_t1 = max(0.0, our_hp_t1 - opp_damage)
        if our_after_t1 <= 0.0:
            score = self._value.score_transition(battle, 0.0, defender.current_hp_fraction)
            return _EvalResult(score, damage_taken=opp_damage, expected_hp_after=0.0, is_setup=True, reasoning="Setup would result in KO")

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

        if _effective_speed(attacker, use_actual=True) >= _effective_speed(defender, use_actual=False):
            opp_after = max(0.0, defender.current_hp_fraction - best_our_damage_t2)
            our_after = max(0.0, our_after_t1 - (opp_damage if opp_after > 0.0 else 0.0))
        else:
            our_after = max(0.0, our_after_t1 - opp_damage)
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

        reasoning = f"2-turn setup: +{atk_boost}atk/+{spa_boost}spa, t2_damage={best_our_damage_t2:.3f}, opp_dmg={opp_damage:.3f}"
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
        """
        attacker = battle.active_pokemon
        defender = battle.opponent_active_pokemon
        if not attacker or not defender:
            return _EvalResult(float("-inf"), reasoning="No attacker or defender")

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
        ctx = self._strategic_ctx
        ctx_adj = 0.0
        if ctx is not None:
            active = battle.active_pokemon
            if ctx["state"] == "SAFE" and active is not None:
                # Active is safe — switching forfeits a turn for no reason
                ctx_adj -= 0.10
            # Sacrifice cycle prevention: heavy penalty for switching INTO a KO.
            # If switch target gets OHKO'd by predicted opp action, this is throwing
            # the mon away. Better to stay and extract value with active.
            if our_after <= 0.0:
                ctx_adj -= 0.30

        score = base_score + offensive_bonus + info_bonus + ctx_adj
        reasoning = f"switch_to {pokemon.species}: hazard_dmg={hazard:.3f}, opp_dmg={opp_damage:.3f}"
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
    if use_actual and pokemon.stats and pokemon.stats.get("spe"):
        base = pokemon.stats["spe"]
    else:
        base_spe = (pokemon.base_stats or {}).get("spe") or 100
        level = getattr(pokemon, "level", None) or 80
        base = _estimate_actual_speed(base_spe, level)
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

    # Use existing M3 switch probability to decide stay vs switch
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

    # Revealed damaging moves
    for m in opp_mon.moves.values():
        if (m.base_power or 0) > 0:
            d = _damage_fraction(m, opp_mon, our_pokemon, type_chart)
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
                d = _damage_fraction(m, opp_mon, our_pokemon, type_chart)
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

    atk_boost: stage count to apply to attacker's attack stat (for setup rollouts
    where we're projecting future state). Defender's current defensive boost
    is read automatically from defender.boosts.

    Critical hits: ignores base 6.25% crit rate (random anomaly). Only accounts
    for high-crit moves (12.5%+) or guaranteed crits.

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

    if atk_boost != 0:
        A = int(A * _stage_to_multiplier(atk_boost))

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

    # High-crit rate handling: only apply if move has guaranteed or 12.5%+ crit rate
    # (e.g., Stone Edge 12.5%, Scope Lens users, moves with guaranteed crit)
    # Ignore base 6.25% crit as random noise
    crit_mult = 1.0
    crit_rate = getattr(move, "crit_ratio", 0) or 0
    # In poke-env, crit_ratio of 1 = 6.25%, 2 = 12.5%, etc.
    if crit_rate >= 2:  # 12.5% or higher
        crit_mult = 1.5  # Crits deal 1.5x damage in Gen 9

    return base_damage * stab * eff * acc * crit_mult / hp


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
