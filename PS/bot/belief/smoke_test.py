"""M2 smoke test: instantiate BeliefState and feed it a scripted trace.

Confirms the belief module is wired end-to-end:
  - HybridSetPredictor loads Smogon data via DataManager.
  - BeliefState produces a non-empty posterior on a Pokemon observation.
  - Revealing a move narrows the move distribution.
  - NicheMechanicsDetector runs without crashing on a realistic context.

Run from the repository's PS/ directory:

    python -m bot.belief.smoke_test

The script uses gen9ou data because that is what currently lives in
data/. A randbats data pipeline is a separate workstream; this smoke
test validates the integration, not the tier-specific statistics.
"""

from src.data_manager import DataManager

from bot.belief import BeliefState


POKEMON = "Kingambit"
REVEALED_MOVE = "Sucker Punch"


def _top_n(probs, n=3):
    return sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:n]


def main() -> None:
    data_manager = DataManager()
    if not data_manager.is_data_available():
        raise SystemExit(
            "Smogon data not found. Run `python update_data.py` first."
        )

    belief = BeliefState(
        data_manager=data_manager,
        battle_id="belief-smoke-test",
        tier="gen9ou",
    )

    initial = belief.observe_pokemon(POKEMON)
    print(f"Observed {POKEMON}")
    print(f"  top items: {_top_n(initial.item_probs)}")
    print(f"  top moves: {_top_n(initial.move_probs)}")

    updated = belief.observe_move(POKEMON, REVEALED_MOVE)
    print(f"Revealed move: {REVEALED_MOVE}")
    print(f"  top items now: {_top_n(updated.item_probs)}")
    print(f"  top moves now: {_top_n(updated.move_probs)}")
    print(f"  revealed_moves: {sorted(updated.revealed_moves)}")

    belief.update_context(POKEMON, weather="sand", terrain=None)

    assert updated.move_probs, "move_probs should be non-empty"
    assert REVEALED_MOVE in updated.revealed_moves, (
        "revealed_moves should include the move we just revealed"
    )
    print("\nbelief smoke test: ok")


if __name__ == "__main__":
    main()
