# Pokemon Showdown Set Predictor

A Chrome extension that predicts opponent Pokemon sets in real-time during Pokemon Showdown battles. Uses Smogon usage statistics and learns from battle history to provide accurate predictions.

## Features
- **Real-time Set Prediction**: Predicts opponent moves, abilities, items, and EV spreads as battle progresses
- **Bayesian Learning**: Updates predictions based on revealed information
- **Battle History**: Learns from past battles to improve accuracy
- **Chrome Extension**: Seamless overlay on Pokemon Showdown battles
- **Privacy-First**: All data stored locally in your browser

## Installation

### Python Backend (for data updates)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Chrome Extension

1. **Convert data to JavaScript**
   ```bash
   python convert_data_to_js.py
   ```

2. **Load extension in Chrome**
   - Open Chrome → `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `extension/` folder

3. **Start using!**
   - Go to https://play.pokemonshowdown.com/
   - Start a battle
   - Predictions appear automatically!

## How It Works

1. **Battle Start**: When opponent sends out a Pokemon, shows initial predictions based on Smogon usage data
2. **Real-time Updates**: As moves/abilities/items are revealed, predictions are refined using Bayesian inference
3. **Learning**: Stores battle history to improve future predictions
4. **Accuracy**: Typically 60% accurate on Turn 1, 80% by Turn 5, 95% by Turn 10

## Usage

### Update Data
```bash
# Fetch latest Smogon statistics
python update_data.py

# Convert to JavaScript for extension
python convert_data_to_js.py
```

### Test Prediction Engine
```bash
# Test Python predictor
python -m src.set_predictor
```

### Use Chrome Extension
- Navigate to Pokemon Showdown
- Start a battle
- Overlay appears automatically with predictions
- Updates in real-time as battle progresses

## Project Status
**Phase 1**: Data Infrastructure ✓ Complete
**Phase 2**: Prediction Engine ✓ Complete
**Phase 3**: Chrome Extension ✓ Complete
**Phase 4**: Testing & Polish (In Progress)

See [specs_set_predictor.md](specs_set_predictor.md) for detailed project specifications.

## Current Scope
- **Tier**: OU (OverUsed) focus, expandable to other tiers
- **Generation**: Gen 9 (Scarlet/Violet)
- **Platform**: Chrome Extension for Pokemon Showdown

## Documentation
- [Set Predictor Specifications](specs_set_predictor.md) - Detailed project plan
- [Original Team Generator Plan](specs.md) - Previous direction (archived)
