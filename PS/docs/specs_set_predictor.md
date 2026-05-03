# Pokemon Showdown Set Predictor - Project Specifications

## Project Overview
A Chrome extension that predicts opponent Pokemon sets in real-time during Pokemon Showdown battles. Uses Smogon usage statistics as a baseline and learns from battle history to provide increasingly accurate predictions.

## Core Concept
During a battle, as information is revealed (moves used, ability shown, item held, damage calculations), the system narrows down the possible sets and provides probability-weighted predictions for:
- **Remaining Moves**: What moves the opponent likely has
- **Item**: What item they're holding (if not revealed)
- **Ability**: What ability they have (if not revealed)
- **EV Spread**: Likely stat distribution
- **Tera Type**: What they might Terastallize into (Gen 9)

## Use Case Example
```
Turn 1: Opponent sends out Kingambit
├─ Initial Prediction (from Smogon data):
│  ├─ 95% Supreme Overlord ability
│  ├─ 50% Leftovers, 21% Black Glasses
│  ├─ 99% Sucker Punch, 91% Swords Dance, 88% Kowtow Cleave
│  └─ Most common: Adamant 0/252/4/0/0/252

Turn 3: Kingambit uses Sucker Punch
├─ Update: Sucker Punch confirmed
└─ Recalculate: Still likely Swords Dance + Kowtow Cleave + Iron Head

Turn 5: Kingambit takes damage, survives with more HP than expected
├─ Damage calc suggests: Leftovers or high HP investment
└─ Update item probability: 75% Leftovers

Turn 7: Kingambit uses Swords Dance
└─ Confirmed moves: Sucker Punch, Swords Dance
    Predicted 4th move: 90% Kowtow Cleave, 80% Iron Head (one of these)
```

---

## System Architecture

### 1. Data Layer
**What We Already Have:**
- ✓ Smogon usage statistics (abilities, items, moves, spreads)
- ✓ 407 Pokemon with detailed moveset data
- ✓ Usage percentages for all components

**What We Need:**
- Battle history database (user's past battles)
- Set matching algorithm
- Bayesian inference engine

### 2. Prediction Engine

#### 2.1 Initial Prediction (Turn 1)
When opponent sends out a Pokemon:
```python
initial_state = {
    "pokemon": "Kingambit",
    "known_moves": [],
    "known_ability": None,
    "known_item": None,
    "predictions": {
        "ability": {"Supreme Overlord": 0.96, "Defiant": 0.04},
        "item": {"Leftovers": 0.50, "Black Glasses": 0.21, ...},
        "moves": {
            "Sucker Punch": 0.99,
            "Swords Dance": 0.91,
            "Kowtow Cleave": 0.88,
            "Iron Head": 0.81,
            ...
        },
        "spreads": {
            "Adamant:0/252/4/0/0/252": 0.16,
            ...
        }
    }
}
```

#### 2.2 Bayesian Update Algorithm
As information is revealed, update probabilities:

**When a move is used:**
```python
# Move is confirmed, probability becomes 1.0
confirmed_moves.add(move_name)

# Update set probabilities based on move correlations
# Example: If Sucker Punch is used, Swords Dance becomes more likely
# (because they're often used together)
```

**When ability is revealed:**
```python
# Ability confirmed
known_ability = ability_name

# Filter out sets that don't have this ability
# Recalculate move probabilities for this specific ability variant
```

**When item is revealed:**
```python
# Item confirmed
known_item = item_name

# Update move correlations
# Example: Choice Scarf → offensive moves more likely
```

**Damage calculation hints:**
```python
# If Pokemon survives/dies from expected damage:
# - Estimate EV investment (bulk vs speed vs offense)
# - Update spread predictions
# - Update item predictions (Leftovers, Assault Vest, etc.)
```

#### 2.3 Game Mechanic Constraints (Hard Rules)

Unlike probabilistic updates, these are **absolute constraints** that immediately rule out impossible items:

**CONSTRAINT 1: Choice Item Detection**
```
IF Pokemon uses 2+ different moves
THEN item CANNOT BE Choice Band/Scarf/Specs
```
- Choice items lock the user into one move
- Example: Kingambit uses Sucker Punch → Swords Dance
- Result: All Choice items eliminated (probability set to 0)

**CONSTRAINT 2: Assault Vest Detection**
```
IF Pokemon uses ANY non-attacking move
THEN item CANNOT BE Assault Vest
```
- Assault Vest prevents all status moves
- Non-attacking moves: Swords Dance, Stealth Rock, Protect, Recover, etc.
- Attacking moves that deal damage: U-turn, Volt Switch, Rapid Spin (Gen 9+)
- Example: Raging Bolt uses Calm Mind
- Result: Assault Vest eliminated

**CONSTRAINT 3: Heavy-Duty Boots Detection**
```
IF Pokemon takes entry hazard damage (Stealth Rock, Spikes)
THEN item CANNOT BE Heavy-Duty Boots
```
- Heavy-Duty Boots prevent all entry hazard damage
- Example: Pokemon switches in and takes 12.5% from Stealth Rock
- Result: Heavy-Duty Boots eliminated

**CONSTRAINT 4: Leftovers/Black Sludge Detection**
```
IF Pokemon heals 1/16 HP at end of turn (without any move)
THEN item VERY LIKELY IS Leftovers or Black Sludge
```
- Passive healing indicates Leftovers/Black Sludge
- Boosts probability to ~90%

**CONSTRAINT 5: Life Orb Detection**
```
IF Pokemon takes 10% recoil damage after attacking
THEN item VERY LIKELY IS Life Orb
```
- Life Orb causes 10% max HP recoil on each attack
- Note: Some moves have natural recoil (Double-Edge, Brave Bird)

**Test Results:**
```
Kingambit Example:
Turn 1: 53% Leftovers, 11% Choice Scarf
Turn 5 (after Sucker Punch + Swords Dance):
  ⚠️  Ruled out Choice Band
  ⚠️  Ruled out Choice Specs
  ⚠️  Ruled out Choice Scarf
  ⚠️  Ruled out Assault Vest
Result: 59% Leftovers (probability redistributed)
```

#### 2.4 Set Correlation Matrix
Build correlation data from Smogon usage:
```python
correlations = {
    "Kingambit": {
        "Sucker Punch + Swords Dance": 0.85,  # Often paired
        "Leftovers + Iron Head": 0.60,
        "Choice Scarf + Low Kick": 0.40,
        ...
    }
}
```

### 3. Learning System

#### 3.1 Battle History Storage
```json
{
  "battle_id": "gen9ou-12345",
  "date": "2025-10-27",
  "opponent": "username",
  "pokemon_seen": [
    {
      "species": "Kingambit",
      "ability": "Supreme Overlord",
      "item": "Leftovers",
      "moves": ["Sucker Punch", "Swords Dance", "Kowtow Cleave", "Iron Head"],
      "tera_type": "Ghost",
      "revealed_turn": {
        "ability": 1,
        "moves": [3, 5, 7, 12],
        "item": 8,
        "tera_type": 15
      }
    }
  ]
}
```

#### 3.2 Personalized Learning
- Track opponent patterns (if you face same players)
- Learn meta-specific trends (ladder rating range)
- Adapt to tier shifts faster than monthly Smogon updates

### 4. Chrome Extension Architecture

#### 4.1 Components
```
extension/
├── manifest.json          # Extension config
├── content/
│   ├── content.js        # Injected into Pokemon Showdown
│   ├── battle_parser.js  # Parses battle log
│   └── ui_overlay.js     # Prediction display
├── background/
│   ├── service_worker.js # Background tasks
│   └── prediction_engine.js
├── popup/
│   ├── popup.html        # Extension popup UI
│   └── popup.js          # Settings, history viewer
└── data/
    ├── smogon_data.json  # Cached usage stats
    └── battle_history.json
```

#### 4.2 Battle Log Parser
Pokemon Showdown battle format:
```
|switch|p2a: Kingambit|Kingambit, L50, M|100/100
|move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
|-damage|p1a: Great Tusk|65/100
|move|p1a: Great Tusk|Close Combat|p2a: Kingambit
|-damage|p2a: Kingambit|20/100
```

Parser extracts:
- Pokemon switches
- Moves used
- Abilities triggered
- Items activated
- Damage dealt/taken
- Status effects

#### 4.3 UI Overlay
Display on Pokemon Showdown page:
```
┌─────────────────────────────┐
│ Opponent: Kingambit         │
├─────────────────────────────┤
│ Ability (95% confident)     │
│ ● Supreme Overlord          │
│                             │
│ Item (75% confident)        │
│ ● Leftovers (75%)           │
│ ○ Black Glasses (15%)       │
│                             │
│ Known Moves                 │
│ ✓ Sucker Punch             │
│ ✓ Swords Dance             │
│                             │
│ Predicted Moves (4th slot)  │
│ ● Kowtow Cleave (90%)      │
│ ● Iron Head (80%)          │
│ ○ Low Kick (25%)           │
│                             │
│ Likely Spread              │
│ ● Adamant 0/252/4/0/0/252  │
└─────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Core Prediction Engine ✓
- [x] Data infrastructure (already complete!)
- [ ] Set prediction algorithm
- [ ] Bayesian update logic
- [ ] Correlation matrix builder

### Phase 2: Battle Log Parser
- [ ] Pokemon Showdown battle log format parser
- [ ] Real-time move/ability/item detection
- [ ] Damage calculation estimator
- [ ] Turn-by-turn state tracking

### Phase 3: Learning System
- [ ] Battle history storage (IndexedDB)
- [ ] Set learning algorithm
- [ ] Opponent pattern recognition
- [ ] Data export/import

### Phase 4: Chrome Extension
- [ ] Manifest V3 extension setup
- [ ] Content script injection
- [ ] UI overlay design
- [ ] Settings page
- [ ] Data sync

### Phase 5: Advanced Features
- [ ] Damage calculator integration
- [ ] Team matchup analysis
- [ ] Predicted set export (Pokemon Showdown format)
- [ ] Statistics dashboard

---

## Technical Stack

### Core Technologies
- **Backend/Engine**: Python (for data processing) or JavaScript (for extension)
- **Chrome Extension**: Manifest V3, JavaScript
- **Storage**: IndexedDB (browser storage)
- **UI Framework**: Vanilla JS or React (lightweight)

### Key Libraries
```json
{
  "extension": [
    "chrome-extension-async",
    "chart.js (for visualizations)"
  ],
  "core": [
    "ml.js or tensorflow.js (optional, for advanced learning)",
    "lodash (utilities)"
  ]
}
```

---

## Prediction Algorithm Details

### Bayesian Inference Formula
```
P(Set|Evidence) = P(Evidence|Set) × P(Set) / P(Evidence)

Where:
- P(Set) = Prior probability (from Smogon usage)
- P(Evidence|Set) = Likelihood (how likely is this evidence given this set)
- P(Set|Evidence) = Posterior probability (updated prediction)
```

### Example Calculation
```python
# Initial: Kingambit sent out
priors = {
    "Set A (SD Sweeper)": 0.60,  # Swords Dance, Sucker Punch, Kowtow, Iron Head
    "Set B (Boots Pivot)": 0.25,  # Sucker Punch, Iron Head, Knock Off, Low Kick
    "Set C (Scarf)": 0.15         # Sucker Punch, Low Kick, Iron Head, Kowtow
}

# Evidence: Used Swords Dance
likelihoods = {
    "Set A": 1.0,   # Has Swords Dance
    "Set B": 0.0,   # Doesn't have Swords Dance
    "Set C": 0.0    # Doesn't have Swords Dance
}

# Update
posteriors = {
    "Set A": 1.0,   # Only possible set
    "Set B": 0.0,
    "Set C": 0.0
}

# Therefore: Likely has Sucker Punch, Kowtow Cleave, Iron Head
```

---

## Data Structure

### Smogon Set Template
```typescript
interface PokemonSet {
  species: string;
  ability: string;
  item: string;
  moves: string[];
  evs: {
    hp: number;
    atk: number;
    def: number;
    spa: number;
    spd: number;
    spe: number;
  };
  nature: string;
  teraType?: string;  // Gen 9
  usage: number;      // Percentage from Smogon
}
```

### Battle State
```typescript
interface BattleState {
  battleId: string;
  turn: number;
  playerTeam: Pokemon[];
  opponentTeam: OpponentPokemon[];
}

interface OpponentPokemon {
  species: string;
  nickname?: string;
  level: number;

  // Known info
  revealedMoves: string[];
  revealedAbility?: string;
  revealedItem?: string;
  revealedTera?: string;

  // Predictions
  predictedSets: SetPrediction[];

  // Observations
  damageObservations: DamageEvent[];
  turnsSeen: number;
}

interface SetPrediction {
  ability: { [ability: string]: number };
  item: { [item: string]: number };
  moves: { [move: string]: number };
  evSpread: { [spread: string]: number };
  confidence: number;
}
```

---

## Privacy & Ethics

### Data Collection
- **Local Only**: All battle data stored locally (IndexedDB)
- **Optional Cloud Sync**: User can opt-in to sync across devices
- **Anonymous**: No personal data sent to servers

### Fair Play
- **Legal Information Only**: Only predicts based on information that's theoretically available
- **No Hacking**: Doesn't access hidden game data
- **Educational Tool**: Helps players learn common sets and improve

---

## Future Enhancements

### Advanced Analytics
- Win rate by set matchup
- Most successful sets against specific threats
- Meta trend detection

### AI/ML Integration
- Neural network for complex set prediction
- Pattern recognition in opponent behavior
- Automatic damage calculator

### Multi-Tier Support
- OU, UU, RU, NU support
- VGC (doubles) format
- Custom format support

### Integration Features
- Export predicted teams to Pokemon Showdown builder
- Share battle analysis with friends
- Replay analysis mode

---

## Success Metrics

### Accuracy Goals
- **Turn 1**: 60% accuracy on full set prediction
- **Turn 5**: 80% accuracy
- **Turn 10**: 95% accuracy

### Performance Goals
- Prediction update: < 100ms
- Extension overhead: < 5% CPU
- Storage: < 50MB for 1000 battles

---

## Current Status
- **Phase**: 1 (Data Infrastructure - Complete, pivoting to Prediction Engine)
- **Data Available**: ✓ 407 Pokemon with detailed sets
- **Next Steps**: Build prediction algorithm and battle parser
- **Target**: Chrome Extension MVP

## Development Timeline

### Week 1-2: Prediction Engine
- Set prediction algorithm
- Bayesian update logic
- Correlation analysis from Smogon data

### Week 3: Battle Parser
- Pokemon Showdown log parser
- Real-time state tracking
- Move/ability detection

### Week 4: Chrome Extension
- Basic extension structure
- Content script injection
- Simple UI overlay

### Week 5-6: Learning & Polish
- Battle history storage
- Learning algorithm
- UI improvements
- Testing on real battles
