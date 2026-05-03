# Machine Learning Architecture for Pokemon Set Predictor

## Overview
This document outlines how to integrate machine learning into the Pokemon Showdown set predictor. The key principle: **the more battle data we collect, the better our predictions become**.

## Hybrid Approach: Bayesian + ML

```
Turn 1 (Cold Start)          Turn 5+ (Warm Model)
┌──────────────┐            ┌──────────────┐
│ Smogon Data  │            │ Smogon Data  │
│   (Prior)    │            │   (Prior)    │
└──────┬───────┘            └──────┬───────┘
       │                           │
       ▼                           ▼
┌──────────────┐            ┌──────────────┐
│   Bayesian   │  80% ────▶ │   Bayesian   │ 40%
│  Inference   │            │  Inference   │
└──────────────┘            └──────┬───────┘
                                   │
                            ┌──────┴───────┐
                            │              │
                            ▼              ▼
                     ┌──────────┐   ┌──────────┐
                     │ ML Model │60%│  Learned │
                     │(Historical│  │ Patterns │
                     │  Battles) │  │          │
                     └──────────┘   └──────────┘
```

### Strategy
1. **Start**: Use pure Bayesian inference (current implementation)
2. **Collect**: Store every battle's revealed sets
3. **Learn**: Train ML models on collected data
4. **Blend**: Combine Bayesian priors with ML predictions

---

## Data Collection Schema

### 1. Battle History Database
Store every complete set you see in battles:

```python
{
  "battle_id": "gen9ou-1234567890",
  "timestamp": "2025-10-27T14:30:00Z",
  "tier": "gen9ou",
  "player_rating": 1650,
  "opponent": {
    "username": "player123",
    "rating": 1680,
    "team": [
      {
        "species": "Kingambit",
        "ability": "Supreme Overlord",
        "item": "Leftovers",
        "moves": ["Sucker Punch", "Swords Dance", "Kowtow Cleave", "Iron Head"],
        "tera_type": "Ghost",
        "spread": "Adamant:0/252/4/0/0/252",

        # What we learned during battle
        "revealed_turn": {
          "first_seen": 1,
          "moves": [3, 5, 7, 12],  # Turn numbers
          "ability": 3,
          "item": 8,
          "tera_type": null  # Never revealed
        },

        # Context when first seen
        "team_preview_context": {
          "player_lead": "Great Tusk",
          "visible_threats": ["Kyurem", "Zapdos", "Garganacl"]
        }
      }
    ]
  }
}
```

---

## Feature Engineering

### Input Features (when predicting)
Transform battle state into ML features:

```python
features = {
    # Pokemon identity
    "pokemon": "Kingambit",  # One-hot encoded
    "tier": "gen9ou",

    # Revealed information
    "revealed_moves": [1, 0, 1, 0, ...],  # Binary vector for each possible move
    "revealed_ability": "Supreme Overlord",  # One-hot encoded
    "revealed_item": None,
    "move_count": 2,  # How many moves seen

    # Battle context
    "turn_number": 5,
    "opponent_rating": 1680,
    "player_lead": "Great Tusk",  # One-hot encoded
    "weather_active": None,
    "terrain_active": None,
    "hazards": ["Stealth Rock"],

    # Team composition features
    "team_has_kingambit": True,
    "team_has_setup_sweeper": True,
    "opposing_team_types": [0.33, 0.17, ...],  # Type distribution

    # Statistical features from Smogon
    "smogon_move_prob_sum": 2.87,  # Sum of Smogon probs for revealed moves
    "smogon_top_set_match": 0.85,  # Does it match most common set?

    # Correlation features
    "move_pairs": [
        ("Sucker Punch", "Swords Dance"),  # Observed pairs
    ],
}
```

### Output Targets (what we predict)

```python
targets = {
    # Item prediction (multi-class classification)
    "item": "Leftovers",  # 100+ possible items

    # Remaining moves (multi-label classification)
    "has_kowtow_cleave": True,
    "has_iron_head": True,
    "has_low_kick": False,
    # ... for all possible moves

    # Spread prediction (regression or classification)
    "spread_category": "Adamant:0/252/4/0/0/252",

    # Tera type (multi-class)
    "tera_type": "Ghost",
}
```

---

## ML Model Options

### Option 1: Gradient Boosting (Recommended for Start)
**Best for**: Tabular data, interpretable, works with less data

```python
# Using XGBoost or LightGBM
import xgboost as xgb
from sklearn.multioutput import MultiOutputClassifier

# Separate models for each prediction task
item_model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1
)

move_model = MultiOutputClassifier(
    xgb.XGBClassifier(n_estimators=100)
)

tera_model = xgb.XGBClassifier(n_estimators=100)
```

**Pros**:
- Works well with small datasets (100+ battles)
- Fast training and prediction
- Feature importance → understand what matters
- No GPU needed

**Cons**:
- Doesn't capture complex patterns as well as neural networks
- Requires manual feature engineering

### Option 2: Neural Network
**Best for**: Large datasets (1000+ battles), complex patterns

```python
import tensorflow as tf

# Multi-task neural network
inputs = tf.keras.Input(shape=(feature_dim,))

# Shared layers
x = tf.keras.layers.Dense(256, activation='relu')(inputs)
x = tf.keras.layers.Dropout(0.3)(x)
x = tf.keras.layers.Dense(128, activation='relu')(x)
x = tf.keras.layers.Dropout(0.3)(x)

# Task-specific heads
item_output = tf.keras.layers.Dense(num_items, activation='softmax', name='item')(x)
move_output = tf.keras.layers.Dense(num_moves, activation='sigmoid', name='moves')(x)
tera_output = tf.keras.layers.Dense(18, activation='softmax', name='tera')(x)

model = tf.keras.Model(
    inputs=inputs,
    outputs=[item_output, move_output, tera_output]
)

model.compile(
    optimizer='adam',
    loss={
        'item': 'sparse_categorical_crossentropy',
        'moves': 'binary_crossentropy',
        'tera': 'sparse_categorical_crossentropy'
    },
    loss_weights={'item': 1.0, 'moves': 0.5, 'tera': 0.8}
)
```

**Pros**:
- Learns complex patterns automatically
- Can improve indefinitely with more data
- End-to-end learning

**Cons**:
- Needs more data (1000+ battles)
- Slower training
- Less interpretable

### Option 3: Ensemble Approach (Best Overall)
Combine multiple models:

```python
predictions = {
    'item': 0.4 * bayesian + 0.3 * xgboost + 0.3 * neural,
    'moves': 0.3 * bayesian + 0.4 * xgboost + 0.3 * neural,
}
```

---

## Implementation Phases

### Phase 1: Data Collection (Weeks 1-2)
**Goal**: Build battle history database

```python
# Add to existing SetPredictor class

class BattleRecorder:
    def __init__(self):
        self.current_battle = None
        self.battle_history = []

    def start_battle(self, battle_id, tier, player_rating):
        self.current_battle = {
            'battle_id': battle_id,
            'timestamp': datetime.now().isoformat(),
            'tier': tier,
            'player_rating': player_rating,
            'opponent_pokemon': []
        }

    def record_pokemon(self, prediction: SetPrediction, final_set: dict):
        """Called when battle ends and full set is revealed"""
        self.current_battle['opponent_pokemon'].append({
            'species': prediction.pokemon,
            'ability': final_set['ability'],
            'item': final_set['item'],
            'moves': final_set['moves'],
            'revealed_moves': list(prediction.revealed_moves),
            'revealed_turn': {
                'moves': [...]  # Turn numbers
            }
        })

    def end_battle(self):
        """Save battle to database"""
        self.battle_history.append(self.current_battle)
        self.save_to_disk()
```

**Action Items**:
- ✓ Already have SetPrediction tracking
- Add BattleRecorder class
- Store battles to JSON/SQLite
- **Target**: Collect 50-100 battles before training

### Phase 2: Feature Engineering (Week 3)
**Goal**: Convert battles to ML features

```python
class FeatureExtractor:
    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.pokemon_encoder = LabelEncoder()
        self.item_encoder = LabelEncoder()
        # ... more encoders

    def extract_features(self, prediction: SetPrediction,
                        battle_context: dict) -> np.ndarray:
        """Convert prediction state to feature vector"""

        features = []

        # 1. Pokemon identity (one-hot)
        pokemon_vec = self.pokemon_encoder.transform([prediction.pokemon])
        features.extend(pokemon_vec)

        # 2. Revealed moves (binary vector)
        move_vec = np.zeros(len(ALL_MOVES))
        for move in prediction.revealed_moves:
            if move in MOVE_TO_INDEX:
                move_vec[MOVE_TO_INDEX[move]] = 1
        features.extend(move_vec)

        # 3. Smogon probabilities (use existing data!)
        features.append(max(prediction.move_probs.values()))
        features.append(len(prediction.revealed_moves))

        # 4. Battle context
        features.append(battle_context['turn_number'] / 20.0)  # Normalized
        features.append(battle_context['opponent_rating'] / 2000.0)

        # 5. Team composition
        team_types = self._get_team_type_distribution(battle_context['team'])
        features.extend(team_types)

        return np.array(features)

    def extract_targets(self, final_set: dict) -> dict:
        """Convert final revealed set to target labels"""
        return {
            'item': self.item_encoder.transform([final_set['item']])[0],
            'moves': self._moves_to_binary(final_set['moves']),
            'tera': self.tera_encoder.transform([final_set['tera_type']])[0]
        }
```

### Phase 3: Model Training (Week 4)
**Goal**: Train initial ML models

```python
class MLPredictor:
    def __init__(self):
        self.item_model = None
        self.move_model = None
        self.is_trained = False
        self.min_battles_required = 50

    def train(self, battle_history: List[dict]):
        """Train models on collected battles"""

        if len(battle_history) < self.min_battles_required:
            print(f"Need {self.min_battles_required} battles, have {len(battle_history)}")
            return False

        # Extract features and targets
        X, y_item, y_moves, y_tera = self._prepare_training_data(battle_history)

        # Split train/validation
        X_train, X_val, y_train, y_val = train_test_split(X, y_item, test_size=0.2)

        # Train item predictor
        print("Training item predictor...")
        self.item_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            eval_metric='mlogloss'
        )
        self.item_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            early_stopping_rounds=10,
            verbose=True
        )

        # Train move predictor
        print("Training move predictor...")
        self.move_model = MultiOutputClassifier(
            xgb.XGBClassifier(n_estimators=100)
        )
        self.move_model.fit(X_train, y_moves_train)

        self.is_trained = True
        return True

    def predict(self, features: np.ndarray) -> dict:
        """Predict item and moves"""
        if not self.is_trained:
            return None

        # Get probability distributions
        item_probs = self.item_model.predict_proba(features)[0]
        move_probs = self.move_model.predict_proba(features)

        return {
            'item': dict(zip(self.item_encoder.classes_, item_probs)),
            'moves': dict(zip(ALL_MOVES, move_probs))
        }
```

### Phase 4: Hybrid System (Week 5)
**Goal**: Blend Bayesian + ML predictions

```python
class HybridSetPredictor(SetPredictor):
    def __init__(self, data_manager):
        super().__init__(data_manager)
        self.ml_predictor = MLPredictor()
        self.feature_extractor = FeatureExtractor(data_manager)
        self.battle_recorder = BattleRecorder()

        # Load trained models if available
        self.ml_predictor.load_models()

    def create_initial_prediction(self, pokemon_name: str,
                                 battle_context: dict = None) -> SetPrediction:
        """Enhanced with ML"""

        # 1. Get Bayesian prior (existing code)
        prediction = super().create_initial_prediction(pokemon_name)

        # 2. If ML model is trained, blend predictions
        if self.ml_predictor.is_trained and battle_context:
            features = self.feature_extractor.extract_features(prediction, battle_context)
            ml_predictions = self.ml_predictor.predict(features)

            # Blend Bayesian and ML
            prediction = self._blend_predictions(
                prediction,
                ml_predictions,
                ml_weight=self._calculate_ml_weight()
            )

        return prediction

    def _blend_predictions(self, bayesian_pred: SetPrediction,
                          ml_pred: dict,
                          ml_weight: float) -> SetPrediction:
        """Combine Bayesian and ML predictions"""

        bayesian_weight = 1.0 - ml_weight

        # Blend item probabilities
        blended_items = {}
        all_items = set(bayesian_pred.item_probs.keys()) | set(ml_pred['item'].keys())

        for item in all_items:
            bayesian_prob = bayesian_pred.item_probs.get(item, 0.0)
            ml_prob = ml_pred['item'].get(item, 0.0)
            blended_items[item] = (
                bayesian_weight * bayesian_prob +
                ml_weight * ml_prob
            )

        # Normalize
        total = sum(blended_items.values())
        bayesian_pred.item_probs = {
            item: prob / total
            for item, prob in blended_items.items()
        }

        # Same for moves, tera types...

        return bayesian_pred

    def _calculate_ml_weight(self) -> float:
        """Determine how much to trust ML vs Bayesian"""

        num_battles = len(self.battle_recorder.battle_history)

        if num_battles < 50:
            return 0.0  # Pure Bayesian
        elif num_battles < 200:
            return 0.3  # Mostly Bayesian
        elif num_battles < 500:
            return 0.5  # Equal weight
        elif num_battles < 1000:
            return 0.7  # Mostly ML
        else:
            return 0.8  # Heavy ML (but keep Bayesian for unknown scenarios)
```

---

## Training Pipeline

### Continuous Learning Loop

```python
# After each battle ends
def on_battle_end(battle_id: str):
    # 1. Record battle
    final_sets = parse_battle_replay(battle_id)
    battle_recorder.record_battle(final_sets)

    # 2. Check if we should retrain
    if should_retrain():
        print("Retraining models with new data...")
        ml_predictor.train(battle_recorder.get_all_battles())
        ml_predictor.save_models()

def should_retrain() -> bool:
    """Retrain every 50 new battles"""
    num_battles = len(battle_recorder.battle_history)
    last_train_count = ml_predictor.last_train_battle_count

    return (num_battles - last_train_count) >= 50
```

---

## Expected Performance

### Accuracy Progression

| Battles Collected | Method | Item Accuracy | Move Accuracy |
|-------------------|--------|---------------|---------------|
| 0-50 | Pure Bayesian | 65% | 70% |
| 50-200 | Hybrid (30% ML) | 70% | 75% |
| 200-500 | Hybrid (50% ML) | 75% | 80% |
| 500-1000 | Hybrid (70% ML) | 80% | 85% |
| 1000+ | Hybrid (80% ML) | 85%+ | 90%+ |

### Why ML Helps

1. **Learns meta shifts**: Adapts faster than monthly Smogon updates
2. **Context-aware**: Understands team compositions, rating ranges
3. **Sequence patterns**: Recognizes move reveal orders (e.g., "If they show Sucker Punch first, likely offensive set")
4. **Opponent patterns**: Can detect player tendencies if facing same opponent
5. **Rare sets**: Builds knowledge of uncommon but viable sets

---

## Storage Requirements

- **Per battle**: ~2-5 KB (JSON)
- **1000 battles**: ~3 MB
- **10,000 battles**: ~30 MB
- **Model files**: 10-50 MB (XGBoost) or 50-200 MB (Neural Network)

Total: Reasonable for browser extension (IndexedDB limit is 50+ MB per origin)

---

## Next Steps

1. **Implement BattleRecorder class** (add to src/set_predictor.py)
2. **Collect data**: Use extension in real battles
3. **Start simple**: Train XGBoost after 50 battles
4. **Iterate**: Monitor accuracy, tune features
5. **Scale up**: Add neural network when you have 1000+ battles

The beauty: **Start with Bayesian now, ML automatically kicks in as data grows!**
