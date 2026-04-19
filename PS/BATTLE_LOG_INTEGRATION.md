# Battle Log Integration Guide

## ❌ No Webscraping Needed!

For a Chrome extension, you **don't need to webscrape**. Pokemon Showdown runs in the browser, so you can directly access battle data using these methods:

---

## 3 Methods to Get Battle Data

### ✅ Method 1: WebSocket Interception (RECOMMENDED)
**Accuracy:** ⭐⭐⭐⭐⭐
**Difficulty:** ⭐⭐⭐⭐
**Performance:** ⭐⭐⭐⭐⭐

**Pros:**
- Gets raw Pokemon Showdown protocol
- Most accurate (exact data)
- Catches everything instantly
- No parsing HTML needed

**How it works:**
```javascript
// Intercept WebSocket messages
const interceptor = new WebSocketInterceptor();
interceptor.start((message, isSent) => {
    // message contains raw protocol:
    // |switch|p2a: Raging Bolt|Raging Bolt, L50|100/100
    // |move|p2a: Raging Bolt|Thunderbolt|p1a: Great Tusk
    // |-damage|p1a: Great Tusk|65/100

    const events = interceptor.parseBattleMessage(message);
    // → { type: 'move', pokemon: 'Raging Bolt', move: 'Thunderbolt' }
});
```

**Files:**
- `extension/content/websocket_interceptor.js`

---

### ✅ Method 2: DOM Observation (FALLBACK)
**Accuracy:** ⭐⭐⭐
**Difficulty:** ⭐⭐
**Performance:** ⭐⭐⭐

**Pros:**
- Simple to implement
- Works if WebSocket interception fails
- No protocol knowledge needed

**Cons:**
- Less accurate (parses human-readable text)
- May miss some events
- Slower than WebSocket

**How it works:**
```javascript
// Watch battle log container for changes
const observer = new BattleObserver();
observer.start((event) => {
    // event contains parsed log entry:
    // "Raging Bolt used Thunderbolt!"
    // → { type: 'move', pokemon: 'Raging Bolt', move: 'Thunderbolt' }
});
```

**Files:**
- `extension/content/battle_observer.js`

---

### ✅ Method 3: Python Battle Log Parser (SERVER-SIDE)
**Accuracy:** ⭐⭐⭐⭐⭐
**Difficulty:** ⭐⭐
**Performance:** ⭐⭐⭐⭐

**Pros:**
- Parses exact protocol
- Can be used with replay analysis
- Full Python feature set

**Cons:**
- Requires server/backend
- Not real-time (needs message passing)

**How it works:**
```python
from src.battle_log_parser import PokemonShowdownParser

parser = PokemonShowdownParser()

battle_log = [
    "|switch|p2a: Raging Bolt|Raging Bolt, L50|100/100",
    "|move|p2a: Raging Bolt|Thunderbolt|p1a: Great Tusk",
    "|-damage|p1a: Great Tusk|65/100"
]

events = parser.parse_battle_log(battle_log)
# → [BattleEvent(type='switch', pokemon='Raging Bolt'), ...]
```

**Files:**
- `src/battle_log_parser.py`

---

## Complete Integration Flow

```
┌─────────────────────────────────────────────────────────┐
│           Pokemon Showdown in Browser                   │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐            │
│  │  WebSocket   │────────▶│ Interceptor  │            │
│  │  Messages    │         │  (JS)        │            │
│  └──────────────┘         └──────┬───────┘            │
│                                   │                     │
└───────────────────────────────────┼─────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────┐
                    │  Battle Integration (JS)  │
                    │  • Parses events          │
                    │  • Tracks battle state    │
                    │  • Calls predictors       │
                    └───────────┬───────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Set Predictor│  │ Damage Calc  │  │ Next Move    │
    │              │  │              │  │  Predictor   │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                  │
           └─────────────────┼──────────────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │   UI Overlay     │
                   │  • Predictions   │
                   │  • Damage ranges │
                   │  • Next move     │
                   └──────────────────┘
```

---

## Quick Start

### Step 1: Load Scripts in Extension

In your `manifest.json`:
```json
{
  "content_scripts": [
    {
      "matches": ["*://play.pokemonshowdown.com/*"],
      "js": [
        "content/websocket_interceptor.js",
        "content/battle_observer.js",
        "content/battle_integration.js",
        "content/content.js"
      ],
      "run_at": "document_start"
    }
  ]
}
```

### Step 2: Initialize in content.js

```javascript
// content.js
console.log('Pokemon Showdown Set Predictor loaded!');

// Battle integration handles everything
const battle = new BattleIntegration();
battle.init();

// Events are now automatically captured and processed!
```

### Step 3: Connect to Backend (Optional)

If using Python for ML predictions:

```javascript
// In battle_integration.js
async createPrediction(pokemon) {
    // Call Python backend via HTTP
    const response = await fetch('http://localhost:5000/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pokemon: pokemon })
    });

    return await response.json();
}
```

Python backend:
```python
from flask import Flask, request, jsonify
from src.set_predictor import SetPredictor
from src.data_manager import DataManager

app = Flask(__name__)
dm = DataManager()
predictor = SetPredictor(dm)

@app.route('/predict', methods=['POST'])
def predict():
    pokemon = request.json['pokemon']
    prediction = predictor.create_initial_prediction(pokemon)

    return jsonify({
        'pokemon': pokemon,
        'abilities': prediction.ability_probs,
        'items': prediction.item_probs,
        'moves': prediction.move_probs
    })

app.run(port=5000)
```

---

## Event Types Captured

| Event | Example | Data Extracted |
|-------|---------|----------------|
| Switch | `\|switch\|p2a: Raging Bolt\|Raging Bolt, L50\|100/100` | Pokemon, HP |
| Move | `\|move\|p2a: Raging Bolt\|Thunderbolt\|p1a: Great Tusk` | Pokemon, Move, Target |
| Damage | `\|-damage\|p1a: Great Tusk\|65/100` | Pokemon, HP% |
| Heal | `\|-heal\|p2a: Kingambit\|25/100\|[from] item: Leftovers` | Pokemon, HP%, Item |
| Ability | `\|-ability\|p2a: Raging Bolt\|Protosynthesis` | Pokemon, Ability |
| Item | `\|-item\|p2a: Kingambit\|Leftovers` | Pokemon, Item |
| Weather | `\|-weather\|SunnyDay` | Weather type |
| Terrain | `\|-fieldstart\|move: Electric Terrain` | Terrain type |
| Faint | `\|faint\|p2a: Kingambit` | Pokemon |
| Boost | `\|-boost\|p2a: Raging Bolt\|spa\|1` | Pokemon, Stat, Amount |

---

## Testing

### Test WebSocket Interception:
```javascript
// Open Pokemon Showdown
// Open DevTools Console
// Paste:
const test = new WebSocketInterceptor();
test.start((msg) => {
    console.log('WS Message:', msg);
});

// Start a battle - you'll see all messages logged!
```

### Test Battle Integration:
```javascript
const integration = new BattleIntegration();
integration.init();

// Start a battle and watch the console
// You'll see predictions update in real-time!
```

---

## Troubleshooting

### Issue: "WebSocketInterceptor not defined"
**Solution:** Make sure scripts load in correct order in manifest.json

### Issue: "No WebSocket messages captured"
**Solution:** Set `"run_at": "document_start"` in manifest.json

### Issue: "CORS errors when calling backend"
**Solution:**
1. Add CORS headers in Python:
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
```

2. Or use Chrome extension messaging instead of HTTP

---

## Summary

✅ **Use Method 1 (WebSocket Interception)** for production
✅ **Use Method 2 (DOM Observer)** as fallback
✅ **Use Method 3 (Python Parser)** for replay analysis

**No webscraping needed** - everything is accessible in the browser! 🎉

---

## Files Reference

| File | Purpose |
|------|---------|
| `extension/content/websocket_interceptor.js` | Intercepts WebSocket messages |
| `extension/content/battle_observer.js` | Observes DOM for battle log changes |
| `extension/content/battle_integration.js` | Main integration logic |
| `src/battle_log_parser.py` | Python battle protocol parser |
| `examples/complete_battle_analysis.py` | Full Python example |

---

## Next Steps

1. ✅ Test WebSocket interception
2. ✅ Connect to set predictor
3. ✅ Add damage calculator
4. ✅ Display predictions in UI overlay
5. ✅ Collect battle data for ML training

Everything is ready to integrate! 🚀
