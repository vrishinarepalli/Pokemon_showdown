"""
Machine Learning Set Predictor
Uses collected battle history to predict Pokemon sets
"""
from typing import Dict, List, Optional, Tuple
import numpy as np
import json
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass

# Try to import ML libraries, gracefully handle if not installed
try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.multioutput import MultiOutputClassifier
    from sklearn.metrics import accuracy_score, f1_score
    HAS_ML_LIBS = True
except ImportError:
    HAS_ML_LIBS = False
    print("Warning: ML libraries not installed. Install with: pip install xgboost scikit-learn")


@dataclass
class MLConfig:
    """Configuration for ML models"""
    min_battles_required: int = 50
    retrain_interval: int = 50  # Retrain every N new battles
    test_size: float = 0.2
    random_state: int = 42

    # XGBoost parameters
    n_estimators: int = 100
    max_depth: int = 6
    learning_rate: float = 0.1


class FeatureExtractor:
    """Extract ML features from battle state"""

    def __init__(self, data_manager):
        """
        Initialize feature extractor

        Args:
            data_manager: DataManager with Pokemon data
        """
        self.data_manager = data_manager

        # Encoders (will be fitted during training)
        self.pokemon_encoder = None
        self.item_encoder = None
        self.ability_encoder = None
        self.move_encoder = None
        self.tera_encoder = None

        # Feature indices
        self.all_moves = []
        self.move_to_index = {}

    def fit_encoders(self, battle_records: List[dict]):
        """
        Fit label encoders on training data

        Args:
            battle_records: List of battle records
        """
        if not HAS_ML_LIBS:
            raise RuntimeError("ML libraries not installed")

        # Collect all unique values
        all_pokemon = set()
        all_items = set()
        all_abilities = set()
        all_moves = set()
        all_tera = set()

        for record in battle_records:
            all_pokemon.add(record['pokemon'])
            all_items.add(record['actual_item'])
            all_abilities.add(record['actual_ability'])
            all_moves.update(record['actual_moves'])
            all_moves.update(record['revealed_moves'])
            if record['actual_tera']:
                all_tera.add(record['actual_tera'])

        # Fit encoders
        self.pokemon_encoder = LabelEncoder()
        self.pokemon_encoder.fit(list(all_pokemon))

        self.item_encoder = LabelEncoder()
        self.item_encoder.fit(list(all_items))

        self.ability_encoder = LabelEncoder()
        self.ability_encoder.fit(list(all_abilities))

        self.tera_encoder = LabelEncoder()
        self.tera_encoder.fit(list(all_tera) if all_tera else ['Normal'])

        # Create move index
        self.all_moves = sorted(list(all_moves))
        self.move_to_index = {move: i for i, move in enumerate(self.all_moves)}

    def extract_features(self, pokemon: str, revealed_moves: List[str],
                        revealed_ability: Optional[str],
                        turn_number: int,
                        opponent_rating: Optional[int] = 1500,
                        smogon_data: Optional[dict] = None) -> np.ndarray:
        """
        Extract features for prediction

        Args:
            pokemon: Pokemon species
            revealed_moves: List of revealed moves
            revealed_ability: Revealed ability (if any)
            turn_number: Current turn number
            opponent_rating: Opponent's rating
            smogon_data: Smogon usage data for this Pokemon

        Returns:
            Feature vector
        """
        if not HAS_ML_LIBS:
            raise RuntimeError("ML libraries not installed")

        features = []

        # 1. Pokemon identity (encoded)
        try:
            pokemon_encoded = self.pokemon_encoder.transform([pokemon])[0]
        except ValueError:
            # Unknown Pokemon, use -1
            pokemon_encoded = -1
        features.append(pokemon_encoded)

        # 2. Revealed moves (binary vector)
        move_vector = np.zeros(len(self.all_moves))
        for move in revealed_moves:
            if move in self.move_to_index:
                move_vector[self.move_to_index[move]] = 1
        features.extend(move_vector)

        # 3. Number of revealed moves
        features.append(len(revealed_moves))

        # 4. Turn number (normalized)
        features.append(turn_number / 20.0)

        # 5. Opponent rating (normalized)
        features.append((opponent_rating or 1500) / 2000.0)

        # 6. Smogon-based features
        if smogon_data:
            # Sum of Smogon probabilities for revealed moves
            move_prob_sum = sum(
                smogon_data.get('moves', {}).get(move, 0.0)
                for move in revealed_moves
            )
            features.append(move_prob_sum / 100.0)  # Normalize

            # Entropy of item distribution (lower = more certain)
            item_probs = list(smogon_data.get('items', {}).values())
            if item_probs:
                item_probs = np.array(item_probs) / 100.0
                item_probs = item_probs / item_probs.sum()
                entropy = -np.sum(item_probs * np.log(item_probs + 1e-10))
                features.append(entropy)
            else:
                features.append(0.0)
        else:
            features.append(0.0)
            features.append(0.0)

        # 7. Revealed ability (encoded)
        if revealed_ability:
            try:
                ability_encoded = self.ability_encoder.transform([revealed_ability])[0]
            except ValueError:
                ability_encoded = -1
        else:
            ability_encoded = -1
        features.append(ability_encoded)

        return np.array(features)

    def extract_target_item(self, item: str) -> int:
        """Extract target label for item"""
        try:
            return self.item_encoder.transform([item])[0]
        except ValueError:
            return -1

    def extract_target_moves(self, moves: List[str]) -> np.ndarray:
        """Extract target labels for moves (multi-label)"""
        target = np.zeros(len(self.all_moves))
        for move in moves:
            if move in self.move_to_index:
                target[self.move_to_index[move]] = 1
        return target

    def extract_target_tera(self, tera: Optional[str]) -> int:
        """Extract target label for tera type"""
        if not tera:
            return 0
        try:
            return self.tera_encoder.transform([tera])[0]
        except ValueError:
            return 0


class MLPredictor:
    """Machine learning set predictor"""

    def __init__(self, data_manager, config: MLConfig = None):
        """
        Initialize ML predictor

        Args:
            data_manager: DataManager with Pokemon data
            config: ML configuration
        """
        self.data_manager = data_manager
        self.config = config or MLConfig()
        self.feature_extractor = FeatureExtractor(data_manager)

        # Models
        self.item_model = None
        self.move_model = None
        self.tera_model = None

        self.is_trained = False
        self.last_train_battle_count = 0
        self.training_history = []

        # Model storage
        self.model_dir = Path(__file__).parent.parent / "data" / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def should_train(self, num_battles: int) -> bool:
        """
        Check if models should be trained/retrained

        Args:
            num_battles: Total number of battles collected

        Returns:
            True if should train
        """
        if num_battles < self.config.min_battles_required:
            return False

        if not self.is_trained:
            return True

        # Retrain every N battles
        return (num_battles - self.last_train_battle_count) >= self.config.retrain_interval

    def train(self, battle_records: List[dict], verbose: bool = True) -> dict:
        """
        Train ML models on battle history

        Args:
            battle_records: List of battle records
            verbose: Print training progress

        Returns:
            Training metrics
        """
        if not HAS_ML_LIBS:
            raise RuntimeError("ML libraries not installed. Install with: pip install xgboost scikit-learn")

        if len(battle_records) < self.config.min_battles_required:
            raise ValueError(f"Need at least {self.config.min_battles_required} battles")

        if verbose:
            print(f"Training models on {len(battle_records)} battles...")

        # Fit encoders
        self.feature_extractor.fit_encoders(battle_records)

        # Extract features and targets
        X, y_item, y_moves, y_tera = self._prepare_training_data(battle_records)

        if verbose:
            print(f"Feature dimension: {X.shape[1]}")
            print(f"Training samples: {X.shape[0]}")

        # Split train/validation
        X_train, X_val, y_item_train, y_item_val = train_test_split(
            X, y_item,
            test_size=self.config.test_size,
            random_state=self.config.random_state
        )

        _, _, y_moves_train, y_moves_val = train_test_split(
            X, y_moves,
            test_size=self.config.test_size,
            random_state=self.config.random_state
        )

        _, _, y_tera_train, y_tera_val = train_test_split(
            X, y_tera,
            test_size=self.config.test_size,
            random_state=self.config.random_state
        )

        metrics = {}

        # Train item predictor
        if verbose:
            print("\nTraining item predictor...")
        self.item_model = xgb.XGBClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            eval_metric='mlogloss',
            random_state=self.config.random_state
        )
        self.item_model.fit(X_train, y_item_train)

        # Evaluate
        y_pred = self.item_model.predict(X_val)
        metrics['item_accuracy'] = accuracy_score(y_item_val, y_pred)
        if verbose:
            print(f"  Item accuracy: {metrics['item_accuracy']:.3f}")

        # Train move predictor (one model per move - simpler than multi-output)
        if verbose:
            print("\nTraining move predictor...")
        self.move_model = MultiOutputClassifier(
            xgb.XGBClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                random_state=self.config.random_state
            )
        )
        self.move_model.fit(X_train, y_moves_train)

        # Evaluate (F1 score for multi-label)
        y_pred = self.move_model.predict(X_val)
        metrics['move_f1'] = f1_score(y_moves_val, y_pred, average='macro', zero_division=0)
        if verbose:
            print(f"  Move F1 score: {metrics['move_f1']:.3f}")

        # Train tera predictor
        if verbose:
            print("\nTraining tera type predictor...")
        self.tera_model = xgb.XGBClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            random_state=self.config.random_state
        )
        self.tera_model.fit(X_train, y_tera_train)

        # Evaluate
        y_pred = self.tera_model.predict(X_val)
        metrics['tera_accuracy'] = accuracy_score(y_tera_val, y_pred)
        if verbose:
            print(f"  Tera accuracy: {metrics['tera_accuracy']:.3f}")

        self.is_trained = True
        self.last_train_battle_count = len(battle_records)
        self.training_history.append(metrics)

        # Save models
        self.save_models()

        if verbose:
            print("\nTraining complete!")

        return metrics

    def predict(self, pokemon: str, revealed_moves: List[str],
               revealed_ability: Optional[str],
               turn_number: int,
               opponent_rating: Optional[int] = 1500) -> Optional[Dict[str, Dict[str, float]]]:
        """
        Predict set components using ML

        Args:
            pokemon: Pokemon species
            revealed_moves: List of revealed moves
            revealed_ability: Revealed ability (if any)
            turn_number: Current turn number
            opponent_rating: Opponent's rating

        Returns:
            Dictionary with probability distributions
        """
        if not self.is_trained:
            return None

        # Get Smogon data for features
        smogon_data = self.data_manager.get_pokemon_moveset(pokemon, "gen9ou")

        # Extract features
        features = self.feature_extractor.extract_features(
            pokemon, revealed_moves, revealed_ability,
            turn_number, opponent_rating, smogon_data
        )
        features = features.reshape(1, -1)

        predictions = {}

        # Predict item
        item_probs = self.item_model.predict_proba(features)[0]
        predictions['item'] = dict(zip(
            self.feature_extractor.item_encoder.classes_,
            item_probs
        ))

        # Predict moves
        move_probs = self.move_model.predict_proba(features)
        # move_probs is a list of arrays (one per move)
        # Extract probability of class 1 (has move) for each move
        move_pred_dict = {}
        for i, move in enumerate(self.feature_extractor.all_moves):
            if hasattr(move_probs[i], '__getitem__'):
                # Binary classifier returns [prob_0, prob_1]
                prob = move_probs[i][0][1] if len(move_probs[i][0]) > 1 else move_probs[i][0][0]
                move_pred_dict[move] = float(prob)

        predictions['moves'] = move_pred_dict

        # Predict tera
        tera_probs = self.tera_model.predict_proba(features)[0]
        predictions['tera'] = dict(zip(
            self.feature_extractor.tera_encoder.classes_,
            tera_probs
        ))

        return predictions

    def _prepare_training_data(self, battle_records: List[dict]) -> Tuple[np.ndarray, ...]:
        """Prepare training data from battle records"""
        X_list = []
        y_item_list = []
        y_moves_list = []
        y_tera_list = []

        for record in battle_records:
            # Extract features
            smogon_data = self.data_manager.get_pokemon_moveset(record['pokemon'], record['tier'])

            features = self.feature_extractor.extract_features(
                pokemon=record['pokemon'],
                revealed_moves=record['revealed_moves'],
                revealed_ability=None,  # Not always available in training data
                turn_number=record['turn_first_seen'],
                opponent_rating=record.get('rating'),
                smogon_data=smogon_data
            )

            # Extract targets
            target_item = self.feature_extractor.extract_target_item(record['actual_item'])
            target_moves = self.feature_extractor.extract_target_moves(record['actual_moves'])
            target_tera = self.feature_extractor.extract_target_tera(record['actual_tera'])

            if target_item >= 0:  # Skip if item is unknown
                X_list.append(features)
                y_item_list.append(target_item)
                y_moves_list.append(target_moves)
                y_tera_list.append(target_tera)

        return (
            np.array(X_list),
            np.array(y_item_list),
            np.array(y_moves_list),
            np.array(y_tera_list)
        )

    def save_models(self):
        """Save trained models to disk"""
        if not self.is_trained:
            return

        # Save XGBoost models
        self.item_model.save_model(str(self.model_dir / "item_model.json"))
        self.tera_model.save_model(str(self.model_dir / "tera_model.json"))

        # Save move model (pickle for MultiOutputClassifier)
        import pickle
        with open(self.model_dir / "move_model.pkl", 'wb') as f:
            pickle.dump(self.move_model, f)

        # Save encoders
        with open(self.model_dir / "encoders.json", 'w') as f:
            json.dump({
                'pokemon': list(self.feature_extractor.pokemon_encoder.classes_),
                'items': list(self.feature_extractor.item_encoder.classes_),
                'abilities': list(self.feature_extractor.ability_encoder.classes_),
                'moves': self.feature_extractor.all_moves,
                'tera': list(self.feature_extractor.tera_encoder.classes_)
            }, f, indent=2)

        # Save training history
        with open(self.model_dir / "training_history.json", 'w') as f:
            json.dump({
                'history': self.training_history,
                'last_train_battle_count': self.last_train_battle_count
            }, f, indent=2)

        print(f"Models saved to {self.model_dir}")

    def load_models(self) -> bool:
        """
        Load trained models from disk

        Returns:
            True if models loaded successfully
        """
        try:
            # Load encoders first
            with open(self.model_dir / "encoders.json", 'r') as f:
                encoder_data = json.load(f)

            # Recreate encoders
            self.feature_extractor.pokemon_encoder = LabelEncoder()
            self.feature_extractor.pokemon_encoder.classes_ = np.array(encoder_data['pokemon'])

            self.feature_extractor.item_encoder = LabelEncoder()
            self.feature_extractor.item_encoder.classes_ = np.array(encoder_data['items'])

            self.feature_extractor.ability_encoder = LabelEncoder()
            self.feature_extractor.ability_encoder.classes_ = np.array(encoder_data['abilities'])

            self.feature_extractor.tera_encoder = LabelEncoder()
            self.feature_extractor.tera_encoder.classes_ = np.array(encoder_data['tera'])

            self.feature_extractor.all_moves = encoder_data['moves']
            self.feature_extractor.move_to_index = {
                move: i for i, move in enumerate(encoder_data['moves'])
            }

            # Load models
            self.item_model = xgb.XGBClassifier()
            self.item_model.load_model(str(self.model_dir / "item_model.json"))

            self.tera_model = xgb.XGBClassifier()
            self.tera_model.load_model(str(self.model_dir / "tera_model.json"))

            import pickle
            with open(self.model_dir / "move_model.pkl", 'rb') as f:
                self.move_model = pickle.load(f)

            # Load training history
            with open(self.model_dir / "training_history.json", 'r') as f:
                history_data = json.load(f)
                self.training_history = history_data['history']
                self.last_train_battle_count = history_data['last_train_battle_count']

            self.is_trained = True
            print(f"Models loaded from {self.model_dir}")
            return True

        except Exception as e:
            print(f"Could not load models: {e}")
            return False


def main():
    """Test ML predictor"""
    from src.data_manager import DataManager

    if not HAS_ML_LIBS:
        print("Please install ML libraries: pip install xgboost scikit-learn")
        return

    dm = DataManager()
    predictor = MLPredictor(dm)

    print("ML Predictor initialized")
    print(f"Minimum battles required: {predictor.config.min_battles_required}")
    print("\nTo train models:")
    print("1. Collect battle data using BattleRecorder")
    print("2. Export data with recorder.export_for_ml()")
    print("3. Load data and call predictor.train(battle_records)")


if __name__ == "__main__":
    main()
