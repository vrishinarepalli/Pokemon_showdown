# Testing Guide - Pokemon Showdown Set Predictor

## Quick Start

### 1. Install the Extension

```bash
# Make sure you're in the project directory
cd Desktop/PS

# Convert data to JavaScript
python convert_data_to_js.py

# Verify the data file was created
ls -lh extension/lib/smogon_data.js
```

### 2. Load in Chrome

1. Open Chrome
2. Go to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top-right)
4. Click "Load unpacked"
5. Navigate to and select the `Desktop/PS/extension/` folder
6. You should see "Pokemon Showdown Set Predictor" appear

### 3. Test on Pokemon Showdown

1. Go to https://play.pokemonshowdown.com/
2. Click "Battle!" → Choose any format (OU recommended)
3. Start a battle (or spectate one)
4. When opponent sends out a Pokemon, you should see the prediction overlay appear!

## What to Look For

### Initial Prediction (Turn 1)
- ✅ Overlay slides in from the right
- ✅ Shows Pokemon name at top
- ✅ Shows confidence percentage (usually ~20-30%)
- ✅ Lists top 3 abilities with percentages
- ✅ Lists top 3 items with percentages
- ✅ Lists top 5-6 predicted moves

### After First Move (Turn 2-3)
- ✅ "Known Moves" section appears with checkmark
- ✅ Move appears in confirmed (green) section
- ✅ Remaining moves update in "Predicted Moves"
- ✅ Confidence increases slightly

### After Second Move (Turn 4-5)
- ✅ **Choice items get ruled out** (if 2 different moves used)
- ✅ **Assault Vest ruled out** (if status move like Swords Dance)
- ✅ "Ruled out" section appears (red) showing eliminated items
- ✅ Item probabilities redistribute
- ✅ Confidence jumps to ~45-50%

### Console Logs to Check

Open DevTools (F12) and look for:
```
🎮 Pokemon Showdown Set Predictor loaded
✓ On Pokemon Showdown, initializing...
✓ Predictor initialized
✓ Found battle log, setting up observer
✓ Battle log observer active
✓ Set Predictor ready!
```

Then during battle:
```
🔄 Opponent sent out Kingambit
⚔️ Opponent's Kingambit used Sucker Punch
⚠️ Ruled out Choice Band (2 moves)
⚠️ Ruled out Assault Vest (status move: Swords Dance)
✓ Kingambit item CONFIRMED: Leftovers (heal message)
```

## Testing Checklist

### Basic Functionality
- [ ] Extension loads without errors
- [ ] Overlay appears when opponent switches Pokemon
- [ ] Overlay updates when opponent uses moves
- [ ] Overlay can be closed with X button
- [ ] Predictions are reasonable (match Smogon data)

### Game Mechanic Constraints
- [ ] Using 2+ moves eliminates Choice items
- [ ] Using status move eliminates Assault Vest
- [ ] Ruled out items appear in red section
- [ ] Probabilities redistribute correctly

### UI/UX
- [ ] Overlay doesn't block battle controls
- [ ] Animations are smooth
- [ ] Colors are readable
- [ ] Scrolling works for long lists
- [ ] Close button works

### Popup Menu
- [ ] Extension icon shows popup when clicked
- [ ] Statistics display (battles, predictions)
- [ ] Toggle switches work
- [ ] Clear history button works

## Common Issues & Fixes

### Overlay doesn't appear
**Check:**
1. Are you in an actual battle? (not team builder)
2. Did opponent send out a Pokemon?
3. Console errors?

**Fix:**
- Reload the page (F5)
- Check if smogon_data.js exists and is not empty
- Make sure you ran `python convert_data_to_js.py`

### "SMOGON_DATA is not defined" error
**Fix:**
```bash
python convert_data_to_js.py
# Then reload extension in chrome://extensions/
```

### Predictions seem random
**Check:**
- Is the Pokemon in the OU tier?
- Are you testing with popular Pokemon (Kingambit, Great Tusk, etc.)?

**Note:** Uncommon Pokemon have less data, so predictions will be less confident.

### Overlay is too large/small
**Fix:** Edit `extension/content/overlay.css`
```css
#ps-set-predictor-overlay {
    width: 320px;  /* Change this value */
}
```

## Test Scenarios

### Scenario 1: Choice Scarf Detection
1. Opponent uses Kingambit
2. Uses Sucker Punch (Turn 1)
3. Uses Iron Head (Turn 3)
4. **Expected:** All Choice items ruled out

### Scenario 2: Assault Vest Detection
1. Opponent uses Raging Bolt
2. Uses Thunderbolt (Turn 1)
3. Uses Calm Mind (Turn 2)
4. **Expected:** Assault Vest ruled out

### Scenario 3: Leftovers Detection
1. Opponent uses Kingambit
2. Takes damage
3. Heals 1/16 HP at end of turn with message "[from] item: Leftovers"
4. **Expected:** Leftovers CONFIRMED at 100% (not just probability boost)

### Scenario 4: Heavy-Duty Boots Detection
1. Set up Stealth Rock
2. Opponent switches Pokemon
3. Pokemon takes damage from Stealth Rock
4. **Expected:** Heavy-Duty Boots ruled out

## Debug Mode

To see more detailed logs, edit `extension/content/content.js`:

```javascript
// In processBattleMessage function, uncomment:
if (event) {
    console.log('Battle event:', event);  // Shows every event
}
```

## Performance Testing

- [ ] Extension doesn't slow down page loading
- [ ] Predictions update instantly (< 100ms)
- [ ] No memory leaks after multiple battles
- [ ] Works with spectating battles (not just your own)

## Next Steps After Testing

1. **Report Issues**: Note any bugs or unexpected behavior
2. **UI Improvements**: Suggest design changes
3. **Add Features**: Request additional functionality
4. **Icons**: Add proper icon files (currently placeholder)
5. **More Tiers**: Expand beyond OU

## Success Criteria

The extension is working correctly if:
- ✅ Overlay appears for every opponent Pokemon
- ✅ Predictions match Smogon top sets
- ✅ Confidence increases with more information
- ✅ Constraints eliminate impossible items
- ✅ UI is smooth and doesn't interfere with gameplay

## Known Limitations (Expected)

- Only works on Pokemon Showdown website
- Only has OU tier data (can be expanded)
- Requires opponent to reveal information
- Some Pokemon have limited data (low usage)
- Predictions based on current month's meta

## Ready to Test!

1. Run `python convert_data_to_js.py`
2. Load extension in Chrome
3. Go to Pokemon Showdown
4. Start a battle
5. Watch the magic happen! ✨
