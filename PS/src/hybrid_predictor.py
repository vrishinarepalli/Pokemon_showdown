"""
Hybrid Set Predictor
Combines Bayesian inference with Machine Learning predictions
"""
from typing import Dict, List, Optional
from src.set_predictor import SetPredictor, SetPrediction
from src.ml_predictor import MLPredictor
from src.battle_recorder import BattleRecorder, PokemonRecord, RevealedTiming, TeamContext


class HybridSetPredictor(SetPredictor):
    """
    Enhanced set predictor that combines:
    1. Bayesian inference (from Smogon usage stats)
    2. Machine learning (from collected battle history)

    Strategy:
    - Start with pure Bayesian (no training data)
    - Gradually increase ML weight as more data is collected
    - Always maintain Bayesian baseline for unseen scenarios
    """

    def __init__(self, data_manager):
        """
        Initialize hybrid predictor

        Args:
            data_manager: DataManager instance with loaded Smogon data
        """
        super().__init__(data_manager)

        # ML components
        self.ml_predictor = MLPredictor(data_manager)
        self.battle_recorder = BattleRecorder()

        # Try to load existing models
        self.ml_predictor.load_models()

        # Battle context for ML features
        self.current_battle_context = {}

    def set_battle_context(self, battle_id: str, tier: str = "gen9ou",
                          player_rating: Optional[int] = None,
                          opponent_username: Optional[str] = None):
        """
        Set context for current battle

        Args:
            battle_id: Unique battle identifier
            tier: Battle tier
            player_rating: Player's rating
            opponent_username: Opponent's username
        """
        self.current_battle_context = {
            'battle_id': battle_id,
            'tier': tier,
            'player_rating': player_rating,
            'opponent_username': opponent_username,
            'turn_number': 0,
            'pokemon_seen': {}
        }

        # Start recording battle
        self.battle_recorder.start_battle(
            battle_id=battle_id,
            tier=tier,
            player_rating=player_rating,
            opponent_username=opponent_username
        )

    def create_initial_prediction(self, pokemon_name: str) -> SetPrediction:
        """
        Create initial prediction with Bayesian + ML blend

        Args:
            pokemon_name: Name of the Pokemon

        Returns:
            SetPrediction with blended probabilities
        """
        # 1. Get Bayesian prediction (existing implementation)
        prediction = super().create_initial_prediction(pokemon_name)

        # 2. If ML is trained, blend predictions
        if self.ml_predictor.is_trained and self.current_battle_context:
            ml_weight = self._calculate_ml_weight()

            if ml_weight > 0:
                # Get ML predictions
                ml_predictions = self.ml_predictor.predict(
                    pokemon=pokemon_name,
                    revealed_moves=[],
                    revealed_ability=None,
                    turn_number=self.current_battle_context.get('turn_number', 0),
                    opponent_rating=self.current_battle_context.get('player_rating')
                )

                if ml_predictions:
                    # Blend Bayesian and ML
                    prediction = self._blend_predictions(
                        prediction, ml_predictions, ml_weight
                    )
                    print(f"  🤖 ML blend: {ml_weight:.0%} ML, {1-ml_weight:.0%} Bayesian")

        # Track this Pokemon
        if self.current_battle_context:
            self.current_battle_context['pokemon_seen'][pokemon_name] = {
                'first_turn': self.current_battle_context.get('turn_number', 0),
                'prediction': prediction
            }

        return prediction

    def update_with_move(self, prediction: SetPrediction, move_name: str) -> SetPrediction:
        """
        Update prediction with ML enhancement

        Args:
            prediction: Current prediction
            move_name: Name of the revealed move

        Returns:
            Updated SetPrediction
        """
        # 1. Update with Bayesian logic (existing implementation)
        prediction = super().update_with_move(prediction, move_name)

        # 2. Blend with ML if available
        if self.ml_predictor.is_trained and self.current_battle_context:
            ml_weight = self._calculate_ml_weight()

            if ml_weight > 0:
                ml_predictions = self.ml_predictor.predict(
                    pokemon=prediction.pokemon,
                    revealed_moves=list(prediction.revealed_moves),
                    revealed_ability=prediction.revealed_ability,
                    turn_number=self.current_battle_context.get('turn_number', 0),
                    opponent_rating=self.current_battle_context.get('player_rating')
                )

                if ml_predictions:
                    prediction = self._blend_predictions(
                        prediction, ml_predictions, ml_weight
                    )

        return prediction

    def finalize_pokemon(self, pokemon_name: str,
                        final_ability: str,
                        final_item: str,
                        final_moves: List[str],
                        final_tera: Optional[str] = None,
                        final_spread: Optional[str] = None):
        """
        Record final confirmed set for a Pokemon (for ML training)

        Args:
            pokemon_name: Pokemon species
            final_ability: Confirmed ability
            final_item: Confirmed item
            final_moves: All 4 moves
            final_tera: Tera type (if revealed)
            final_spread: EV spread (if known)
        """
        if not self.current_battle_context:
            return

        # Get tracking data
        pokemon_data = self.current_battle_context['pokemon_seen'].get(pokemon_name)
        if not pokemon_data:
            return

        prediction = pokemon_data['prediction']

        # Create Pokemon record for ML training
        record = PokemonRecord(
            species=pokemon_name,
            ability=final_ability,
            item=final_item,
            moves=final_moves,
            tera_type=final_tera,
            spread=final_spread,
            revealed_moves=list(prediction.revealed_moves),
            revealed_timing=RevealedTiming(
                first_seen=pokemon_data['first_turn'],
                moves=[]  # TODO: Track actual turn numbers
            ),
            team_context=TeamContext(
                player_lead="Unknown",  # TODO: Track team context
                visible_threats=[],
                team_types={}
            ),
            turn_first_seen=pokemon_data['first_turn'],
            opponent_rating=self.current_battle_context.get('player_rating')
        )

        # Record in battle history
        self.battle_recorder.record_pokemon(record)

    def end_battle(self, winner: Optional[str] = None):
        """
        End current battle and trigger retraining if needed

        Args:
            winner: 'player' or 'opponent'
        """
        if not self.current_battle_context:
            return

        # Save battle
        self.battle_recorder.end_battle(
            winner=winner,
            turn_count=self.current_battle_context.get('turn_number')
        )

        # Check if we should retrain
        num_battles = len(self.battle_recorder.battle_history)
        if self.ml_predictor.should_train(num_battles):
            print(f"\n📊 Retraining models with {num_battles} battles...")
            self._retrain_models()

        # Clear context
        self.current_battle_context = {}

    def _blend_predictions(self, bayesian_pred: SetPrediction,
                          ml_pred: Dict[str, Dict[str, float]],
                          ml_weight: float) -> SetPrediction:
        """
        Blend Bayesian and ML predictions

        Args:
            bayesian_pred: Bayesian prediction
            ml_pred: ML predictions
            ml_weight: Weight for ML (0-1)

        Returns:
            Blended SetPrediction
        """
        bayesian_weight = 1.0 - ml_weight

        # Blend item probabilities
        if 'item' in ml_pred and not bayesian_pred.revealed_item:
            blended_items = {}
            all_items = set(bayesian_pred.item_probs.keys()) | set(ml_pred['item'].keys())

            for item in all_items:
                # Skip if ruled out by game mechanics
                if item in bayesian_pred.impossible_items:
                    continue

                bayesian_prob = bayesian_pred.item_probs.get(item, 0.0)
                ml_prob = ml_pred['item'].get(item, 0.0)

                blended_items[item] = (
                    bayesian_weight * bayesian_prob +
                    ml_weight * ml_prob
                )

            # Normalize
            total = sum(blended_items.values())
            if total > 0:
                bayesian_pred.item_probs = {
                    item: prob / total
                    for item, prob in blended_items.items()
                }

        # Blend move probabilities
        if 'moves' in ml_pred:
            blended_moves = {}
            all_moves = set(bayesian_pred.move_probs.keys()) | set(ml_pred['moves'].keys())

            for move in all_moves:
                # Keep revealed moves at 1.0
                if move in bayesian_pred.revealed_moves:
                    blended_moves[move] = 1.0
                    continue

                bayesian_prob = bayesian_pred.move_probs.get(move, 0.0)
                ml_prob = ml_pred['moves'].get(move, 0.0)

                blended_moves[move] = (
                    bayesian_weight * bayesian_prob +
                    ml_weight * ml_prob
                )

            # Keep top moves only (for efficiency)
            sorted_moves = sorted(blended_moves.items(), key=lambda x: x[1], reverse=True)
            bayesian_pred.move_probs = dict(sorted_moves[:50])  # Top 50 moves

        # Blend tera probabilities
        if 'tera' in ml_pred:
            blended_tera = {}
            all_tera = set(bayesian_pred.tera_probs.keys()) | set(ml_pred['tera'].keys())

            for tera in all_tera:
                bayesian_prob = bayesian_pred.tera_probs.get(tera, 0.0)
                ml_prob = ml_pred['tera'].get(tera, 0.0)

                blended_tera[tera] = (
                    bayesian_weight * bayesian_prob +
                    ml_weight * ml_prob
                )

            # Normalize
            total = sum(blended_tera.values())
            if total > 0:
                bayesian_pred.tera_probs = {
                    tera: prob / total
                    for tera, prob in blended_tera.items()
                }

        return bayesian_pred

    def _calculate_ml_weight(self) -> float:
        """
        Calculate how much to trust ML vs Bayesian

        Returns gradually increasing weight as more data is collected
        """
        num_battles = len(self.battle_recorder.battle_history)

        if num_battles < 50:
            return 0.0  # Pure Bayesian
        elif num_battles < 100:
            return 0.2  # 20% ML
        elif num_battles < 200:
            return 0.4  # 40% ML
        elif num_battles < 500:
            return 0.5  # Equal weight
        elif num_battles < 1000:
            return 0.6  # 60% ML
        else:
            return 0.7  # Heavy ML (but keep Bayesian for unknown scenarios)

    def _retrain_models(self):
        """Retrain ML models on collected battle data"""
        try:
            # Export battle data
            ml_data_file = self.battle_recorder.export_for_ml()

            # Load training data
            import json
            with open(ml_data_file, 'r') as f:
                training_data = json.load(f)

            # Train models
            metrics = self.ml_predictor.train(training_data, verbose=True)

            print(f"✅ Training complete!")
            print(f"   Item accuracy: {metrics['item_accuracy']:.1%}")
            print(f"   Move F1: {metrics['move_f1']:.1%}")
            print(f"   Tera accuracy: {metrics['tera_accuracy']:.1%}")

        except Exception as e:
            print(f"❌ Training failed: {e}")

    def get_statistics(self) -> Dict:
        """
        Get statistics about the hybrid system

        Returns:
            Statistics dictionary
        """
        battle_stats = self.battle_recorder.get_statistics()
        ml_weight = self._calculate_ml_weight()

        return {
            'total_battles': battle_stats['total_battles'],
            'total_pokemon': battle_stats['total_pokemon'],
            'unique_species': battle_stats['unique_species'],
            'ml_trained': self.ml_predictor.is_trained,
            'ml_weight': ml_weight,
            'bayesian_weight': 1.0 - ml_weight,
            'training_history': self.ml_predictor.training_history,
            'most_common_pokemon': battle_stats['most_common']
        }


def main():
    """Test hybrid predictor"""
    from src.data_manager import DataManager

    dm = DataManager()

    if not dm.is_data_available():
        print("Error: Data not available. Run update_data.py first.")
        return

    predictor = HybridSetPredictor(dm)

    print("=" * 60)
    print("Hybrid Set Predictor - Combining Bayesian + ML")
    print("=" * 60)

    # Get statistics
    stats = predictor.get_statistics()
    print(f"\nBattles collected: {stats['total_battles']}")
    print(f"ML trained: {stats['ml_trained']}")
    print(f"Current blend: {stats['ml_weight']:.0%} ML, {stats['bayesian_weight']:.0%} Bayesian")

    # Example prediction
    print("\n" + "-" * 60)
    print("Example: Kingambit prediction")
    print("-" * 60)

    # Set battle context
    predictor.set_battle_context(
        battle_id="test-battle-001",
        tier="gen9ou",
        player_rating=1650
    )

    # Initial prediction
    prediction = predictor.create_initial_prediction("Kingambit")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"\nTop Items:")
    for item, prob in top['items']:
        print(f"  - {item}: {prob:.1%}")

    print(f"\nTop Moves:")
    for move, prob in top['moves']:
        print(f"  - {move}: {prob:.1%}")

    # Simulate move reveal
    print("\n[Turn 3] Kingambit used Sucker Punch")
    prediction = predictor.update_with_move(prediction, "Sucker Punch")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"\nUpdated Item Predictions:")
    for item, prob in top['items']:
        print(f"  - {item}: {prob:.1%}")

    print("\n" + "=" * 60)
    print("\nHow to collect training data:")
    print("1. Use this predictor in real battles")
    print("2. Call finalize_pokemon() when sets are revealed")
    print("3. Call end_battle() when battle ends")
    print("4. Models automatically retrain every 50 battles")
    print("\nAs you collect data, predictions will automatically improve!")


if __name__ == "__main__":
    main()
