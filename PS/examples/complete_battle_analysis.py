"""
Complete Battle Analysis Example
Demonstrates all features: Set Prediction, Damage Calculation, Next Move Prediction, Niche Mechanics
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_manager import DataManager
from src.set_predictor import SetPredictor
from src.damage_calculator import DamageCalculator
from src.next_move_predictor import NextMovePredictor
from src.niche_mechanics import NicheMechanicsDetector


def comprehensive_battle_example():
    """
    Comprehensive example showing all features working together
    """
    print("=" * 80)
    print("POKEMON SHOWDOWN - COMPREHENSIVE BATTLE ANALYSIS")
    print("=" * 80)

    # Initialize all components
    dm = DataManager()
    if not dm.is_data_available():
        print("Error: Run update_data.py first to download data")
        return

    set_predictor = SetPredictor(dm)
    damage_calc = DamageCalculator(dm)
    move_predictor = NextMovePredictor(dm, damage_calc)
    niche_detector = NicheMechanicsDetector()

    # =========================================================================
    # SCENARIO: Turn 1 - Opponent sends out Raging Bolt
    # =========================================================================
    print("\n" + "=" * 80)
    print("TURN 1: Opponent sends out Raging Bolt!")
    print("=" * 80)

    # Create initial prediction
    prediction = set_predictor.create_initial_prediction("Raging Bolt")

    print("\n[SET PREDICTION]")
    print("-" * 80)
    top = set_predictor.get_top_predictions(prediction, n=3)

    print(f"Confidence: {prediction.confidence:.1%}\n")
    print(f"Top Abilities:")
    for ability, prob in top['abilities']:
        print(f"  • {ability}: {prob:.1%}")

    print(f"\nTop Items:")
    for item, prob in top['items']:
        print(f"  • {item}: {prob:.1%}")

    print(f"\nTop Moves:")
    for move, prob in top['moves'][:5]:
        print(f"  • {move}: {prob:.1%}")

    # Check for niche mechanics (Paradox Pokemon)
    print("\n[NICHE MECHANICS CHECK]")
    print("-" * 80)
    paradox_check = niche_detector.detect_paradox_booster_energy(
        pokemon="Raging Bolt",
        ability_activated=True,  # Protosynthesis activated on switch
        weather_active=None,
        terrain_active=None
    )
    if paradox_check:
        print(f"✓ {paradox_check.reason}")
        print(f"  Confirmed item: {list(paradox_check.confirmed_items)[0] if paradox_check.confirmed_items else 'None yet'}")

    # =========================================================================
    # DAMAGE CALCULATOR: What can Raging Bolt do to you?
    # =========================================================================
    print("\n[DAMAGE CALCULATOR] What can Raging Bolt do to my Great Tusk?")
    print("-" * 80)

    your_pokemon = "Great Tusk"
    predicted_moves = ["Thunderbolt", "Dragon Pulse", "Thunderclap", "Volt Switch"]

    for move in predicted_moves:
        result = damage_calc.calculate_damage(
            attacker_name="Raging Bolt",
            defender_name=your_pokemon,
            move_name=move,
            attacker_item="Booster Energy",  # From niche mechanics
            attacker_ability="Protosynthesis"
        )

        threat = "🔴 LETHAL" if result.guaranteed_ko else \
                "🟠 DANGER" if result.possible_ko else \
                "🟡 MODERATE" if result.max_percent >= 50 else \
                "🟢 LOW"

        print(f"{threat} {move}: {result.min_damage}-{result.max_damage} " +
              f"({result.min_percent:.1f}%-{result.max_percent:.1f}%)")

        if result.roll_to_ko:
            print(f"       {result.roll_to_ko}")

    # =========================================================================
    # NEXT MOVE PREDICTION
    # =========================================================================
    print("\n[NEXT MOVE PREDICTION] What will Raging Bolt do?")
    print("-" * 80)

    game_state = {
        'your_hp_percent': 100,
        'opponent_hp_percent': 100,
        'weather': None,
        'terrain': None,
        'hazards_set': [],
    }

    recommendations = move_predictor.predict_next_move(
        opponent_pokemon="Raging Bolt",
        your_pokemon=your_pokemon,
        set_prediction=prediction,
        game_state=game_state
    )

    for i, rec in enumerate(recommendations[:4], 1):
        print(f"\n{i}. {rec.move} ({rec.probability*100:.1f}%)")
        print(f"   Threat: {rec.threat_level}")
        print(f"   Reasoning: {rec.reasoning}")

    # =========================================================================
    # TURN 3: Raging Bolt uses Thunderbolt!
    # =========================================================================
    print("\n\n" + "=" * 80)
    print("TURN 3: Raging Bolt used Thunderbolt!")
    print("=" * 80)

    # Update prediction
    prediction = set_predictor.update_with_move(prediction, "Thunderbolt")
    move_predictor.record_move("Raging Bolt", "Thunderbolt", turn=3)

    print("\n[UPDATED SET PREDICTION]")
    print("-" * 80)
    top = set_predictor.get_top_predictions(prediction, n=3)

    print(f"Confidence: {prediction.confidence:.1%}\n")
    print(f"Revealed Moves: {', '.join(top['revealed_moves'])}\n")

    print(f"Predicted Remaining Moves:")
    for move, prob in top['moves'][:3]:
        print(f"  • {move}: {prob:.1%}")

    print(f"\nUpdated Item Probabilities:")
    for item, prob in top['items']:
        print(f"  • {item}: {prob:.1%}")

    # =========================================================================
    # TURN 5: Raging Bolt uses Calm Mind!
    # =========================================================================
    print("\n\n" + "=" * 80)
    print("TURN 5: Raging Bolt used Calm Mind!")
    print("=" * 80)

    prediction = set_predictor.update_with_move(prediction, "Calm Mind")
    move_predictor.record_move("Raging Bolt", "Calm Mind", turn=5)

    # Calm Mind rules out Assault Vest!
    print("\n[GAME MECHANIC CONSTRAINT]")
    print("-" * 80)
    print("⚠️  Calm Mind is a status move → Assault Vest ruled out!")
    print(f"    Impossible items: {prediction.impossible_items}")

    print("\n[UPDATED SET PREDICTION]")
    print("-" * 80)
    top = set_predictor.get_top_predictions(prediction, n=3)

    print(f"Confidence: {prediction.confidence:.1%}\n")
    print(f"Revealed: {', '.join(top['revealed_moves'])}\n")

    print(f"Top Items (Assault Vest removed):")
    for item, prob in top['items']:
        print(f"  • {item}: {prob:.1%}")

    # Recalculate damage with boosted stats
    print("\n[DAMAGE RECALCULATION] After +1 SpA, +1 SpD from Calm Mind")
    print("-" * 80)
    print("⚠️  Raging Bolt is now more dangerous!")
    print("    Thunderbolt damage increased ~1.5x")
    print("    Your special attacks less effective (higher SpD)")

    # =========================================================================
    # FINAL RECOMMENDATION
    # =========================================================================
    print("\n\n" + "=" * 80)
    print("STRATEGIC RECOMMENDATION")
    print("=" * 80)

    print("""
┌────────────────────────────────────────────────────────────────────────┐
│ ANALYSIS SUMMARY                                                       │
├────────────────────────────────────────────────────────────────────────┤
│ Opponent: Raging Bolt                                                  │
│ Set: Calm Mind Sweeper                                                 │
│ Item: Very likely Booster Energy (confirmed via Protosynthesis)       │
│ Known Moves: Thunderbolt, Calm Mind                                    │
│ Predicted 4th Move: Dragon Pulse (80%), Thunderclap (60%)             │
│                                                                        │
│ THREATS:                                                               │
│  🔴 After +1 Calm Mind, can sweep your team                           │
│  🔴 Thunderbolt threatens all Water/Flying types                      │
│  🟠 Boosted stats make it hard to take down                           │
│                                                                        │
│ RECOMMENDATIONS:                                                       │
│  1. ✓ Switch to a Ground-type (immune to Electric)                    │
│  2. ✓ Use Earthquake for super-effective damage                       │
│  3. ✓ Don't let it set up more Calm Minds                            │
│  4. ⚠️  Beware of potential Tera Grass (ruins Ground immunity)        │
└────────────────────────────────────────────────────────────────────────┘
    """)

    # =========================================================================
    # BONUS: Showcase more niche mechanics
    # =========================================================================
    print("\n" + "=" * 80)
    print("BONUS: Other Niche Mechanics Examples")
    print("=" * 80)

    print("\n[Example 1] Ogerpon-Wellspring - Forme Change Detection")
    print("-" * 70)
    forme_check = niche_detector.detect_forme_change("Ogerpon-Wellspring", {})
    if forme_check:
        print(f"✓ {forme_check.reason}")
        print(f"  Required item: {list(forme_check.confirmed_items)[0]}")

    print("\n[Example 2] Guts + Burn = Flame Orb")
    print("-" * 70)
    status_check = niche_detector.detect_status_orb_activation(
        pokemon="Ursaluna",
        status_inflicted="burn",
        ability="Guts",
        took_damage=False
    )
    if status_check:
        print(f"✓ {status_check.reason}")
        print(f"  Item probability boost: Flame Orb × {status_check.probability_boosts.get('Flame Orb', 1.0)}")

    print("\n[Example 3] Multi-hit move + 5 hits = Loaded Dice?")
    print("-" * 70)
    multi_hit = niche_detector.detect_multi_hit_interaction(
        move_used="Bullet Seed",
        damage_taken=120,
        hits_count=5
    )
    if multi_hit:
        print(f"✓ {multi_hit.reason}")

    print("\n" + "=" * 80)
    print("COMPLETE BATTLE ANALYSIS FINISHED")
    print("=" * 80)


def main():
    """Run comprehensive example"""
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║  POKEMON SHOWDOWN - COMPREHENSIVE BATTLE ANALYSIS                        ║
║                                                                          ║
║  This example demonstrates:                                             ║
║  ✓ Set Prediction (Bayesian inference)                                  ║
║  ✓ Niche Mechanics Detection (Paradox Pokemon, Forme Changes, etc.)     ║
║  ✓ Damage Calculator (predict damage ranges)                            ║
║  ✓ Next Move Prediction (game theory + ML)                              ║
║  ✓ Real-time constraint application                                     ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)

    try:
        comprehensive_battle_example()

        print("\n" + "=" * 80)
        print("Next Steps:")
        print("  • Integrate this into your Chrome extension")
        print("  • Parse Pokemon Showdown battle logs")
        print("  • Display predictions in real-time UI")
        print("  • Collect battle data for ML training")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you've run: python update_data.py")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
