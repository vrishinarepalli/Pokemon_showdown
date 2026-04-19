# Pokémon Showdown AI – Project Design Doc (v0.1)

## 1. Project Overview

**Goal:**  
Build an AI agent that can battle on Pokémon Showdown (or a local Showdown server) against a human trainer or scripted bots.  
The AI should:

- Start with basic “good enough” knowledge (hard-coded heuristics + usage data).
- Use Machine Learning to improve its battle decisions over time.
- Eventually support multiple difficulty levels (from casual to highly competitive).

For now, we focus on:

1. Single difficulty level (≈ “Normal”).
2. Single format (e.g., **Gen 9 OU** or **Random Battle**) to keep scope manageable.
3. Battles vs:
   - A human player (you) OR
   - A simple scripted opponent for testing.

---

## 2. High-Level Requirements

### Functional Requirements

- Connect to a Pokémon Showdown server (public or local).
- Join battles and choose valid moves each turn.
- Track battle state:
  - Own team: HP, statuses, boosts, revealed moves/items, etc.
  - Opponent: revealed Pokémon, moves, items, hazards, boosts, etc.
- Decide actions each turn:
  - Choose **move** OR **switch**.
- Log battle data for training:
  - State → Action → Result (win/loss, damage dealt, positional advantage, etc.).
- Provide at least one baseline AI policy that does **not** learn (for comparison).
- Provide one learning-based AI policy (even if it’s simple at first).

### Non-Functional Requirements

- Modular design (easy to swap out AI models and difficulty policies).
- Reproducible (seeded randomness for experiments).
- Extensible for:
  - Additional formats (e.g., VGC, Monotype).
  - Different generations.
  - New difficulty tiers.

---

## 3. Tech Stack

**Languages / Frameworks (proposed):**

- **Python** for the AI logic and ML pipeline.
- **Websocket / HTTP client** for interacting with Showdown (e.g., `websockets`, `aiohttp` or custom PS client lib).
- **ML / Data**:
  - `PyTorch` or `TensorFlow` / `Keras` for neural models.
  - `pandas`, `numpy` for data handling and feature extraction.
- **Storage**:
  - Local JSON/CSV/Parquet files for battle logs in v0.
  - (Optional later) SQLite/Postgres for large-scale training data.

---

## 4. System Architecture

### 4.1 Modules

1. **Showdown Client Layer**
   - Handles connection to server via websocket.
   - Joins/creates battles.
   - Parses server messages into a structured, internal representation.
   - Sends action commands to server (choose move, switch, etc.).

2. **Battle State Representation**
   - Maintains current game state:
     - Active Pokémon (both sides).
     - Remaining team members.
     - HP, status, stat boosts, hazards, weather, terrain, screens, etc.
   - Provides a **feature vector** / structured object for the AI.

3. **AI Decision Engine**
   - Interface: `action = policy.get_action(state)`
   - Pluggable policies:
     - `RuleBasedPolicy` (baseline).
     - `MLPolicy` (uses trained model).
     - Future: `RLPolicy`, `SearchPolicy` (MCTS), etc.

4. **Data Logger**
   - Records:
     - State features.
     - Action taken.
     - Turn result / reward.
     - Final battle outcome (win/loss).
   - Saves logs to disk for training.

5. **Training Pipeline**
   - Loads logged battles.
   - Cleans and encodes features.
   - Trains ML model:
     - Supervised learning from “good” actions OR
     - Reinforcement learning from rewards.
   - Exports trained model for use in `MLPolicy`.

6. **Difficulty Manager (Future)**
   - Wrapper that selects which policy to use or how “smart” a policy acts.
   - Examples:
     - Easy: mostly rule-based with random noise.
     - Normal: ML policy but limited look-ahead or imperfect info.
     - Hard: best available model, minimal randomness, deeper search.

---

## 5. AI / ML Approach

### 5.1 Phase 1 – Baseline Heuristic Bot

Start simple. No learning yet.

- Hard-coded heuristics:
  - Prefer super-effective moves.
  - Avoid moves that are “not very effective” or immune.
  - Consider STAB.
  - Consider expected KOs based on rough damage estimation.
  - Basic switching rules.

### 5.2 Phase 2 – Supervised Learning

Train a model to imitate stronger behavior.

### 5.3 Phase 3 – Reinforcement Learning (Long-Term)

Use RL to improve surpassing the initial heuristic.

---

## 6. Difficulty Levels (Design for Later)

Future difficulty knobs listed.

---

## 7. Data & Feature Engineering

Includes full description of state features, encoding, etc.

---

## 8. Milestones & Roadmap

Milestones 0–4 listed in full.

---

## 9. Folder Structure (Draft)

Full tree included.

---

## 10. Open Questions

---

## 11. Next Steps

---
