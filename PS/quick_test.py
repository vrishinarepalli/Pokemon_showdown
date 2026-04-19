#!/usr/bin/env python3
"""
Quick Test - Run all components to verify they work
"""
import sys
from pathlib import Path

def test_set_predictor():
    """Test 1: Set Predictor with Auto-Confirmation"""
    print("\n1️⃣  Testing Set Predictor...")
    print("-" * 60)

    try:
        from src.set_predictor import SetPredictor
        from src.data_manager import DataManager

        dm = DataManager()
        predictor = SetPredictor(dm)

        # Test single-ability Pokemon
        print("  Testing: Raging Bolt (single ability)")
        prediction = predictor.create_initial_prediction('Raging Bolt')

        if prediction.revealed_ability == 'Protosynthesis':
            print("  ✅ PASS - Ability auto-confirmed!")
            return True
        else:
            print(f"  ❌ FAIL - Expected auto-confirm, got: {prediction.revealed_ability}")
            return False

    except Exception as e:
        print(f"  ❌ FAIL - Error: {e}")
        return False


def test_niche_mechanics():
    """Test 2: Niche Mechanics Detector"""
    print("\n2️⃣  Testing Niche Mechanics Detector...")
    print("-" * 60)

    try:
        from src.niche_mechanics import NicheMechanicsDetector

        detector = NicheMechanicsDetector()

        # Test Paradox Pokemon detection
        print("  Testing: Booster Energy detection")
        constraint = detector.detect_paradox_booster_energy(
            pokemon="Raging Bolt",
            ability_activated=True,
            weather_active=None,
            terrain_active=None
        )

        if constraint and 'Booster Energy' in constraint.confirmed_items:
            print("  ✅ PASS - Booster Energy detected!")
            return True
        else:
            print("  ❌ FAIL - Booster Energy not detected")
            return False

    except Exception as e:
        print(f"  ❌ FAIL - Error: {e}")
        return False


def test_damage_calculator():
    """Test 3: Damage Calculator"""
    print("\n3️⃣  Testing Damage Calculator...")
    print("-" * 60)

    try:
        from src.damage_calculator import DamageCalculator
        from src.data_manager import DataManager

        dm = DataManager()
        calc = DamageCalculator(dm)

        print("  Calculating: Raging Bolt Thunderbolt vs Great Tusk")
        result = calc.calculate_damage(
            attacker_name="Raging Bolt",
            defender_name="Great Tusk",
            move_name="Thunderbolt"
        )

        if result.max_damage > 0:
            print(f"  ✅ PASS - Damage: {result.min_damage}-{result.max_damage} ({result.min_percent:.1f}%-{result.max_percent:.1f}%)")
            return True
        else:
            print("  ❌ FAIL - No damage calculated")
            return False

    except Exception as e:
        print(f"  ❌ FAIL - Error: {e}")
        return False


def test_next_move_predictor():
    """Test 4: Next Move Predictor"""
    print("\n4️⃣  Testing Next Move Predictor...")
    print("-" * 60)

    try:
        from src.next_move_predictor import NextMovePredictor
        from src.set_predictor import SetPredictor
        from src.data_manager import DataManager

        dm = DataManager()
        predictor = NextMovePredictor(dm)
        set_predictor = SetPredictor(dm)

        print("  Predicting: Kingambit's next move")
        set_prediction = set_predictor.create_initial_prediction("Kingambit")

        recommendations = predictor.predict_next_move(
            opponent_pokemon="Kingambit",
            your_pokemon="Great Tusk",
            set_prediction=set_prediction,
            game_state={'your_hp_percent': 75, 'opponent_hp_percent': 100}
        )

        if recommendations and len(recommendations) > 0:
            print(f"  ✅ PASS - Top move: {recommendations[0].move} ({recommendations[0].probability*100:.0f}%)")
            return True
        else:
            print("  ❌ FAIL - No predictions")
            return False

    except Exception as e:
        print(f"  ❌ FAIL - Error: {e}")
        return False


def test_battle_parser():
    """Test 5: Battle Log Parser"""
    print("\n5️⃣  Testing Battle Log Parser...")
    print("-" * 60)

    try:
        from src.battle_log_parser import PokemonShowdownParser

        parser = PokemonShowdownParser()

        battle_log = [
            "|switch|p2a: Raging Bolt|Raging Bolt, L50|100/100",
            "|move|p2a: Raging Bolt|Thunderbolt|p1a: Great Tusk",
        ]

        print("  Parsing: Battle protocol")
        events = parser.parse_battle_log(battle_log)

        if len(events) >= 2:
            print(f"  ✅ PASS - Parsed {len(events)} events")
            return True
        else:
            print("  ❌ FAIL - Expected 2+ events")
            return False

    except Exception as e:
        print(f"  ❌ FAIL - Error: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("POKEMON SHOWDOWN SET PREDICTOR - QUICK TEST")
    print("=" * 60)

    results = []

    # Run all tests
    results.append(("Set Predictor", test_set_predictor()))
    results.append(("Niche Mechanics", test_niche_mechanics()))
    results.append(("Damage Calculator", test_damage_calculator()))
    results.append(("Next Move Predictor", test_next_move_predictor()))
    results.append(("Battle Parser", test_battle_parser()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nNext steps:")
        print("  1. Run full example: python3 examples/complete_battle_analysis.py")
        print("  2. Load Chrome extension")
        print("  3. Test on Pokemon Showdown!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check error messages above.")
        print("\nTroubleshooting:")
        print("  1. Make sure data is downloaded: python3 update_data.py")
        print("  2. Check if all files exist: ls src/")
        print("  3. See TESTING_GUIDE.md for more help")
        return 1


if __name__ == "__main__":
    sys.exit(main())
