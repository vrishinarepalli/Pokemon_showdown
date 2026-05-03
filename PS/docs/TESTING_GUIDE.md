# Complete Testing Guide

## 🧪 How to Test Everything

---

## Quick Start (5 Minutes)

### Step 1: Install Dependencies
```bash
cd /Users/vrishinarepalli/Desktop/PS

# Make sure data is downloaded
python3 update_data.py

# Install ML dependencies (optional)
pip3 install xgboost scikit-learn numpy
```

### Step 2: Run Complete Example
```bash
python3 examples/complete_battle_analysis.py
```

**Expected Output:**
```
╔══════════════════════════════════════════════════════════════════════════╗
║  POKEMON SHOWDOWN - COMPREHENSIVE BATTLE ANALYSIS                        ║
╚══════════════════════════════════════════════════════════════════════════╝

=== TURN 1: Opponent sends out Raging Bolt! ===
[SET PREDICTION]
  ✓ Single ability: Protosynthesis (auto-confirmed)
  ✓ Required item: Booster Energy (Protosynthesis activated without sun)

[DAMAGE CALCULATOR]
  🔴 LETHAL Thunderbolt: 180-212 (70-85%)
  🟢 LOW Dragon Pulse: 45-53 (15-20%)

[NEXT MOVE PREDICTION]
  1. Thunderbolt (45%) - High threat
  2. Calm Mind (30%) - Medium threat
```

✅ **If you see this**, everything is working!

---

## Detailed Testing (By Component)

### 1️⃣ Test Set Predictor (with Auto-Confirmation)

```bash
python3 -c "
from src.set_predictor import SetPredictor
from src.data_manager import DataManager

dm = DataManager()
predictor = SetPredictor(dm)

print('Testing single-ability Pokemon (Raging Bolt):')
print('=' * 60)
prediction = predictor.create_initial_prediction('Raging Bolt')

print(f'Revealed ability: {prediction.revealed_ability}')
print(f'Ability probs: {prediction.ability_probs}')

print('\n\nTesting multi-ability Pokemon (Kingambit):')
print('=' * 60)
prediction2 = predictor.create_initial_prediction('Kingambit')

print(f'Revealed ability: {prediction2.revealed_ability}')
print(f'Ability probs: {prediction2.ability_probs}')
"
```

**Expected Output:**
```
Testing single-ability Pokemon (Raging Bolt):
============================================================
  ✓ Single ability: Protosynthesis (auto-confirmed)
Revealed ability: Protosynthesis
Ability probs: {'Protosynthesis': 1.0}

Testing multi-ability Pokemon (Kingambit):
============================================================
Revealed ability: None
Ability probs: {'Supreme Overlord': 0.959, 'Defiant': 0.040, ...}
```

✅ **Pass:** Raging Bolt auto-confirms, Kingambit shows probabilities

---

### 2️⃣ Test Niche Mechanics Detector

```bash
python3 src/niche_mechanics.py
```

**Expected Output:**
```
=== Niche Mechanics Detector - Test Cases ===

[Test 1] Raging Bolt - Protosynthesis activation
✓ Protosynthesis activated without sun → Booster Energy confirmed
  Confirmed items: {'Booster Energy'}

[Test 2] Ogerpon-Wellspring - Forme change
✓ Ogerpon-Wellspring forme requires Wellspring Mask
  Confirmed items: {'Wellspring Mask'}

[Test 3] Pokemon with Guts - Self-inflicted burn
✓ Guts + self-inflicted burn → very likely Flame Orb
  Probability boosts: {'Flame Orb': 20.0}
```

✅ **Pass:** All 4 test cases work

---

### 3️⃣ Test Damage Calculator

```bash
python3 -c "
from src.damage_calculator import DamageCalculator
from src.data_manager import DataManager

dm = DataManager()
calc = DamageCalculator(dm)

print('Calculating: Raging Bolt Thunderbolt vs Great Tusk')
print('=' * 60)

result = calc.calculate_damage(
    attacker_name='Raging Bolt',
    defender_name='Great Tusk',
    move_name='Thunderbolt',
    attacker_item='Booster Energy',
    attacker_ability='Protosynthesis'
)

print(f'Damage: {result.min_damage}-{result.max_damage}')
print(f'Percent: {result.min_percent:.1f}%-{result.max_percent:.1f}%')
print(f'Guaranteed KO: {result.guaranteed_ko}')
print(f'Possible KO: {result.possible_ko}')
if result.roll_to_ko:
    print(f'KO Chance: {result.roll_to_ko}')
"
```

**Expected Output:**
```
Calculating: Raging Bolt Thunderbolt vs Great Tusk
============================================================
Damage: 120-142
Percent: 45.2%-53.4%
Guaranteed KO: False
Possible KO: False
```

✅ **Pass:** Shows damage range with percentages

---

### 4️⃣ Test Next Move Predictor

```bash
python3 src/next_move_predictor.py
```

**Expected Output:**
```
=== Next Move Predictor Test ===

[Scenario] Opponent: Kingambit vs Your: Great Tusk

Predicted Moves (in order of likelihood):
----------------------------------------------------------------------

1. Sucker Punch (45.2%)
   Threat Level: High
   Reasoning: Sucker Punch deals heavy damage (70-85%); Good offensive pressure

2. Swords Dance (28.5%)
   Threat Level: Medium
   Reasoning: Safe to set up Swords Dance (you're weakened)
```

✅ **Pass:** Shows move predictions with reasoning

---

### 5️⃣ Test Battle Log Parser

```bash
python3 src/battle_log_parser.py
```

**Expected Output:**
```
=== Pokemon Showdown Battle Log Parser Test ===

Parsed Events:
----------------------------------------------------------------------
[Turn 1] p2 switched to Raging Bolt
[Turn 1] Raging Bolt's ability: Protosynthesis
[Turn 2] Raging Bolt used Thunderbolt
[Turn 2] Great Tusk took damage: 65.0%

Tracked Pokemon:
----------------------------------------------------------------------
p2a: Raging Bolt
  HP: 30.0%
  Revealed moves: {'Thunderbolt', 'Calm Mind'}
  Revealed ability: Protosynthesis
  Revealed item: None
```

✅ **Pass:** Parses battle protocol correctly

---

### 6️⃣ Test Auto-Updating Smogon Data

```bash
python3 -c "
from src.data_fetcher import SmogonDataFetcher

fetcher = SmogonDataFetcher()
latest_month = fetcher.get_latest_month()
print(f'Latest month detected: {latest_month}')

# Expected: 2025-10 (or whatever is latest)
"
```

**Expected Output:**
```
  Found latest month: 2025-10
Latest month detected: 2025-10
```

✅ **Pass:** Auto-detects latest Smogon data

---

### 7️⃣ Test ML Training (Optional)

```bash
python3 examples/ml_training_example.py
```

**Expected Output:**
```
[Example 1] Single Battle Simulation
...
[Example 2] Collecting Data from Multiple Battles
...
📊 Retraining models with 60 battles...
Training models on 60 battles...
  Item accuracy: 0.700
  Move F1 score: 0.650
✅ Training complete!
```

✅ **Pass:** ML models train successfully

---

## 🌐 Testing Chrome Extension

### Method 1: Test Locally (No Pokemon Showdown)

Create a test HTML file:

```bash
cat > /Users/vrishinarepalli/Desktop/PS/test_extension.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Extension Test</title>
</head>
<body>
    <h1>Pokemon Showdown Set Predictor Test</h1>
    <div id="output"></div>

    <!-- Load scripts -->
    <script src="extension/content/websocket_interceptor.js"></script>
    <script src="extension/content/battle_observer.js"></script>
    <script src="extension/content/battle_integration.js"></script>

    <!-- Test script -->
    <script>
        console.log('Testing WebSocket Interceptor...');
        const interceptor = new WebSocketInterceptor();

        // Test parsing
        const testMessage = `|switch|p2a: Raging Bolt|Raging Bolt, L50|100/100
|move|p2a: Raging Bolt|Thunderbolt|p1a: Great Tusk
|-damage|p1a: Great Tusk|65/100`;

        const events = interceptor.parseBattleMessage(testMessage);
        console.log('Parsed events:', events);

        document.getElementById('output').innerHTML =
            '<pre>' + JSON.stringify(events, null, 2) + '</pre>';
    </script>
</body>
</html>
EOF

# Open in browser
open /Users/vrishinarepalli/Desktop/PS/test_extension.html
```

**Expected:** Browser shows parsed battle events in console

---

### Method 2: Test on Pokemon Showdown (Live)

1. **Load Extension in Chrome:**
```bash
# Open Chrome
# Go to: chrome://extensions/
# Enable "Developer mode" (top right)
# Click "Load unpacked"
# Select: /Users/vrishinarepalli/Desktop/PS/extension/
```

2. **Go to Pokemon Showdown:**
```
https://play.pokemonshowdown.com/
```

3. **Open DevTools Console:**
```
Right-click → Inspect → Console tab
```

4. **Start a Battle:**
```
Click "Battle!" → "Random Battle"
```

5. **Watch Console:**
```javascript
// You should see:
✓ WebSocket connection intercepted
✓ Battle observer started
Battle event: {type: 'switch', pokemon: 'Raging Bolt'}
Battle event: {type: 'move', move: 'Thunderbolt'}
```

---

### Method 3: Test WebSocket Interception (Manual)

Open Pokemon Showdown, then paste in console:

```javascript
// Test 1: Check if interceptor loaded
if (typeof WebSocketInterceptor !== 'undefined') {
    console.log('✅ WebSocketInterceptor loaded!');
} else {
    console.log('❌ WebSocketInterceptor not loaded');
}

// Test 2: Start interceptor
const interceptor = new WebSocketInterceptor();
interceptor.start((message, isSent) => {
    if (!isSent && message.includes('|')) {
        console.log('📨 Battle message:', message.substring(0, 100));
    }
});

console.log('✅ Interceptor started - start a battle to see messages!');
```

**Expected:** See battle messages logged as you play

---

## 🐛 Troubleshooting

### Problem: "No module named 'src'"

**Solution:**
```bash
cd /Users/vrishinarepalli/Desktop/PS
export PYTHONPATH="${PYTHONPATH}:/Users/vrishinarepalli/Desktop/PS"
python3 examples/complete_battle_analysis.py
```

---

### Problem: "Data not available"

**Solution:**
```bash
cd /Users/vrishinarepalli/Desktop/PS
python3 update_data.py

# Check if data files exist
ls -lh data/usage/
# Should see: gen9ou_usage.json, gen9ou_movesets.json
```

---

### Problem: "ML libraries not installed"

**Solution:**
```bash
pip3 install xgboost scikit-learn numpy

# Or skip ML features (Bayesian still works!)
```

---

### Problem: Chrome Extension not loading

**Solution:**

1. Check manifest.json:
```bash
cat extension/manifest.json
```

2. Make sure files exist:
```bash
ls extension/content/
# Should see: websocket_interceptor.js, battle_integration.js, etc.
```

3. Reload extension:
```
chrome://extensions/ → Click reload icon
```

---

### Problem: "WebSocketInterceptor not defined"

**Solution:**

Update manifest.json to load scripts in correct order:
```json
{
  "content_scripts": [{
    "matches": ["*://play.pokemonshowdown.com/*"],
    "js": [
      "content/websocket_interceptor.js",
      "content/battle_observer.js",
      "content/battle_integration.js"
    ],
    "run_at": "document_start"
  }]
}
```

---

## ✅ Checklist

### Python Components
- [ ] Set predictor works (single-ability auto-confirms)
- [ ] Niche mechanics detector works (all tests pass)
- [ ] Damage calculator works (shows damage ranges)
- [ ] Next move predictor works (shows predictions)
- [ ] Battle log parser works (parses protocol)
- [ ] Auto-update fetches latest Smogon data
- [ ] Complete battle analysis runs successfully

### Chrome Extension
- [ ] Extension loads in Chrome
- [ ] No errors in console
- [ ] WebSocket interceptor captures messages
- [ ] Battle integration initializes
- [ ] Predictions display in console (during battle)

### Integration
- [ ] Can start a battle on Pokemon Showdown
- [ ] See battle events in console
- [ ] Predictions update as moves are revealed
- [ ] Damage calculations appear
- [ ] Next move predictions show

---

## 📊 Success Criteria

| Component | Test | Expected Result | Status |
|-----------|------|-----------------|--------|
| Set Predictor | Single ability | ✓ Protosynthesis (confirmed) | ⬜ |
| Niche Mechanics | Booster Energy | ✓ Confirmed via activation | ⬜ |
| Damage Calc | Thunderbolt calc | 120-142 damage (45-54%) | ⬜ |
| Next Move | Prediction | Shows top 3 moves | ⬜ |
| Battle Parser | Parse protocol | Extracts all events | ⬜ |
| WebSocket | Intercept | Captures messages | ⬜ |
| Integration | Complete flow | All features work together | ⬜ |

---

## 🎯 Quick Test Script

Run everything at once:

```bash
cd /Users/vrishinarepalli/Desktop/PS

# Create test script
cat > test_all.sh << 'EOF'
#!/bin/bash

echo "================================"
echo "TESTING POKEMON SHOWDOWN PREDICTOR"
echo "================================"

echo -e "\n1️⃣ Testing Set Predictor..."
python3 -c "from src.set_predictor import SetPredictor; from src.data_manager import DataManager; dm = DataManager(); p = SetPredictor(dm); pred = p.create_initial_prediction('Raging Bolt')" && echo "✅ PASS" || echo "❌ FAIL"

echo -e "\n2️⃣ Testing Niche Mechanics..."
python3 src/niche_mechanics.py > /dev/null 2>&1 && echo "✅ PASS" || echo "❌ FAIL"

echo -e "\n3️⃣ Testing Damage Calculator..."
python3 -c "from src.damage_calculator import DamageCalculator; from src.data_manager import DataManager; dm = DataManager(); calc = DamageCalculator(dm); calc.calculate_damage('Raging Bolt', 'Great Tusk', 'Thunderbolt')" > /dev/null 2>&1 && echo "✅ PASS" || echo "❌ FAIL"

echo -e "\n4️⃣ Testing Battle Log Parser..."
python3 src/battle_log_parser.py > /dev/null 2>&1 && echo "✅ PASS" || echo "❌ FAIL"

echo -e "\n5️⃣ Testing Complete Integration..."
python3 examples/complete_battle_analysis.py > /dev/null 2>&1 && echo "✅ PASS" || echo "❌ FAIL"

echo -e "\n================================"
echo "TESTING COMPLETE!"
echo "================================"
EOF

chmod +x test_all.sh
./test_all.sh
```

**Expected Output:**
```
================================
TESTING POKEMON SHOWDOWN PREDICTOR
================================

1️⃣ Testing Set Predictor...
✅ PASS

2️⃣ Testing Niche Mechanics...
✅ PASS

3️⃣ Testing Damage Calculator...
✅ PASS

4️⃣ Testing Battle Log Parser...
✅ PASS

5️⃣ Testing Complete Integration...
✅ PASS

================================
TESTING COMPLETE!
================================
```

---

## 🎮 Interactive Testing (Most Fun!)

1. **Start Pokemon Showdown**
2. **Load Extension**
3. **Open Console** (F12)
4. **Start a Battle**
5. **Watch predictions update in real-time!**

You should see output like:
```
=== TURN 1 ===
Opponent switched to: Raging Bolt
✓ Single ability: Protosynthesis (auto-confirmed)
✓ Booster Energy confirmed (Protosynthesis activated)

=== PREDICTION: Raging Bolt ===
Top Items:
  • Booster Energy: 100%
Top Moves:
  • Thunderbolt: 71%
  • Thunderclap: 96%
  • Dragon Pulse: 62%

=== DAMAGE CALCULATOR ===
🔴 Thunderbolt: 70-85% (DANGER)
🟡 Dragon Pulse: 15-20% (LOW)

=== NEXT MOVE PREDICTION ===
1. Thunderbolt (45%) - High threat
2. Calm Mind (30%) - Medium threat
```

---

## Need Help?

Run the comprehensive example:
```bash
python3 examples/complete_battle_analysis.py
```

This shows EVERYTHING working together in a realistic battle scenario!
