/**
 * Main Content Script for Pokemon Showdown Set Predictor
 * Connects battle parser, predictor, and UI
 */

(function() {
    'use strict';

    console.log('🎮 Pokemon Showdown Set Predictor loaded');

    // Global state
    let battleParser = null;
    let predictor = null;
    let predictionUI = null;
    let currentPredictions = new Map(); // pokemon -> prediction

    /**
     * Initialize extension
     */
    function init() {
        // Check if we're on a battle page
        if (!window.location.href.includes('pokemonshowdown.com')) {
            console.log('Not on Pokemon Showdown, extension inactive');
            return;
        }

        console.log('✓ On Pokemon Showdown, initializing...');

        // Initialize components
        battleParser = new BattleParser();
        predictionUI = new PredictionUI();
        predictionUI.init();

        // Check if Smogon data is loaded
        if (typeof SMOGON_DATA === 'undefined') {
            console.warn('⚠️ Smogon data not loaded, predictor will have limited functionality');
            return;
        }

        predictor = new SetPredictor(SMOGON_DATA);
        console.log('✓ Predictor initialized');

        // Subscribe to battle events
        battleParser.subscribe(handleBattleEvent);

        // Hook into Pokemon Showdown's battle system
        hookBattleSystem();

        console.log('✓ Set Predictor ready!');
    }

    /**
     * Hook into Pokemon Showdown's battle system
     */
    function hookBattleSystem() {
        // Pokemon Showdown uses a custom app.receive() method to handle messages
        // We need to intercept battle messages

        // Method 1: MutationObserver on battle log
        observeBattleLog();

        // Method 2: Listen for custom events (if PS implements them)
        window.addEventListener('ps-battle-message', (event) => {
            if (event.detail && event.detail.message) {
                processBattleMessage(event.detail.message);
            }
        });
    }

    /**
     * Observe battle log for new messages
     */
    function observeBattleLog() {
        // Wait for battle log element to exist
        const checkBattleLog = setInterval(() => {
            // Pokemon Showdown's battle log container
            const battleLog = document.querySelector('.battle-log');

            if (battleLog) {
                clearInterval(checkBattleLog);

                console.log('✓ Found battle log, setting up observer');

                // Create observer
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                            mutation.addedNodes.forEach((node) => {
                                if (node.textContent) {
                                    const lines = node.textContent.split('\n');
                                    lines.forEach(line => {
                                        if (line.startsWith('|')) {
                                            processBattleMessage(line);
                                        }
                                    });
                                }
                            });
                        }
                    });
                });

                // Start observing
                observer.observe(battleLog, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });

                console.log('✓ Battle log observer active');
            }
        }, 1000);

        // Stop checking after 30 seconds
        setTimeout(() => clearInterval(checkBattleLog), 30000);
    }

    /**
     * Process a battle message
     */
    function processBattleMessage(message) {
        if (!battleParser || !predictor) return;

        const event = battleParser.parseLine(message);

        // Debug logging (can be disabled)
        if (event && event.type !== 'turn') {
            console.log('Battle event:', event);
        }
    }

    /**
     * Handle battle events
     */
    function handleBattleEvent(event) {
        if (!event || !event.isOpponent) return;

        switch (event.type) {
            case 'switch':
                handleSwitch(event);
                break;

            case 'move':
                handleMove(event);
                break;

            case 'ability':
                handleAbility(event);
                break;

            case 'item':
            case 'enditem':
                handleItem(event);
                break;

            case 'damage':
                handleDamage(event);
                break;

            case 'heal':
                handleHeal(event);
                break;
        }
    }

    /**
     * Handle opponent Pokemon switch
     */
    function handleSwitch(event) {
        console.log(`🔄 Opponent sent out ${event.species}`);

        // Create or get prediction
        let prediction = currentPredictions.get(event.species);

        if (!prediction) {
            prediction = predictor.createInitialPrediction(event.species);
            currentPredictions.set(event.species, prediction);
        }

        // Show prediction
        const topPredictions = predictor.getTopPredictions(prediction);
        predictionUI.showPrediction(event.species, prediction, topPredictions);
    }

    /**
     * Handle opponent move
     */
    function handleMove(event) {
        console.log(`⚔️ Opponent's ${event.pokemon?.species} used ${event.moveName}`);

        const species = event.pokemon?.species;
        if (!species) return;

        let prediction = currentPredictions.get(species);
        if (!prediction) {
            prediction = predictor.createInitialPrediction(species);
            currentPredictions.set(species, prediction);
        }

        // Update with move
        prediction = predictor.updateWithMove(prediction, event.moveName);
        currentPredictions.set(species, prediction);

        // Update UI
        const topPredictions = predictor.getTopPredictions(prediction);
        predictionUI.update(species, prediction, topPredictions);
    }

    /**
     * Handle ability reveal
     */
    function handleAbility(event) {
        console.log(`💫 ${event.pokemon?.species} ability: ${event.abilityName}`);

        const species = event.pokemon?.species;
        if (!species) return;

        let prediction = currentPredictions.get(species);
        if (!prediction) return;

        // Update with ability
        prediction = predictor.updateWithAbility(prediction, event.abilityName);
        currentPredictions.set(species, prediction);

        // Update UI
        const topPredictions = predictor.getTopPredictions(prediction);
        predictionUI.update(species, prediction, topPredictions);
    }

    /**
     * Handle item reveal
     */
    function handleItem(event) {
        console.log(`📦 ${event.pokemon?.species} item: ${event.itemName}`);

        const species = event.pokemon?.species;
        if (!species) return;

        let prediction = currentPredictions.get(species);
        if (!prediction) return;

        // Update with item
        prediction = predictor.updateWithItem(prediction, event.itemName);
        currentPredictions.set(species, prediction);

        // Update UI
        const topPredictions = predictor.getTopPredictions(prediction);
        predictionUI.update(species, prediction, topPredictions);
    }

    /**
     * Handle damage
     */
    function handleDamage(event) {
        const species = event.pokemon?.species;
        if (!species) return;

        let prediction = currentPredictions.get(species);
        if (!prediction) return;

        // Check for hazard damage (Heavy-Duty Boots constraint)
        if (event.isHazardDamage) {
            console.log(`🪨 ${species} took hazard damage (no Heavy-Duty Boots)`);
            predictor.applyDamageConstraints(prediction, { tookHazardDamage: true });
            currentPredictions.set(species, prediction);

            // Update UI
            const topPredictions = predictor.getTopPredictions(prediction);
            predictionUI.update(species, prediction, topPredictions);
        }
    }

    /**
     * Handle healing
     */
    function handleHeal(event) {
        const species = event.pokemon?.species;
        if (!species) return;

        let prediction = currentPredictions.get(species);
        if (!prediction) return;

        // Check if item was explicitly confirmed from heal message
        if (event.confirmedItem) {
            console.log(`✓ ${species} item CONFIRMED: ${event.confirmedItem} (heal message)`);

            // Update with 100% confirmed item
            prediction = predictor.updateWithItem(prediction, event.confirmedItem);
            currentPredictions.set(species, prediction);

            // Update UI
            const topPredictions = predictor.getTopPredictions(prediction);
            predictionUI.update(species, prediction, topPredictions);
        }
        // Otherwise, just boost probability for passive healing
        else if (event.isPassiveHealing) {
            console.log(`💚 ${species} healed passively (likely Leftovers/Black Sludge)`);
            predictor.applyDamageConstraints(prediction, { healedOverTime: true });
            currentPredictions.set(species, prediction);

            // Update UI
            const topPredictions = predictor.getTopPredictions(prediction);
            predictionUI.update(species, prediction, topPredictions);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
