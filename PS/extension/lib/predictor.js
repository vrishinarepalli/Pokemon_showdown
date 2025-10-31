/**
 * Set Predictor - JavaScript port
 * Predicts Pokemon sets using Bayesian inference
 */

class SetPredictor {
    constructor(smogonData) {
        this.smogonData = smogonData;
        this.tier = 'gen9ou';

        // Non-attacking moves (blocked by Assault Vest)
        this.nonAttackingMoves = new Set([
            'Swords Dance', 'Nasty Plot', 'Dragon Dance', 'Calm Mind', 'Bulk Up', 'Quiver Dance',
            'Stealth Rock', 'Spikes', 'Toxic Spikes', 'Sticky Web',
            'Thunder Wave', 'Will-O-Wisp', 'Toxic', 'Spore', 'Sleep Powder', 'Hypnosis',
            'Recover', 'Roost', 'Soft-Boiled', 'Wish', 'Synthesis', 'Morning Sun', 'Moonlight',
            'Protect', 'Detect', 'Substitute', 'Taunt', 'Encore', 'Trick', 'Switcheroo',
            'Defog', 'Haze', 'Whirlwind', 'Roar',
            'Light Screen', 'Reflect', 'Tailwind', 'Trick Room', 'Magic Room', 'Wonder Room',
            'Leech Seed', 'Rest', 'Sleep Talk', 'Baton Pass',
            'Teleport', 'Parting Shot'
        ]);
    }

    /**
     * Create initial prediction when Pokemon is first seen
     */
    createInitialPrediction(pokemonName) {
        const movesetData = this.smogonData.movesets[pokemonName];

        if (!movesetData) {
            console.warn(`No moveset data for ${pokemonName}`);
            return this.createEmptyPrediction(pokemonName);
        }

        return {
            pokemon: pokemonName,
            revealedMoves: new Set(),
            revealedAbility: null,
            revealedItem: null,
            revealedTera: null,
            abilityProbs: this.normalizeProbs(movesetData.abilities || {}),
            itemProbs: this.normalizeProbs(movesetData.items || {}),
            moveProbs: this.normalizeProbs(movesetData.moves || {}),
            spreadProbs: this.normalizeProbs(movesetData.spreads || {}),
            teraProbs: this.normalizeProbs(movesetData.tera_types || {}),
            impossibleItems: new Set(),
            confidence: 0.2,
            turnsSeen: 0
        };
    }

    /**
     * Create empty prediction
     */
    createEmptyPrediction(pokemonName) {
        return {
            pokemon: pokemonName,
            revealedMoves: new Set(),
            revealedAbility: null,
            revealedItem: null,
            revealedTera: null,
            abilityProbs: {},
            itemProbs: {},
            moveProbs: {},
            spreadProbs: {},
            teraProbs: {},
            impossibleItems: new Set(),
            confidence: 0,
            turnsSeen: 0
        };
    }

    /**
     * Update prediction with revealed move
     */
    updateWithMove(prediction, moveName) {
        prediction.revealedMoves.add(moveName);
        prediction.turnsSeen++;

        // Set move to 100%
        prediction.moveProbs[moveName] = 1.0;

        // Apply game mechanic constraints
        this.applyMoveConstraints(prediction, moveName);

        // Update correlated probabilities
        this.updateCorrelatedMoves(prediction, moveName);
        this.updateCorrelatedItems(prediction, moveName);

        // Recalculate confidence
        prediction.confidence = this.calculateConfidence(prediction);

        return prediction;
    }

    /**
     * Update prediction with revealed ability
     */
    updateWithAbility(prediction, abilityName) {
        prediction.revealedAbility = abilityName;
        prediction.turnsSeen++;

        // Set ability to 100%
        prediction.abilityProbs = { [abilityName]: 1.0 };

        prediction.confidence = this.calculateConfidence(prediction);
        return prediction;
    }

    /**
     * Update prediction with revealed item
     */
    updateWithItem(prediction, itemName) {
        prediction.revealedItem = itemName;
        prediction.turnsSeen++;

        // Set item to 100%
        prediction.itemProbs = { [itemName]: 1.0 };

        prediction.confidence = this.calculateConfidence(prediction);
        return prediction;
    }

    /**
     * Apply game mechanic constraints
     */
    applyMoveConstraints(prediction, moveName) {
        if (prediction.revealedItem) return;

        // CONSTRAINT 1: 2+ moves → NOT Choice item
        if (prediction.revealedMoves.size >= 2) {
            const choiceItems = ['Choice Band', 'Choice Scarf', 'Choice Specs'];
            choiceItems.forEach(item => {
                if (!prediction.impossibleItems.has(item)) {
                    prediction.impossibleItems.add(item);
                    console.log(`⚠️ Ruled out ${item} (${prediction.revealedMoves.size} moves)`);
                }
            });
        }

        // CONSTRAINT 2: Status move → NOT Assault Vest
        if (this.nonAttackingMoves.has(moveName)) {
            if (!prediction.impossibleItems.has('Assault Vest')) {
                prediction.impossibleItems.add('Assault Vest');
                console.log(`⚠️ Ruled out Assault Vest (status move: ${moveName})`);
            }
        }

        // Remove impossible items
        prediction.impossibleItems.forEach(item => {
            delete prediction.itemProbs[item];
        });

        // Renormalize
        prediction.itemProbs = this.normalizeProbs(prediction.itemProbs, false);
    }

    /**
     * Apply damage-based constraints
     */
    applyDamageConstraints(prediction, options = {}) {
        if (prediction.revealedItem) return;

        const { tookHazardDamage, healedOverTime, tookRecoil } = options;

        // Took hazard damage → NOT Heavy-Duty Boots
        if (tookHazardDamage) {
            if (!prediction.impossibleItems.has('Heavy-Duty Boots')) {
                prediction.impossibleItems.add('Heavy-Duty Boots');
                console.log(`⚠️ Ruled out Heavy-Duty Boots (took hazard damage)`);
                delete prediction.itemProbs['Heavy-Duty Boots'];
            }
        }

        // Healed over time → likely Leftovers/Black Sludge
        if (healedOverTime) {
            const healingItems = ['Leftovers', 'Black Sludge'];
            healingItems.forEach(item => {
                if (prediction.itemProbs[item]) {
                    prediction.itemProbs[item] *= 3.0;
                }
            });
        }

        // Took recoil → likely Life Orb
        if (tookRecoil) {
            if (prediction.itemProbs['Life Orb']) {
                prediction.itemProbs['Life Orb'] *= 2.0;
            }
        }

        // Renormalize
        prediction.itemProbs = this.normalizeProbs(prediction.itemProbs, false);
    }

    /**
     * Apply Booster Energy detection based on ability activation
     *
     * Protosynthesis/Quark Drive can activate two ways:
     * 1. Naturally (Sun for Protosynthesis, Electric Terrain for Quark Drive)
     * 2. Via Booster Energy item (when weather/terrain not present)
     */
    applyAbilityActivationConstraint(prediction, options = {}) {
        if (prediction.revealedItem) return;

        const { abilityActivatedOnSwitch, sunActive, electricTerrainActive } = options;

        // Check if ability is Protosynthesis or Quark Drive
        const isProtosynthesis = prediction.revealedAbility === 'Protosynthesis';
        const isQuarkDrive = prediction.revealedAbility === 'Quark Drive';

        if (!isProtosynthesis && !isQuarkDrive) return;

        if (abilityActivatedOnSwitch) {
            // Protosynthesis activates in sun naturally
            if (isProtosynthesis && sunActive) {
                console.log('ℹ️ Protosynthesis activated naturally (sun present)');
                console.log('   Item is unknown - could be anything');
                return;
            }

            // Quark Drive activates in Electric Terrain naturally
            if (isQuarkDrive && electricTerrainActive) {
                console.log('ℹ️ Quark Drive activated naturally (Electric Terrain present)');
                console.log('   Item is unknown - could be anything');
                return;
            }

            // If ability activated but NO weather/terrain, must be Booster Energy!
            if (isProtosynthesis && !sunActive) {
                console.log('⚡ Protosynthesis activated without sun!');
                console.log('✓ Item CONFIRMED: Booster Energy');
                prediction.revealedItem = 'Booster Energy';
                prediction.itemProbs = { 'Booster Energy': 1.0 };
            } else if (isQuarkDrive && !electricTerrainActive) {
                console.log('⚡ Quark Drive activated without Electric Terrain!');
                console.log('✓ Item CONFIRMED: Booster Energy');
                prediction.revealedItem = 'Booster Energy';
                prediction.itemProbs = { 'Booster Energy': 1.0 };
            }
        }
    }

    /**
     * Update correlated move probabilities
     */
    updateCorrelatedMoves(prediction, revealedMove) {
        // Move synergies
        const synergies = {
            'Swords Dance': ['Sucker Punch', 'Close Combat', 'Iron Head', 'Earthquake'],
            'Nasty Plot': ['Dark Pulse', 'Sludge Bomb', 'Flamethrower', 'Focus Blast'],
            'Dragon Dance': ['Outrage', 'Earthquake', 'Extreme Speed', 'Fire Punch'],
            'U-turn': ['Earthquake', 'Close Combat', 'Stone Edge'],
            'Volt Switch': ['Thunderbolt', 'Hidden Power', 'Focus Blast'],
            'Stealth Rock': ['Rapid Spin', 'Earthquake', 'Close Combat']
        };

        if (synergies[revealedMove]) {
            const boostFactor = 1.5;
            synergies[revealedMove].forEach(move => {
                if (prediction.moveProbs[move] && !prediction.revealedMoves.has(move)) {
                    prediction.moveProbs[move] *= boostFactor;
                }
            });

            // Renormalize
            prediction.moveProbs = this.normalizeProbs(prediction.moveProbs, false);
        }
    }

    /**
     * Update correlated item probabilities
     */
    updateCorrelatedItems(prediction, revealedMove) {
        if (prediction.revealedItem) return;

        const moveItemHints = {
            'Swords Dance': ['Leftovers', 'Life Orb', 'Lum Berry'],
            'Nasty Plot': ['Leftovers', 'Life Orb', 'Focus Sash'],
            'Dragon Dance': ['Leftovers', 'Lum Berry', 'Life Orb'],
            'U-turn': ['Choice Scarf', 'Choice Band', 'Heavy-Duty Boots'],
            'Volt Switch': ['Choice Specs', 'Choice Scarf', 'Heavy-Duty Boots'],
            'Stealth Rock': ['Leftovers', 'Rocky Helmet', 'Heavy-Duty Boots'],
            'Protect': ['Leftovers', 'Black Sludge', 'Sitrus Berry']
        };

        if (moveItemHints[revealedMove]) {
            const boostFactor = 1.3;
            moveItemHints[revealedMove].forEach(item => {
                if (prediction.itemProbs[item]) {
                    prediction.itemProbs[item] *= boostFactor;
                }
            });

            // Renormalize
            prediction.itemProbs = this.normalizeProbs(prediction.itemProbs, false);
        }
    }

    /**
     * Calculate prediction confidence
     */
    calculateConfidence(prediction) {
        let revealedCount = prediction.revealedMoves.size;
        if (prediction.revealedAbility) revealedCount++;
        if (prediction.revealedItem) revealedCount++;

        const baseConfidence = revealedCount / 6.0;

        // Distribution confidence (higher max prob = more confident)
        const maxMoveProb = Math.max(...Object.values(prediction.moveProbs), 0);
        const maxItemProb = Math.max(...Object.values(prediction.itemProbs), 0);
        const maxAbilityProb = Math.max(...Object.values(prediction.abilityProbs), 0);

        const distributionConfidence = (maxMoveProb + maxItemProb + maxAbilityProb) / 3.0;

        return Math.min(1.0, 0.6 * baseConfidence + 0.4 * distributionConfidence);
    }

    /**
     * Get top N predictions
     */
    getTopPredictions(prediction, n = 5) {
        const result = {};

        // Abilities
        if (!prediction.revealedAbility) {
            result.abilities = this.getTopN(prediction.abilityProbs, n);
        } else {
            result.abilities = [[prediction.revealedAbility, 1.0]];
        }

        // Items
        if (!prediction.revealedItem) {
            result.items = this.getTopN(prediction.itemProbs, n);
        } else {
            result.items = [[prediction.revealedItem, 1.0]];
        }

        // Unrevealed moves
        const unrevealedMoves = {};
        for (const [move, prob] of Object.entries(prediction.moveProbs)) {
            if (!prediction.revealedMoves.has(move)) {
                unrevealedMoves[move] = prob;
            }
        }
        result.moves = this.getTopN(unrevealedMoves, n);

        // Revealed moves
        result.revealedMoves = Array.from(prediction.revealedMoves);

        return result;
    }

    /**
     * Helper: Get top N from probability dict
     */
    getTopN(probs, n) {
        return Object.entries(probs)
            .sort((a, b) => b[1] - a[1])
            .slice(0, n);
    }

    /**
     * Helper: Normalize probabilities
     */
    normalizeProbs(data, convertPercent = true) {
        if (!data || Object.keys(data).length === 0) return {};

        // Convert percentages to decimals if needed
        let probs = convertPercent ?
            Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v / 100.0])) :
            { ...data };

        // Normalize to sum to 1.0
        const total = Object.values(probs).reduce((sum, val) => sum + val, 0);
        if (total > 0) {
            probs = Object.fromEntries(
                Object.entries(probs).map(([k, v]) => [k, v / total])
            );
        }

        return probs;
    }
}
