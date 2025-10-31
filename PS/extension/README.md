# Pokemon Showdown Set Predictor - Chrome Extension

A Chrome extension that predicts opponent Pokemon sets in real-time during Pokemon Showdown battles.

## Installation

### From Source (Development)

1. **Convert Data to JavaScript**
   ```bash
   python convert_data_to_js.py
   ```

2. **Load Extension in Chrome**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode" (toggle in top right)
   - Click "Load unpacked"
   - Select the `extension/` folder

3. **Test on Pokemon Showdown**
   - Go to https://play.pokemonshowdown.com/
   - Start a battle
   - The predictor overlay will appear automatically!

## Features

- ✅ Real-time set prediction as battle progresses
- ✅ Bayesian probability updates
- ✅ Game mechanic constraints (Choice items, Assault Vest, etc.)
- ✅ Beautiful overlay UI
- ✅ Confidence scoring
- ✅ Battle history tracking

## How It Works

1. **Battle Detection**: Automatically detects when you're in a battle
2. **Log Parsing**: Reads Pokemon Showdown's battle log in real-time
3. **Prediction**: Uses Smogon usage data + Bayesian inference
4. **Constraints**: Applies game mechanics (2 moves = no Choice item, etc.)
5. **Display**: Shows predictions in a sleek overlay

## Usage

### During Battle

When opponent sends out a Pokemon:
- Overlay appears automatically showing initial predictions
- Updates in real-time as moves/abilities/items are revealed
- Confidence increases as more information is gathered

### Overlay Information

- **Ability**: Most likely ability (with percentage)
- **Item**: Most likely item + ruled out items
- **Moves**: Known moves + predicted remaining moves
- **Confidence**: Overall prediction confidence

### Popup Menu

Click the extension icon to access:
- Battle statistics
- Settings (enable/disable, show confidence)
- Clear battle history

## Files Structure

```
extension/
├── manifest.json              # Extension configuration
├── content/
│   ├── content.js            # Main content script
│   ├── battle_parser.js      # Pokemon Showdown log parser
│   ├── ui_overlay.js         # Prediction UI
│   └── overlay.css           # UI styles
├── lib/
│   ├── predictor.js          # Prediction engine (JS port)
│   └── smogon_data.js        # Usage data (generated)
├── background/
│   └── service_worker.js     # Background tasks
├── popup/
│   ├── popup.html            # Extension popup
│   └── popup.js              # Popup logic
└── icons/                    # Extension icons
```

## Development

### Rebuilding Data

When Smogon updates monthly stats:
```bash
# Update Smogon data
python update_data.py

# Convert to JavaScript
python convert_data_to_js.py

# Reload extension in Chrome
```

### Debugging

1. Open Chrome DevTools on Pokemon Showdown page
2. Check Console for log messages:
   - `🎮 Pokemon Showdown Set Predictor loaded`
   - `✓ Battle log observer active`
   - Battle events as they occur

3. Check extension background page:
   - Go to `chrome://extensions/`
   - Click "Inspect views: service worker"

## Known Limitations

- Only works on Pokemon Showdown (not Pokemon games)
- Requires internet connection for first load
- Only supports OU tier currently (expandable)
- Data updates monthly with Smogon stats

## Troubleshooting

### Overlay not appearing
- Check if you're in a battle (not team builder)
- Check browser console for errors
- Reload the extension

### Predictions seem wrong
- Data is based on current month's Smogon stats
- Some Pokemon have multiple viable sets
- Confidence increases with more revealed information

### Extension not loading
- Make sure you converted data: `python convert_data_to_js.py`
- Check `lib/smogon_data.js` exists
- Verify manifest.json has no errors

## Privacy

- All data stored locally in browser
- No external servers or tracking
- Battle history stays on your device
- Can be cleared anytime from popup

## Contributing

See main project README for contribution guidelines.

## License

MIT License - See main project for details
