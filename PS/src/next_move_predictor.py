"""
Next Move Predictor
Predicts opponent's next move using game theory, damage calculations, and historical patterns
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from src.damage_calculator import DamageCalculator
from src.set_predictor import SetPrediction


@dataclass
class MoveRecommendation:
    """Recommendation for what move opponent will use next"""
    move: str
    probability: float
    reasoning: str
    threat_level: str  # "Low", "Medium", "High", "Lethal"
    optimal_counter: Optional[str] = None  # Your best move to counter this


class NextMovePredictor:
    """
    Predicts opponent's next move based on:
    1. Game theory (what's optimal for them)
    2. Damage calculations (what threatens you most)
    3. Historical patterns (what they've done before)
    4. Psychological factors (aggressive vs defensive play)
    """

    def __init__(self, data_manager, damage_calculator: Optional[DamageCalculator] = None):
        """
        Initialize next move predictor

        Args:
            data_manager: DataManager instance
            damage_calculator: DamageCalculator instance (optional)
        """
        self.data_manager = data_manager
        self.damage_calc = damage_calculator or DamageCalculator(data_manager)

        # Track opponent's move history
        self.move_history = []
        self.switch_history = []

    def predict_next_move(
        self,
        opponent_pokemon: str,
        your_pokemon: str,
        set_prediction: SetPrediction,
        game_state: Dict,
        your_team: Optional[List[Dict]] = None
    ) -> List[MoveRecommendation]:
        """
        Predict opponent's most likely next move

        Args:
            opponent_pokemon: Opponent's current Pokemon
            your_pokemon: Your current Pokemon
            set_prediction: Current set prediction for opponent
            game_state: Current game state (HP, hazards, etc.)
            your_team: Your remaining team (for predicting switches)

        Returns:
            List of MoveRecommendations sorted by probability
        """
        recommendations = []

        # Get opponent's known and predicted moves
        known_moves = list(set_prediction.revealed_moves)
        predicted_moves = self._get_top_predicted_moves(set_prediction, n=4 - len(known_moves))

        all_possible_moves = known_moves + predicted_moves

        # Analyze each possible move
        for move in all_possible_moves:
            move_score = 0.0
            reasoning = []

            # 1. OFFENSIVE PRESSURE - Can they KO you?
            threat_score, threat_level, damage_info = self._evaluate_offensive_threat(
                opponent_pokemon, your_pokemon, move, set_prediction, game_state
            )
            move_score += threat_score
            reasoning.append(damage_info)

            # 2. DEFENSIVE PLAY - Are they trying to set up or stall?
            defensive_score, defensive_reason = self._evaluate_defensive_play(
                move, game_state, set_prediction
            )
            move_score += defensive_score
            if defensive_reason:
                reasoning.append(defensive_reason)

            # 3. MOMENTUM CONTROL - Pivoting, hazards, etc.
            momentum_score, momentum_reason = self._evaluate_momentum_moves(
                move, game_state, opponent_pokemon
            )
            move_score += momentum_score
            if momentum_reason:
                reasoning.append(momentum_reason)

            # 4. GAME THEORY - What's optimal?
            theory_score, theory_reason = self._evaluate_game_theory(
                move, opponent_pokemon, your_pokemon, game_state
            )
            move_score += theory_score
            if theory_reason:
                reasoning.append(theory_reason)

            # 5. HISTORICAL PATTERNS - What have they done before?
            pattern_score, pattern_reason = self._evaluate_historical_patterns(
                move, opponent_pokemon, game_state
            )
            move_score += pattern_score
            if pattern_reason:
                reasoning.append(pattern_reason)

            # Normalize score to probability
            probability = min(1.0, move_score / 10.0)

            # Determine optimal counter
            optimal_counter = self._find_optimal_counter(move, your_pokemon, game_state)

            recommendations.append(MoveRecommendation(
                move=move,
                probability=probability,
                reasoning="; ".join(reasoning),
                threat_level=threat_level,
                optimal_counter=optimal_counter
            ))

        # Sort by probability
        recommendations.sort(key=lambda x: x.probability, reverse=True)

        # Normalize probabilities to sum to 1.0
        total_prob = sum(r.probability for r in recommendations)
        if total_prob > 0:
            for rec in recommendations:
                rec.probability = rec.probability / total_prob

        return recommendations

    def _get_top_predicted_moves(self, set_prediction: SetPrediction, n: int) -> List[str]:
        """Get top N predicted moves that aren't revealed yet"""
        unrevealed = {
            move: prob
            for move, prob in set_prediction.move_probs.items()
            if move not in set_prediction.revealed_moves
        }

        sorted_moves = sorted(unrevealed.items(), key=lambda x: x[1], reverse=True)
        return [move for move, _ in sorted_moves[:n]]

    def _evaluate_offensive_threat(
        self,
        attacker: str,
        defender: str,
        move: str,
        set_prediction: SetPrediction,
        game_state: Dict
    ) -> Tuple[float, str, str]:
        """
        Evaluate offensive threat of a move

        Returns:
            (score, threat_level, reasoning)
        """
        # Calculate damage
        result = self.damage_calc.calculate_damage(
            attacker_name=attacker,
            defender_name=defender,
            move_name=move,
            attacker_item=set_prediction.revealed_item,
            attacker_ability=set_prediction.revealed_ability,
            weather=game_state.get('weather'),
            terrain=game_state.get('terrain')
        )

        # Score based on damage
        if result.guaranteed_ko:
            return (10.0, "Lethal", f"{move} guarantees KO ({result.min_percent:.0f}%+)")
        elif result.possible_ko:
            return (8.0, "High", f"{move} can KO ({result.roll_to_ko})")
        elif result.max_percent >= 80:
            return (6.0, "High", f"{move} deals heavy damage ({result.min_percent:.0f}-{result.max_percent:.0f}%)")
        elif result.max_percent >= 50:
            return (4.0, "Medium", f"{move} deals moderate damage ({result.min_percent:.0f}-{result.max_percent:.0f}%)")
        elif result.max_percent >= 25:
            return (2.0, "Low", f"{move} deals light damage ({result.min_percent:.0f}-{result.max_percent:.0f}%)")
        else:
            return (0.5, "Low", f"{move} barely damages ({result.max_percent:.0f}%)")

    def _evaluate_defensive_play(
        self,
        move: str,
        game_state: Dict,
        set_prediction: SetPrediction
    ) -> Tuple[float, str]:
        """Evaluate if move is defensive/setup"""
        setup_moves = {
            'Swords Dance', 'Nasty Plot', 'Dragon Dance', 'Calm Mind', 'Bulk Up',
            'Quiver Dance', 'Shift Gear', 'Shell Smash', 'Tail Glow'
        }

        recovery_moves = {
            'Recover', 'Roost', 'Soft-Boiled', 'Wish', 'Synthesis',
            'Morning Sun', 'Moonlight', 'Rest', 'Slack Off'
        }

        hazard_moves = {
            'Stealth Rock', 'Spikes', 'Toxic Spikes', 'Sticky Web'
        }

        if move in setup_moves:
            # Check if it's safe to set up
            your_hp_percent = game_state.get('your_hp_percent', 100)
            if your_hp_percent < 50:
                return (7.0, f"Safe to set up {move} (you're weakened)")
            else:
                return (3.0, f"Risky to set up {move} (you're healthy)")

        if move in recovery_moves:
            opponent_hp = game_state.get('opponent_hp_percent', 100)
            if opponent_hp < 60:
                return (6.0, f"Likely to use {move} (low HP)")
            else:
                return (1.0, f"Unlikely to use {move} (healthy)")

        if move in hazard_moves:
            hazards_set = game_state.get('hazards_set', [])
            if move not in hazards_set:
                return (5.0, f"Good time to set {move}")
            else:
                return (0.0, f"{move} already set")

        return (0.0, "")

    def _evaluate_momentum_moves(
        self,
        move: str,
        game_state: Dict,
        pokemon: str
    ) -> Tuple[float, str]:
        """Evaluate momentum/pivot moves"""
        pivot_moves = {'U-turn', 'Volt Switch', 'Flip Turn', 'Teleport', 'Parting Shot'}

        if move in pivot_moves:
            # Pivoting is good if:
            # 1. Opponent has unfavorable matchup
            # 2. They want to scout your move
            # 3. They want momentum
            return (4.0, f"{move} to gain momentum/scout")

        return (0.0, "")

    def _evaluate_game_theory(
        self,
        move: str,
        attacker: str,
        defender: str,
        game_state: Dict
    ) -> Tuple[float, str]:
        """
        Evaluate move from game theory perspective

        What's the Nash equilibrium? What's optimal play?
        """
        # Priority moves are good if opponent is faster
        priority_moves = {
            'Extreme Speed', 'Sucker Punch', 'Aqua Jet', 'Ice Shard',
            'Mach Punch', 'Shadow Sneak', 'Accelerock', 'Fake Out'
        }

        if move in priority_moves:
            your_hp = game_state.get('your_hp_percent', 100)
            if your_hp < 30:
                return (8.0, f"{move} priority to revenge kill (you're low HP)")
            else:
                return (2.0, f"{move} priority move")

        # Protect is good for scouting/stalling
        if move == 'Protect':
            if game_state.get('protect_last_turn', False):
                return (0.0, "Protect failed last turn (unlikely to use again)")
            else:
                return (3.0, "Protect to scout/stall")

        return (0.0, "")

    def _evaluate_historical_patterns(
        self,
        move: str,
        pokemon: str,
        game_state: Dict
    ) -> Tuple[float, str]:
        """
        Evaluate based on what opponent has done before

        Args:
            move: Move being evaluated
            pokemon: Pokemon name
            game_state: Game state

        Returns:
            (score, reasoning)
        """
        # Count how often this move was used in similar situations
        # This would require tracking move history
        # For now, return neutral score

        # Check if move was used recently
        recent_moves = self.move_history[-3:] if len(self.move_history) >= 3 else self.move_history
        if move in recent_moves:
            # Less likely to spam the same move (unless it's optimal)
            return (-1.0, f"{move} used recently (less likely)")

        return (0.0, "")

    def _find_optimal_counter(
        self,
        opponent_move: str,
        your_pokemon: str,
        game_state: Dict
    ) -> Optional[str]:
        """
        Find your best move to counter opponent's predicted move

        Args:
            opponent_move: Predicted opponent move
            your_pokemon: Your Pokemon
            game_state: Game state

        Returns:
            Name of optimal counter move
        """
        # This is complex - would need to analyze:
        # 1. Can you survive the move?
        # 2. Can you KO back?
        # 3. Should you switch?
        # 4. Should you protect/set up?

        # For now, return None (TODO: implement)
        return None

    def record_move(self, pokemon: str, move: str, turn: int):
        """
        Record a move the opponent used

        Args:
            pokemon: Pokemon that used the move
            move: Move used
            turn: Turn number
        """
        self.move_history.append({
            'pokemon': pokemon,
            'move': move,
            'turn': turn
        })

    def should_predict_switch(
        self,
        opponent_pokemon: str,
        your_pokemon: str,
        game_state: Dict,
        opponent_team: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Predict if opponent will switch out

        Args:
            opponent_pokemon: Opponent's current Pokemon
            your_pokemon: Your current Pokemon
            game_state: Game state
            opponent_team: Opponent's team (if known)

        Returns:
            (will_switch, predicted_switch_target)
        """
        # Opponent likely switches if:
        # 1. They're at a type disadvantage
        # 2. You threaten a KO
        # 3. They need to preserve their Pokemon
        # 4. They have a better matchup on the bench

        # For now, simple heuristic
        # TODO: Implement full switch prediction
        return (False, None)


def main():
    """Test next move predictor"""
    from src.data_manager import DataManager
    from src.set_predictor import SetPredictor

    dm = DataManager()

    if not dm.is_data_available():
        print("Error: Data not available. Run update_data.py first.")
        return

    predictor = NextMovePredictor(dm)
    set_predictor = SetPredictor(dm)

    print("=" * 70)
    print("Next Move Predictor Test")
    print("=" * 70)

    # Scenario: Opponent Kingambit vs Your Great Tusk
    print("\n[Scenario] Opponent: Kingambit vs Your: Great Tusk")
    print("-" * 70)

    # Get set prediction for Kingambit
    set_prediction = set_predictor.create_initial_prediction("Kingambit")
    set_prediction = set_predictor.update_with_move(set_prediction, "Sucker Punch")

    # Game state
    game_state = {
        'your_hp_percent': 85,
        'opponent_hp_percent': 100,
        'weather': None,
        'terrain': None,
        'hazards_set': [],
        'your_team': ['Great Tusk', 'Gholdengo', 'Dragapult']
    }

    # Predict next move
    recommendations = predictor.predict_next_move(
        opponent_pokemon="Kingambit",
        your_pokemon="Great Tusk",
        set_prediction=set_prediction,
        game_state=game_state
    )

    print("\nPredicted Moves (in order of likelihood):")
    print("-" * 70)
    for i, rec in enumerate(recommendations[:5], 1):
        print(f"\n{i}. {rec.move} ({rec.probability*100:.1f}%)")
        print(f"   Threat Level: {rec.threat_level}")
        print(f"   Reasoning: {rec.reasoning}")
        if rec.optimal_counter:
            print(f"   Counter: {rec.optimal_counter}")

    print("\n" + "=" * 70)
    print("\nRecommendation: Prepare for high-damage moves!")
    print("Most likely: Opponent will try to deal heavy damage or set up")


if __name__ == "__main__":
    main()
