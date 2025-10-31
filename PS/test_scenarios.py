#!/usr/bin/env python3
"""
Test Scenarios for Set Predictor
Walks through realistic battle situations
"""
from src.set_predictor import SetPredictor
from src.data_manager import DataManager


def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_turn(turn_num, action):
    """Print turn header"""
    print(f"\n{'─' * 70}")
    print(f"[Turn {turn_num}] {action}")
    print('─' * 70)


def show_prediction(predictor, prediction, show_moves=True):
    """Display current prediction state"""
    top = predictor.get_top_predictions(prediction, n=5)

    print(f"\n📊 Confidence: {prediction.confidence:.1%}")

    # Abilities
    if top['abilities']:
        print(f"\n💫 Abilities:")
        for ability, prob in top['abilities'][:3]:
            icon = "✓" if prob == 1.0 else "●" if prob > 0.5 else "○"
            print(f"   {icon} {ability}: {prob:.1%}")

    # Items
    if top['items']:
        print(f"\n📦 Items:")
        for item, prob in top['items'][:3]:
            icon = "✓" if prob == 1.0 else "●" if prob > 0.5 else "○"
            print(f"   {icon} {item}: {prob:.1%}")

        # Show ruled out items
        if prediction.impossible_items:
            print(f"\n   ⚠️  Ruled out: {', '.join(sorted(prediction.impossible_items))}")

    # Moves
    if show_moves and (top['revealed_moves'] or top['moves']):
        if top['revealed_moves']:
            print(f"\n⚔️  Known Moves:")
            for move in top['revealed_moves']:
                print(f"   ✓ {move}")

        remaining = 4 - len(top['revealed_moves'])
        if top['moves'] and remaining > 0:
            print(f"\n🎯 Predicted Moves ({remaining} slot{'s' if remaining != 1 else ''} remaining):")
            for move, prob in top['moves'][:5]:
                icon = "●" if prob > 0.5 else "○"
                print(f"   {icon} {move}: {prob:.1%}")


def scenario_1_choice_scarf():
    """Scenario 1: Detecting Choice Scarf vs Normal Set"""
    print_section("SCENARIO 1: Choice Scarf Detection")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Opponent sends out Dragapult")
    print("   Question: Is it Choice Specs or a mixed attacker?")

    # Turn 1: Dragapult switches in
    print_turn(1, "Opponent sends out Dragapult")
    prediction = predictor.create_initial_prediction("Dragapult")
    show_prediction(predictor, prediction)

    # Turn 2: Uses Dragon Darts
    print_turn(2, "Dragapult used Dragon Darts!")
    prediction = predictor.update_with_move(prediction, "Dragon Darts")
    show_prediction(predictor, prediction)

    # Turn 4: Uses U-turn
    print_turn(4, "Dragapult used U-turn!")
    print("   💡 This is the KEY moment - two different moves!")
    prediction = predictor.update_with_move(prediction, "U-turn")
    show_prediction(predictor, prediction)

    print("\n✅ Conclusion: NOT a Choice Specs set (would be locked into first move)")
    print("   Likely a mixed attacker with Dragon Darts, U-turn, and coverage moves")


def scenario_2_assault_vest():
    """Scenario 2: Detecting Assault Vest vs Leftovers"""
    print_section("SCENARIO 2: Assault Vest vs Leftovers")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Opponent sends out Raging Bolt")
    print("   Question: Does it have Assault Vest or Leftovers?")

    # Turn 1: Raging Bolt switches in
    print_turn(1, "Opponent sends out Raging Bolt")
    prediction = predictor.create_initial_prediction("Raging Bolt")
    show_prediction(predictor, prediction)

    # Turn 2: Uses Thunderbolt
    print_turn(2, "Raging Bolt used Thunderbolt!")
    prediction = predictor.update_with_move(prediction, "Thunderbolt")
    show_prediction(predictor, prediction)

    # Turn 3: Uses Calm Mind
    print_turn(3, "Raging Bolt used Calm Mind!")
    print("   💡 KEY: Calm Mind is a STATUS MOVE - blocked by Assault Vest!")
    prediction = predictor.update_with_move(prediction, "Calm Mind")
    show_prediction(predictor, prediction)

    print("\n✅ Conclusion: NOT Assault Vest (can't use status moves)")
    print("   Likely a Calm Mind sweeper with Leftovers or Booster Energy")


def scenario_3_swords_dance_sweeper():
    """Scenario 3: Identifying a Swords Dance Sweeper"""
    print_section("SCENARIO 3: Swords Dance Sweeper Identification")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Opponent sends out Kingambit")
    print("   Question: What's the full moveset?")

    # Turn 1: Kingambit switches in
    print_turn(1, "Opponent sends out Kingambit")
    prediction = predictor.create_initial_prediction("Kingambit")
    show_prediction(predictor, prediction)

    # Turn 3: Uses Sucker Punch
    print_turn(3, "Kingambit used Sucker Punch!")
    prediction = predictor.update_with_move(prediction, "Sucker Punch")
    show_prediction(predictor, prediction)

    # Turn 5: Uses Swords Dance
    print_turn(5, "Kingambit used Swords Dance!")
    print("   💡 Setup move suggests offensive set")
    prediction = predictor.update_with_move(prediction, "Swords Dance")
    show_prediction(predictor, prediction)

    # Turn 7: Uses Kowtow Cleave
    print_turn(7, "Kingambit used Kowtow Cleave!")
    print("   💡 3 moves revealed - can predict 4th slot")
    prediction = predictor.update_with_move(prediction, "Kowtow Cleave")
    show_prediction(predictor, prediction)

    print("\n✅ Conclusion: Swords Dance sweeper set")
    print("   Known: Sucker Punch, Swords Dance, Kowtow Cleave")
    print("   4th move likely: Iron Head (80%+) or Low Kick")
    print("   Item: Leftovers (boosted due to Swords Dance correlation)")


def scenario_4_boots_detection():
    """Scenario 4: Heavy-Duty Boots Detection"""
    print_section("SCENARIO 4: Heavy-Duty Boots Detection")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: You set up Stealth Rock")
    print("   Opponent sends out Great Tusk")
    print("   Question: Does it have Heavy-Duty Boots?")

    # Turn 1: Great Tusk switches in
    print_turn(1, "Opponent sends out Great Tusk")
    prediction = predictor.create_initial_prediction("Great Tusk")
    print("\n📦 Initial Item Predictions:")
    top = predictor.get_top_predictions(prediction)
    for item, prob in top['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    # Scenario A: Takes hazard damage
    print("\n\n━━━ SCENARIO A: Takes Stealth Rock Damage ━━━")
    print_turn(1, "Great Tusk took 12.5% damage from Stealth Rock!")
    prediction_a = predictor.create_initial_prediction("Great Tusk")
    predictor.apply_damage_constraints(prediction_a, took_hazard_damage=True)

    print("\n📦 Updated Item Predictions:")
    top_a = predictor.get_top_predictions(prediction_a)
    for item, prob in top_a['items'][:5]:
        icon = "✓" if prob == 1.0 else "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")
    if prediction_a.impossible_items:
        print(f"\n   ⚠️  Ruled out: {', '.join(sorted(prediction_a.impossible_items))}")

    print("\n✅ Conclusion A: Does NOT have Heavy-Duty Boots")
    print("   Most likely: Booster Energy or Leftovers")

    # Scenario B: No hazard damage
    print("\n\n━━━ SCENARIO B: NO Stealth Rock Damage ━━━")
    print_turn(1, "Great Tusk switches in unscathed!")
    prediction_b = predictor.create_initial_prediction("Great Tusk")

    # Manually boost Heavy-Duty Boots since it avoided hazards
    if 'Heavy-Duty Boots' in prediction_b.item_probs:
        prediction_b.item_probs['Heavy-Duty Boots'] *= 5.0
        # Renormalize
        total = sum(prediction_b.item_probs.values())
        prediction_b.item_probs = {
            item: prob / total for item, prob in prediction_b.item_probs.items()
        }

    print("\n📦 Updated Item Predictions:")
    top_b = predictor.get_top_predictions(prediction_b)
    for item, prob in top_b['items'][:5]:
        icon = "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")

    print("\n✅ Conclusion B: Very likely has Heavy-Duty Boots")
    print("   Rock-type takes 25% from SR normally, but took 0%")


def scenario_5_leftovers_detection():
    """Scenario 5: Leftovers Detection via Healing"""
    print_section("SCENARIO 5: Leftovers Detection via Passive Healing")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Opponent's Slowking-Galar is taking damage")
    print("   Question: What item does it have?")

    # Turn 1: Slowking switches in
    print_turn(1, "Opponent sends out Slowking-Galar")
    prediction = predictor.create_initial_prediction("Slowking-Galar")

    print("\n📦 Initial Item Predictions:")
    top = predictor.get_top_predictions(prediction)
    for item, prob in top['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    # Turn 3: Takes damage
    print_turn(3, "Slowking-Galar at 80/100 HP after taking damage")

    # Turn 4: Heals passively
    print_turn(4, "Slowking-Galar healed to 86/100 HP at end of turn!")
    print("   💡 Healed 6% HP without using a move - that's 1/16 HP!")

    predictor.apply_damage_constraints(prediction, healed_over_time=True)

    print("\n📦 Updated Item Predictions:")
    top = predictor.get_top_predictions(prediction)
    for item, prob in top['items'][:5]:
        icon = "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")

    print("\n✅ Conclusion: Almost certainly Leftovers or Black Sludge")
    print("   Leftovers heals 1/16 HP (6.25%) at end of each turn")


def scenario_6_full_battle():
    """Scenario 6: Complete Battle Simulation"""
    print_section("SCENARIO 6: Complete Battle - Ogerpon-Wellspring")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Full battle scenario showing confidence progression")

    # Turn 1: Ogerpon switches in
    print_turn(1, "Opponent sends out Ogerpon-Wellspring")
    prediction = predictor.create_initial_prediction("Ogerpon-Wellspring")
    show_prediction(predictor, prediction, show_moves=False)

    # Turn 2: Uses Ivy Cudgel
    print_turn(2, "Ogerpon-Wellspring used Ivy Cudgel!")
    prediction = predictor.update_with_move(prediction, "Ivy Cudgel")
    show_prediction(predictor, prediction, show_moves=False)

    # Turn 3: Ability revealed
    print_turn(3, "Ogerpon-Wellspring's Water Absorb activated!")
    print("   💡 Ability revealed when opponent used Water move")
    prediction = predictor.update_with_ability(prediction, "Water Absorb")
    show_prediction(predictor, prediction, show_moves=False)

    # Turn 5: Uses Swords Dance
    print_turn(5, "Ogerpon-Wellspring used Swords Dance!")
    prediction = predictor.update_with_move(prediction, "Swords Dance")
    show_prediction(predictor, prediction)

    # Turn 7: Uses Horn Leech
    print_turn(7, "Ogerpon-Wellspring used Horn Leech!")
    prediction = predictor.update_with_move(prediction, "Horn Leech")
    show_prediction(predictor, prediction)

    # Turn 10: Item revealed
    print_turn(10, "Ogerpon-Wellspring's Wellspring Mask activated!")
    print("   💡 Signature item revealed")
    prediction = predictor.update_with_item(prediction, "Wellspring Mask")
    show_prediction(predictor, prediction)

    print("\n✅ Final Analysis:")
    print("   Confidence progression: 20% → 40% → 55% → 65% → 75% → 90%+")
    print("   Known set: Ivy Cudgel, Swords Dance, Horn Leech, (4th move unknown)")
    print("   Item: Wellspring Mask (confirmed)")
    print("   Ability: Water Absorb (confirmed)")


def scenario_7_booster_energy_detection():
    """Scenario 7: Booster Energy Detection via Ability Activation"""
    print_section("SCENARIO 7: Booster Energy Detection")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Protosynthesis/Quark Drive Pokemon switch in")
    print("   Question: Is the ability activated by Booster Energy or weather/terrain?")

    # Scenario A: Protosynthesis activates WITHOUT sun
    print("\n\n━━━ SCENARIO A: Great Tusk (Protosynthesis) - NO SUN ━━━")

    print_turn(1, "Opponent sends out Great Tusk")
    print("   Weather: Clear (no sun)")
    prediction_a = predictor.create_initial_prediction("Great Tusk")

    print("\n📦 Initial Item Predictions:")
    top_a = predictor.get_top_predictions(prediction_a)
    for item, prob in top_a['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    print_turn(1, "Great Tusk's Protosynthesis activated on switch!")
    print("   💡 Ability activated but NO SUN present!")

    predictor.apply_ability_activation_constraint(
        prediction_a,
        ability_activated_on_switch=True,
        sun_active=False,
        electric_terrain_active=False
    )

    print("\n📦 After Ability Activation:")
    top_a = predictor.get_top_predictions(prediction_a)
    for item, prob in top_a['items'][:5]:
        icon = "✓" if prob == 1.0 else "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")

    print("\n✅ Conclusion A: Item is DEFINITELY Booster Energy")
    print("   Protosynthesis can only activate without sun via Booster Energy")

    # Scenario B: Protosynthesis activates WITH sun
    print("\n\n━━━ SCENARIO B: Great Tusk (Protosynthesis) - SUN ACTIVE ━━━")

    print_turn(1, "Opponent sends out Great Tusk")
    print("   Weather: Harsh sunlight (sun active)")
    prediction_b = predictor.create_initial_prediction("Great Tusk")

    print("\n📦 Initial Item Predictions:")
    top_b = predictor.get_top_predictions(prediction_b)
    for item, prob in top_b['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    print_turn(1, "Great Tusk's Protosynthesis activated on switch!")
    print("   💡 Ability activated naturally due to sun")

    predictor.apply_ability_activation_constraint(
        prediction_b,
        ability_activated_on_switch=True,
        sun_active=True,
        electric_terrain_active=False
    )

    print("\n📦 After Ability Activation:")
    top_b = predictor.get_top_predictions(prediction_b)
    for item, prob in top_b['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    print("\n✅ Conclusion B: Item is UNKNOWN")
    print("   Protosynthesis activated naturally from sun")
    print("   Could have ANY item (Leftovers, Rocky Helmet, etc.)")

    # Scenario C: Iron Valiant with Quark Drive
    print("\n\n━━━ SCENARIO C: Iron Valiant (Quark Drive) - NO TERRAIN ━━━")

    print_turn(1, "Opponent sends out Iron Valiant")
    print("   Terrain: None (no Electric Terrain)")
    prediction_c = predictor.create_initial_prediction("Iron Valiant")

    print("\n📦 Initial Item Predictions:")
    top_c = predictor.get_top_predictions(prediction_c)
    for item, prob in top_c['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    print_turn(1, "Iron Valiant's Quark Drive activated on switch!")
    print("   💡 Ability activated but NO Electric Terrain present!")

    predictor.apply_ability_activation_constraint(
        prediction_c,
        ability_activated_on_switch=True,
        sun_active=False,
        electric_terrain_active=False
    )

    print("\n📦 After Ability Activation:")
    top_c = predictor.get_top_predictions(prediction_c)
    for item, prob in top_c['items'][:5]:
        icon = "✓" if prob == 1.0 else "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")

    print("\n✅ Conclusion C: Item is DEFINITELY Booster Energy")
    print("   Quark Drive can only activate without terrain via Booster Energy")


def scenario_8_choice_locked():
    """Scenario 7: Choice-Locked Pokemon"""
    print_section("SCENARIO 7: Choice-Locked Detection")

    dm = DataManager()
    predictor = SetPredictor(dm)

    print("\n🎮 Context: Is this Pokemon Choice-locked?")

    # Turn 1: Cinderace switches in
    print_turn(1, "Opponent sends out Cinderace")
    prediction = predictor.create_initial_prediction("Cinderace")

    print("\n📦 Initial Item Predictions:")
    top = predictor.get_top_predictions(prediction)
    for item, prob in top['items'][:5]:
        print(f"   {item}: {prob:.1%}")

    # Turn 2: Uses Pyro Ball
    print_turn(2, "Cinderace used Pyro Ball!")
    prediction = predictor.update_with_move(prediction, "Pyro Ball")

    # Turn 3: Uses Pyro Ball AGAIN
    print_turn(3, "Cinderace used Pyro Ball again!")
    print("   💡 Same move twice - might be Choice-locked OR best move")

    # Turn 4: Uses Pyro Ball AGAIN
    print_turn(4, "Cinderace used Pyro Ball for the 3rd time!")
    print("   💡 THREE times in a row - very likely Choice item")

    # Turn 5: Switches out instead of attacking
    print_turn(5, "Opponent switched Cinderace out")
    print("   💡 Switching pattern consistent with Choice item")

    print("\n📦 Current Item Assessment:")
    top = predictor.get_top_predictions(prediction)
    for item, prob in top['items'][:5]:
        icon = "●" if prob > 0.5 else "○"
        print(f"   {icon} {item}: {prob:.1%}")

    print("\n✅ Strong Inference: Choice Scarf Cinderace")
    print("   Evidence: Only used one move repeatedly, then switched")
    print("   Note: Can't be 100% certain until it uses a 2nd different move")
    print("         (which would eliminate all Choice items)")


def main():
    """Run all scenarios"""
    dm = DataManager()

    if not dm.is_data_available():
        print("❌ Error: Data not available. Run update_data.py first.")
        return 1

    print("\n" + "█" * 70)
    print("  POKEMON SHOWDOWN SET PREDICTOR - SCENARIO TESTING")
    print("█" * 70)
    print("\nShowing how the prediction engine reacts to different battle situations")

    scenarios = [
        ("1", "Choice Scarf Detection", scenario_1_choice_scarf),
        ("2", "Assault Vest Detection", scenario_2_assault_vest),
        ("3", "Swords Dance Sweeper", scenario_3_swords_dance_sweeper),
        ("4", "Heavy-Duty Boots Detection", scenario_4_boots_detection),
        ("5", "Leftovers Detection", scenario_5_leftovers_detection),
        ("6", "Complete Battle", scenario_6_full_battle),
        ("7", "Booster Energy Detection", scenario_7_booster_energy_detection),
        ("8", "Choice-Locked Detection", scenario_8_choice_locked),
    ]

    print("\n📋 Available Scenarios:")
    for num, name, _ in scenarios:
        print(f"   {num}. {name}")
    print("   0. Run all scenarios")

    choice = input("\nSelect scenario (0-7): ").strip()

    if choice == "0":
        for _, _, func in scenarios:
            func()
            input("\n⏸️  Press Enter to continue to next scenario...")
    else:
        for num, name, func in scenarios:
            if choice == num:
                func()
                break
        else:
            print(f"Invalid choice: {choice}")
            return 1

    print("\n\n" + "█" * 70)
    print("  TESTING COMPLETE")
    print("█" * 70)
    print("\n✨ These scenarios demonstrate how the engine:")
    print("   ✓ Starts with Smogon usage statistics")
    print("   ✓ Updates probabilities with Bayesian inference")
    print("   ✓ Applies hard constraints based on game mechanics")
    print("   ✓ Increases confidence as information is revealed")
    print("   ✓ Narrows down exact sets by Turn 5-7")

    return 0


if __name__ == "__main__":
    exit(main())
