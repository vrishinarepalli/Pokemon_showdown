"""Battle logging and decision tracking for debugging M4's decision-making.

Logs each turn's available actions, their scores, and the chosen action,
along with team compositions and battle outcome.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import json
from datetime import datetime


@dataclass
class Decision:
    """A single decision (move/switch choice) made during a turn."""
    turn: int
    action_type: str  # "move", "switch", "forced"
    action_name: str
    score: float
    our_hp: float
    opp_hp: float
    chosen: bool


@dataclass
class TurnLog:
    """All decisions evaluated on a single turn."""
    turn: int
    our_pokemon: str
    opp_pokemon: str
    our_hp: float
    opp_hp: float
    decisions: List[Decision] = field(default_factory=list)
    # What opponent did on the PREVIOUS turn (visible at start of this turn)
    opp_last_move: Optional[str] = None
    opp_last_action: Optional[str] = None  # "move" or "switch"
    opp_prev_pokemon: Optional[str] = None  # Their pokemon last turn (if different)


@dataclass
class BattleLog:
    """Complete log of a single battle."""
    battle_id: str
    timestamp: str
    our_team: Dict[str, Any]
    opp_team: Dict[str, Any]
    our_name: str
    opp_name: str
    winner: Optional[str]  # "us", "them", or None if incomplete
    turns: List[TurnLog] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        def sanitize_score(score: float) -> float:
            """Convert -inf to large negative, +inf to large positive for JSON."""
            if score == float("-inf"):
                return -999.0
            elif score == float("inf"):
                return 999.0
            return round(score, 4)

        return {
            "battle_id": self.battle_id,
            "timestamp": self.timestamp,
            "our_name": self.our_name,
            "opp_name": self.opp_name,
            "our_team": self.our_team,
            "opp_team": self.opp_team,
            "winner": self.winner,
            "turns": [
                {
                    "turn": t.turn,
                    "our_pokemon": t.our_pokemon,
                    "opp_pokemon": t.opp_pokemon,
                    "our_hp": round(t.our_hp, 3),
                    "opp_hp": round(t.opp_hp, 3),
                    "opp_last_move": t.opp_last_move,
                    "opp_last_action": t.opp_last_action,
                    "opp_prev_pokemon": t.opp_prev_pokemon,
                    "decisions": [
                        {
                            "type": d.action_type,
                            "name": d.action_name,
                            "score": sanitize_score(d.score),
                            "chosen": d.chosen,
                        }
                        for d in t.decisions
                    ]
                }
                for t in self.turns
            ]
        }


class BattleLogger:
    """Track decisions and outcomes for a battle."""

    def __init__(self, battle_id: str, our_name: str, opp_name: str):
        self.battle_id = battle_id
        self.our_name = our_name
        self.opp_name = opp_name
        self.timestamp = datetime.now().isoformat()
        self.our_team: Dict[str, Any] = {}
        self.opp_team: Dict[str, Any] = {}
        self.turns: List[TurnLog] = []
        self.current_turn: Optional[TurnLog] = None
        self.winner: Optional[str] = None

    def set_teams(self, our_team: Dict[str, Any], opp_team: Dict[str, Any]):
        """Record team compositions at battle start."""
        self.our_team = our_team
        self.opp_team = opp_team

    def start_turn(self, turn: int, our_pokemon: str, opp_pokemon: str,
                   our_hp: float, opp_hp: float,
                   opp_last_move: Optional[str] = None,
                   opp_last_action: Optional[str] = None,
                   opp_prev_pokemon: Optional[str] = None):
        """Mark the start of a new turn."""
        self.current_turn = TurnLog(
            turn=turn,
            our_pokemon=our_pokemon,
            opp_pokemon=opp_pokemon,
            our_hp=our_hp,
            opp_hp=opp_hp,
            opp_last_move=opp_last_move,
            opp_last_action=opp_last_action,
            opp_prev_pokemon=opp_prev_pokemon,
        )

    def log_decision(self, action_type: str, action_name: str, score: float,
                     our_hp: float, opp_hp: float, chosen: bool = False):
        """Log a move/switch option evaluated this turn."""
        if self.current_turn is None:
            return
        decision = Decision(
            turn=self.current_turn.turn,
            action_type=action_type,
            action_name=action_name,
            score=score,
            our_hp=our_hp,
            opp_hp=opp_hp,
            chosen=chosen,
        )
        self.current_turn.decisions.append(decision)

    def end_turn(self):
        """Finalize the current turn."""
        if self.current_turn is not None:
            self.turns.append(self.current_turn)
            self.current_turn = None

    def set_winner(self, winner: str):
        """Record battle outcome."""
        self.winner = winner

    def get_log(self) -> BattleLog:
        """Get the complete battle log."""
        return BattleLog(
            battle_id=self.battle_id,
            timestamp=self.timestamp,
            our_team=self.our_team,
            opp_team=self.opp_team,
            our_name=self.our_name,
            opp_name=self.opp_name,
            winner=self.winner,
            turns=self.turns,
        )


class BattleLogCollector:
    """Collect logs from multiple battles and provide analysis."""

    def __init__(self):
        self.logs: List[BattleLog] = []

    def add_log(self, log: BattleLog):
        """Add a battle log to the collection."""
        self.logs.append(log)

    def save_to_file(self, filename: str):
        """Save all logs to a JSON file."""
        data = [log.to_dict() for log in self.logs]
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def analyze_switches(self) -> Dict[str, Any]:
        """Analyze switching patterns: which switches were chosen and their outcomes."""
        switch_outcomes = {"good": [], "bad": []}

        for log in self.logs:
            for turn in log.turns:
                for decision in turn.decisions:
                    if decision.action_type == "switch" and decision.chosen:
                        # Next turn, did we win/lose HP?
                        switch_outcomes["good" if decision.score > 0.2 else "bad"].append({
                            "battle": log.battle_id,
                            "turn": turn.turn,
                            "switched_to": decision.action_name,
                            "score": decision.score,
                            "outcome": log.winner,
                        })

        return switch_outcomes

    def print_summary(self):
        """Print a summary of all logged battles."""
        total = len(self.logs)
        wins = sum(1 for log in self.logs if log.winner == "us")
        winrate = (wins / total * 100) if total else 0.0

        print(f"\n{'='*60}")
        print(f"Battle Log Summary: {wins}/{total} wins ({winrate:.1f}%)")
        print(f"{'='*60}\n")

        for log in self.logs[-5:]:  # Show last 5 battles
            outcome = f"WIN" if log.winner == "us" else "LOSS" if log.winner == "them" else "??"
            print(f"Battle {log.battle_id} ({outcome}):")
            print(f"  {log.our_name} vs {log.opp_name}")
            print(f"  {len(log.turns)} turns")

            # Find questionable switches
            for turn in log.turns:
                switches = [d for d in turn.decisions if d.action_type == "switch"]
                if switches and any(d.chosen for d in switches):
                    chosen = [d for d in switches if d.chosen][0]
                    all_scores = [d.score for d in turn.decisions]
                    if chosen.score < max(all_scores) - 0.05:
                        print(f"    Turn {turn.turn}: SWITCHED TO {chosen.action_name} (score={chosen.score:.3f})")
                        print(f"      Available: {[(d.action_name, d.score) for d in turn.decisions[:3]]}")
            print()
