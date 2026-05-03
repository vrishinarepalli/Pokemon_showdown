"""
ML Training Example
Demonstrates how to collect data and train ML models
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_manager import DataManager
from src.hybrid_predictor import HybridSetPredictor
from src.battle_recorder import PokemonRecord, RevealedTiming, TeamContext


def simulate_battle_example():
    """
    Simulate a complete battle to show how data collection works
    """
    print("=" * 70)
    print("Example: Simulating a Battle for ML Training")
    print("=" * 70)

    # Initialize
    dm = DataManager()
    if not dm.is_data_available():
        print("Error: Run update_data.py first to download Smogon data")
        return

    predictor = HybridSetPredictor(dm)

    # Step 1: Start battle
    print("\n[Battle Start]")
    print("Battle ID: gen9ou-test-001")
    print("Your rating: 1650")
    predictor.set_battle_context(
        battle_id="gen9ou-test-001",
        tier="gen9ou",
        player_rating=1650,
        opponent_username="TestOpponent"
    )

    # Step 2: Opponent sends out Kingambit
    print("\n[Turn 1] Opponent sends out Kingambit")
    print("-" * 70)
    prediction = predictor.create_initial_prediction("Kingambit")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Initial Predictions:")
    print(f"  Items: {', '.join(f'{item}({prob:.0%})' for item, prob in top['items'])}")
    print(f"  Moves: {', '.join(f'{move}({prob:.0%})' for move, prob in top['moves'][:5])}")

    # Step 3: Kingambit uses Sucker Punch
    print("\n[Turn 3] Kingambit used Sucker Punch!")
    print("-" * 70)
    predictor.current_battle_context['turn_number'] = 3
    prediction = predictor.update_with_move(prediction, "Sucker Punch")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Updated Predictions:")
    print(f"  Items: {', '.join(f'{item}({prob:.0%})' for item, prob in top['items'])}")

    # Step 4: Kingambit uses Swords Dance
    print("\n[Turn 5] Kingambit used Swords Dance!")
    print("-" * 70)
    predictor.current_battle_context['turn_number'] = 5
    prediction = predictor.update_with_move(prediction, "Swords Dance")

    top = predictor.get_top_predictions(prediction, n=3)
    print(f"Updated Predictions:")
    print(f"  Items: {', '.join(f'{item}({prob:.0%})' for item, prob in top['items'])}")
    print(f"  Predicted 4th move: {', '.join(f'{move}({prob:.0%})' for move, prob in top['moves'][:3])}")

    # Step 5: Battle ends - Record final set
    print("\n[Battle End] Recording Kingambit's actual set...")
    print("-" * 70)
    predictor.finalize_pokemon(
        pokemon_name="Kingambit",
        final_ability="Supreme Overlord",
        final_item="Leftovers",
        final_moves=["Sucker Punch", "Swords Dance", "Kowtow Cleave", "Iron Head"],
        final_tera="Ghost",
        final_spread="Adamant:0/252/4/0/0/252"
    )

    predictor.end_battle(winner="player")
    print("✅ Battle recorded!")

    # Show statistics
    stats = predictor.get_statistics()
    print(f"\nTotal battles collected: {stats['total_battles']}")
    print(f"ML model trained: {stats['ml_trained']}")

    return predictor


def simulate_multiple_battles(num_battles: int = 10):
    """
    Simulate multiple battles with various Pokemon
    """
    print("\n" + "=" * 70)
    print(f"Simulating {num_battles} Battles with Varied Pokemon")
    print("=" * 70)

    dm = DataManager()
    predictor = HybridSetPredictor(dm)

    # Common Pokemon and their typical sets
    common_sets = [
        {
            "pokemon": "Kingambit",
            "ability": "Supreme Overlord",
            "item": "Leftovers",
            "moves": ["Sucker Punch", "Swords Dance", "Kowtow Cleave", "Iron Head"],
            "tera": "Ghost"
        },
        {
            "pokemon": "Great Tusk",
            "ability": "Protosynthesis",
            "item": "Heavy-Duty Boots",
            "moves": ["Rapid Spin", "Headlong Rush", "Ice Spinner", "Stealth Rock"],
            "tera": "Steel"
        },
        {
            "pokemon": "Dragapult",
            "ability": "Infiltrator",
            "item": "Choice Specs",
            "moves": ["Shadow Ball", "Draco Meteor", "U-turn", "Fire Blast"],
            "tera": "Ghost"
        },
        {
            "pokemon": "Gholdengo",
            "ability": "Good as Gold",
            "item": "Air Balloon",
            "moves": ["Make It Rain", "Shadow Ball", "Nasty Plot", "Recover"],
            "tera": "Steel"
        },
        {
            "pokemon": "Raging Bolt",
            "ability": "Protosynthesis",
            "item": "Booster Energy",
            "moves": ["Thunderbolt", "Dragon Pulse", "Calm Mind", "Thunderclap"],
            "tera": "Electric"
        }
    ]

    for i in range(num_battles):
        # Pick a random set
        import random
        set_data = random.choice(common_sets)

        battle_id = f"gen9ou-sim-{i:03d}"
        print(f"\n[Battle {i+1}/{num_battles}] {battle_id}")
        print(f"  Pokemon: {set_data['pokemon']}")

        # Start battle
        predictor.set_battle_context(
            battle_id=battle_id,
            tier="gen9ou",
            player_rating=random.randint(1500, 1800)
        )

        # Create prediction
        prediction = predictor.create_initial_prediction(set_data['pokemon'])

        # Simulate revealing 2 random moves
        revealed = random.sample(set_data['moves'], 2)
        for move in revealed:
            prediction = predictor.update_with_move(prediction, move)

        # Record final set
        predictor.finalize_pokemon(
            pokemon_name=set_data['pokemon'],
            final_ability=set_data['ability'],
            final_item=set_data['item'],
            final_moves=set_data['moves'],
            final_tera=set_data.get('tera'),
            final_spread=None
        )

        predictor.end_battle(winner=random.choice(["player", "opponent"]))

    # Show final statistics
    stats = predictor.get_statistics()
    print("\n" + "=" * 70)
    print("Data Collection Complete!")
    print("=" * 70)
    print(f"Total battles: {stats['total_battles']}")
    print(f"Total Pokemon: {stats['total_pokemon']}")
    print(f"Unique species: {stats['unique_species']}")
    print(f"\nML model trained: {stats['ml_trained']}")
    print(f"Current prediction blend: {stats['ml_weight']:.0%} ML, {stats['bayesian_weight']:.0%} Bayesian")

    if stats['most_common_pokemon']:
        print(f"\nMost common Pokemon:")
        for pokemon, count in stats['most_common_pokemon'][:5]:
            print(f"  - {pokemon}: {count} times")

    return predictor


def demonstrate_ml_improvement():
    """
    Show how predictions improve with ML training
    """
    print("\n" + "=" * 70)
    print("Demonstration: How ML Improves Predictions")
    print("=" * 70)

    # Simulate 60 battles to trigger ML training
    print("\nCollecting 60 battles to train ML models...")
    predictor = simulate_multiple_battles(num_battles=60)

    stats = predictor.get_statistics()

    if stats['ml_trained']:
        print("\n✅ ML models have been trained!")
        print("\nNow let's compare predictions:")

        # Test on Kingambit
        print("\n" + "-" * 70)
        print("Test Pokemon: Kingambit")
        print("Revealed: Sucker Punch, Swords Dance")
        print("-" * 70)

        predictor.set_battle_context(
            battle_id="test-comparison",
            tier="gen9ou",
            player_rating=1650
        )

        prediction = predictor.create_initial_prediction("Kingambit")
        prediction = predictor.update_with_move(prediction, "Sucker Punch")
        prediction = predictor.update_with_move(prediction, "Swords Dance")

        top = predictor.get_top_predictions(prediction, n=5)

        print("\nHybrid Prediction (Bayesian + ML):")
        print("  Top Items:")
        for item, prob in top['items'][:3]:
            print(f"    {item}: {prob:.1%}")

        print("\n  Top Remaining Moves:")
        for move, prob in top['moves'][:5]:
            print(f"    {move}: {prob:.1%}")

        print("\n📊 The more battles you collect, the better these predictions become!")
        print("   Current accuracy based on training:")
        if stats['training_history']:
            latest = stats['training_history'][-1]
            print(f"   - Item prediction: {latest['item_accuracy']:.1%}")
            print(f"   - Move F1 score: {latest['move_f1']:.1%}")
    else:
        print("\n⚠️  Need 50+ battles to train ML. Keep collecting data!")


def main():
    """Run examples"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  Pokemon Showdown Set Predictor - ML Training Tutorial          ║
║                                                                  ║
║  This example shows how to:                                     ║
║  1. Collect battle data                                         ║
║  2. Train ML models                                             ║
║  3. Get better predictions over time                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    try:
        # Check if ML libraries are available
        import xgboost
        import sklearn

        # Example 1: Single battle
        print("\n[Example 1] Single Battle Simulation")
        simulate_battle_example()

        # Example 2: Multiple battles
        print("\n\n[Example 2] Collecting Data from Multiple Battles")
        input("\nPress Enter to simulate 60 battles (takes ~5 seconds)...")
        demonstrate_ml_improvement()

        print("\n" + "=" * 70)
        print("Tutorial Complete!")
        print("=" * 70)
        print("\nNext Steps:")
        print("1. Integrate this into your Chrome extension")
        print("2. Parse real battles from Pokemon Showdown")
        print("3. Collect data as you play")
        print("4. Watch predictions improve automatically!")
        print("\nSee ML_ARCHITECTURE.md for detailed implementation guide.")

    except ImportError:
        print("\n❌ ML libraries not installed!")
        print("\nInstall them with:")
        print("  pip install xgboost scikit-learn numpy")
        print("\nThen run this example again.")


if __name__ == "__main__":
    main()
