# Pokemon Team Generator - Project Specifications

## Project Overview
A competitive Pokemon team generator that analyzes the OU (OverUsed) metagame to create viable, competitive teams that can handle popular threats and team compositions.

## Current Scope
- **Tier**: OU (OverUsed) only
- **Generation**: Gen 9 (Scarlet/Violet)
- **Output**: 6-Pokemon teams with movesets, EVs, items, and abilities

---

## Phase 1: Data Infrastructure

### 1.1 Data Sources
- **Smogon Usage Statistics**: https://www.smogon.com/stats/
  - Monthly usage stats (Pokemon usage %, moveset data, item data, ability data)
  - Format: Plain text files with structured data
  - Example: `https://www.smogon.com/stats/2024-10/gen9ou-1500.txt` (usage rankings)
  - Example: `https://www.smogon.com/stats/2024-10/moveset/gen9ou-1500.txt` (detailed movesets)

- **Pokemon Showdown Data**: https://github.com/smogon/pokemon-showdown
  - Pokemon base stats, types, abilities
  - Move data (power, accuracy, type, category)
  - Item effects
  - Format: JSON/JavaScript files

- **Pikalytics** (Optional): https://pikalytics.com/
  - Alternative source for usage data
  - Team composition insights

### 1.2 Data Collection System
**Components:**
- `data_fetcher.py`: Downloads latest usage stats from Smogon
- `pokemon_data_parser.py`: Parses Pokemon Showdown data files
- `usage_parser.py`: Parses Smogon usage statistics

**Storage Structure:**
```
data/
├── pokemon/          # Pokemon base data
│   ├── pokedex.json  # All Pokemon stats, types, abilities
│   ├── moves.json    # All moves data
│   └── items.json    # All items data
├── usage/            # Usage statistics
│   ├── gen9ou_usage.json
│   └── gen9ou_movesets.json
└── cache/            # Cached API responses
```

### 1.3 Data Models
```python
Pokemon:
  - name: str
  - types: List[str]
  - base_stats: Dict[str, int]  # HP, Atk, Def, SpA, SpD, Spe
  - abilities: List[str]
  - common_moves: List[str]
  - usage_rank: int
  - usage_percent: float

Moveset:
  - pokemon: str
  - ability: str
  - item: str
  - moves: List[str] (4 moves)
  - evs: Dict[str, int]
  - nature: str
  - tera_type: str (Gen 9 specific)

Team:
  - pokemon_list: List[Moveset] (6 Pokemon)
  - archetype: str
  - roles: Dict[str, str]  # Pokemon -> Role mapping
  - score: float  # Effectiveness score
```

---

## Phase 2: Core Analysis Engine

### 2.1 Metagame Analyzer
**Purpose**: Identify threats and trends in OU tier

**Components:**
- `meta_analyzer.py`: Main analysis engine
- `threat_detector.py`: Identifies top threats (usage > 10%)
- `archetype_classifier.py`: Categorizes team styles

**Metrics to Track:**
- Top 20 Pokemon by usage
- Most common offensive types
- Most common defensive types
- Speed tier distribution
- Common abilities (Regenerator, Protean, etc.)
- Common items (Choice items, Leftovers, Heavy-Duty Boots)

### 2.2 Team Composition Logic
**Core Roles:**
- **Offensive Sweeper**: High attack/special attack, setup moves
- **Defensive Wall**: High defenses, recovery moves
- **Pivot**: U-turn/Volt Switch, momentum control
- **Hazard Setter**: Stealth Rock, Spikes
- **Hazard Remover**: Rapid Spin, Defog
- **Speed Control**: Choice Scarf, Trick Room setter

**Type Coverage:**
- Ensure offensive coverage of all 18 types
- Minimize shared weaknesses
- Have answers to top threats

---

## Phase 3: Team Generation Algorithm

### 3.1 Building Strategy
**Step 1: Core Selection (2-3 Pokemon)**
- Pick high-usage Pokemon that synergize well
- Ensure type diversity
- Cover each other's weaknesses

**Step 2: Role Fulfillment**
- Add defensive backbone (1-2 walls)
- Add offensive pressure (1-2 sweepers)
- Add utility (pivot, hazard control)

**Step 3: Threat Coverage**
- Check against top 20 meta threats
- Ensure at least 2 answers to each major threat
- Validate no major gaps

**Step 4: Archetype Matching**
- Balance: Mix of offense/defense
- Hyper Offense: 4+ offensive Pokemon
- Bulky Offense: 2-3 walls, 3-4 attackers
- Stall: 5+ defensive Pokemon

### 3.2 Team Validation
**Legality Checks:**
- No duplicate Pokemon
- No illegal move/ability combinations
- Obeys OU tier rules (no Ubers)
- Species Clause compliant

**Quality Checks:**
- Type coverage score > 80%
- At least 1 hazard setter
- At least 1 hazard remover
- Speed diversity (fast, medium, slow Pokemon)

---

## Phase 4: Intelligence & Optimization

### 4.1 Scoring System
**Team Effectiveness Score (0-100):**
- Usage alignment: 25 points (using meta-relevant Pokemon)
- Type coverage: 20 points (offensive coverage)
- Defensive synergy: 20 points (resist coverage)
- Threat handling: 25 points (can beat top threats)
- Team balance: 10 points (role distribution)

### 4.2 Advanced Features
- Suggest movesets based on current month's usage
- EV spread optimization for specific matchups
- Alternative Pokemon suggestions for team slots
- Team weakness report

---

## Phase 5: User Interface

### 5.1 CLI Tool (Initial Implementation)
**Commands:**
```
python team_gen.py generate --tier ou --archetype balance
python team_gen.py analyze-team <team_file>
python team_gen.py update-data
python team_gen.py show-meta
```

**Output Format:**
- Plain text team export (Pokemon Showdown format)
- JSON format for programmatic use
- Analysis report with strengths/weaknesses

### 5.2 Future: Web Interface
- Team builder UI
- Drag-and-drop Pokemon selection
- Interactive coverage chart
- One-click export to Pokemon Showdown

---

## Technology Stack

### Core Technologies
- **Language**: Python 3.11+
- **HTTP Requests**: `requests` library
- **Data Processing**: `pandas` (optional, for stats)
- **Data Storage**: JSON files (SQLite if scaling)

### Python Libraries
```
requests          # HTTP requests for data fetching
beautifulsoup4    # HTML parsing if needed
pytest            # Testing
click             # CLI interface
python-dotenv     # Environment variables
```

### Optional Libraries
```
poke-env          # Pokemon Showdown battle simulation
smogon            # Smogon API wrapper (if available)
numpy             # Numerical calculations
```

---

## Implementation Timeline

### Week 1: Phase 1 - Data Infrastructure
- [x] Set up project structure
- [ ] Implement Smogon usage stats fetcher
- [ ] Parse Pokemon Showdown data
- [ ] Create data storage system
- [ ] Test data retrieval and parsing

### Week 2: Phase 2 - Analysis Engine
- [ ] Build metagame analyzer
- [ ] Implement threat detection
- [ ] Create type coverage calculator
- [ ] Build synergy evaluator

### Week 3: Phase 3 - Team Generation
- [ ] Core selection algorithm
- [ ] Role fulfillment system
- [ ] Team validation
- [ ] Moveset assignment

### Week 4: Phase 4 & 5 - Optimization & UI
- [ ] Scoring system
- [ ] CLI interface
- [ ] Testing with real teams
- [ ] Documentation

---

## Key Considerations

### OU Tier Rules (Gen 9)
- **Banned Pokemon**: All Ubers, restricted legendaries
- **Clauses**:
  - Species Clause: No duplicate Pokemon
  - Sleep Clause: Only one Pokemon can be put to sleep at a time
  - Evasion Clause: No evasion-boosting moves (Double Team, Minimize)
  - OHKO Clause: No one-hit-KO moves
  - Endless Battle Clause: Battles must end

### Metagame Shifts
- Usage stats update monthly
- New Pokemon/moves/mechanics can shift meta dramatically
- Need periodic data updates (automated monthly fetch)

### Common OU Archetypes (Gen 9)
1. **Balance**: Mixed offense/defense, adapts to opponent
2. **Hyper Offense (HO)**: Fast, aggressive, focuses on early game pressure
3. **Bulky Offense**: Offensive with defensive backbone
4. **Stall**: Extremely defensive, wins through chip damage
5. **Weather Teams**: Rain (Swift Swim), Sun (Chlorophyll), Sand (Sand Rush)
6. **Trick Room**: Slow, powerful Pokemon under Trick Room

### Team Building Philosophy
- **Core + Support**: Build around 2-3 core Pokemon, add support
- **Defensive Backbone**: At least 1-2 Pokemon that can take hits
- **Offensive Pressure**: Force opponent into unfavorable positions
- **Hazard Control**: Stealth Rock is critical, need setter + remover
- **Coverage**: Hit everything for neutral damage minimum

---

## Future Enhancements

### Machine Learning Integration
- Train model on successful teams from tournaments
- Pattern recognition for team compositions
- Predict team effectiveness against meta

### Battle Simulation
- Use `poke-env` to simulate battles
- Test generated teams against common teams
- Iteratively improve team based on battle results

### Multi-Tier Support
- Expand to UU, RU, NU, PU tiers
- Cross-tier analysis
- Tier-specific strategies

### Real-Time Updates
- WebSocket connection to Smogon for live updates
- Discord bot for team generation
- API endpoint for external tools

---

## Notes & References

### Useful Resources
- Smogon Strategy Pokedex: https://www.smogon.com/dex/sv/pokemon/
- Pokemon Showdown: https://play.pokemonshowdown.com/
- Pikalytics: https://pikalytics.com/
- Smogon Forums: https://www.smogon.com/forums/

### Data Update Schedule
- Smogon stats: Monthly (typically by 5th of each month)
- Tier shifts: Every 3 months
- Pokemon Showdown updates: As patches release

### Testing Strategy
- Unit tests for each component
- Integration tests for team generation
- Validate against known good teams
- Test against top ladder teams

---

## Current Status
- **Phase**: 1 (Data Infrastructure)
- **Tier**: OU only
- **Last Updated**: October 27, 2024
