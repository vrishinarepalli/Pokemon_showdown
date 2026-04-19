/**
 * Complete Battle Integration
 * Connects battle log parsing with set prediction, damage calculation, and next move prediction
 */

class BattleIntegration {
    constructor() {
        this.interceptor = null;
        this.parser = null;
        this.currentBattle = {
            id: null,
            turn: 0,
            player: 'p1',  // You are p1
            opponent: 'p2',
            opponentPokemon: {},  // Track opponent's team
            predictions: {}  // Pokemon -> prediction data
        };
    }

    /**
     * Initialize the battle integration
     */
    async init() {
        console.log('Initializing battle integration...');

        // Method 1: WebSocket Interception (RECOMMENDED - most accurate)
        this.useWebSocketMethod();

        // Method 2: DOM Observation (fallback)
        // this.useDOMMethod();
    }

    /**
     * Use WebSocket interception to capture battle events
     */
    useWebSocketMethod() {
        // Import the interceptor (make sure websocket_interceptor.js is loaded first)
        if (typeof WebSocketInterceptor === 'undefined') {
            console.error('WebSocketInterceptor not loaded');
            return;
        }

        this.interceptor = new WebSocketInterceptor();

        this.interceptor.start((message, isSent) => {
            if (isSent) return; // Ignore outgoing messages

            // Parse battle message
            const events = this.interceptor.parseBattleMessage(message);
            if (!events || events.length === 0) return;

            // Process each event
            events.forEach(event => {
                this.handleBattleEvent(event);
            });
        });

        console.log('✓ WebSocket interception active');
    }

    /**
     * Use DOM observation (alternative method)
     */
    useDOMMethod() {
        if (typeof BattleObserver === 'undefined') {
            console.error('BattleObserver not loaded');
            return;
        }

        const observer = new BattleObserver();
        observer.start((event) => {
            this.handleBattleEvent(event);
        });

        console.log('✓ DOM observation active');
    }

    /**
     * Handle a battle event
     * @param {Object} event - Battle event from parser
     */
    handleBattleEvent(event) {
        if (!event) return;

        console.log('Battle event:', event);

        switch (event.type) {
            case 'turn':
                this.handleTurn(event);
                break;

            case 'switch':
                this.handleSwitch(event);
                break;

            case 'move':
                this.handleMove(event);
                break;

            case 'ability':
                this.handleAbility(event);
                break;

            case 'item':
                this.handleItem(event);
                break;

            case 'damage':
                this.handleDamage(event);
                break;

            case 'heal':
                this.handleHeal(event);
                break;

            case 'weather':
                this.handleWeather(event);
                break;

            case 'terrain':
                this.handleTerrain(event);
                break;

            case 'faint':
                this.handleFaint(event);
                break;
        }
    }

    /**
     * Handle turn change
     */
    handleTurn(event) {
        this.currentBattle.turn = event.turn;
        console.log(`\n=== TURN ${event.turn} ===`);

        // Update UI: display turn number
        this.updateUI();
    }

    /**
     * Handle Pokemon switch
     */
    async handleSwitch(event) {
        // Ignore player's switches
        if (event.player === this.currentBattle.player) return;

        const pokemon = event.pokemon;
        console.log(`Opponent switched to: ${pokemon}`);

        // Create/update prediction for this Pokemon
        if (!this.currentBattle.predictions[pokemon]) {
            // First time seeing this Pokemon - create initial prediction
            const prediction = await this.createPrediction(pokemon);
            this.currentBattle.predictions[pokemon] = prediction;

            // Display prediction
            this.displayPrediction(pokemon, prediction);
        } else {
            // Already seen this Pokemon - update display
            this.displayPrediction(pokemon, this.currentBattle.predictions[pokemon]);
        }

        // Track current opponent Pokemon
        this.currentBattle.opponentPokemon.active = pokemon;
    }

    /**
     * Handle move usage
     */
    async handleMove(event) {
        // Only track opponent's moves
        if (event.player === this.currentBattle.player) return;

        const pokemon = event.pokemon;
        const move = event.move;

        console.log(`${pokemon} used ${move}!`);

        // Update prediction with revealed move
        if (this.currentBattle.predictions[pokemon]) {
            await this.updatePredictionWithMove(pokemon, move);

            // Display updated prediction
            this.displayPrediction(pokemon, this.currentBattle.predictions[pokemon]);
        }

        // Calculate damage this move can do to your Pokemon
        await this.calculateDamageForMove(pokemon, move);

        // Predict next move
        await this.predictNextMove(pokemon);
    }

    /**
     * Handle ability reveal
     */
    async handleAbility(event) {
        if (event.player === this.currentBattle.player) return;

        const pokemon = event.pokemon;
        const ability = event.ability;

        console.log(`${pokemon}'s ability: ${ability}`);

        // Update prediction
        if (this.currentBattle.predictions[pokemon]) {
            await this.updatePredictionWithAbility(pokemon, ability);
            this.displayPrediction(pokemon, this.currentBattle.predictions[pokemon]);
        }
    }

    /**
     * Handle item reveal
     */
    async handleItem(event) {
        if (event.player === this.currentBattle.player) return;

        const pokemon = event.pokemon;
        const item = event.item;

        console.log(`${pokemon}'s item: ${item}`);

        // Update prediction
        if (this.currentBattle.predictions[pokemon]) {
            await this.updatePredictionWithItem(pokemon, item);
            this.displayPrediction(pokemon, this.currentBattle.predictions[pokemon]);
        }
    }

    /**
     * Handle damage event
     */
    handleDamage(event) {
        // Can use damage to reverse-engineer stats/items
        // TODO: Implement reverse damage calculation
    }

    /**
     * Handle heal event
     */
    handleHeal(event) {
        if (event.player === this.currentBattle.player) return;

        // Check heal source for item reveals
        if (event.source && event.source.includes('Leftovers')) {
            console.log('Leftovers confirmed via heal!');
            // Update prediction
        }
    }

    /**
     * Handle weather change
     */
    handleWeather(event) {
        this.currentBattle.weather = event.weather;
        console.log(`Weather: ${event.weather}`);
    }

    /**
     * Handle terrain change
     */
    handleTerrain(event) {
        this.currentBattle.terrain = event.terrain;
        console.log(`Terrain: ${event.terrain}`);
    }

    /**
     * Handle Pokemon faint
     */
    handleFaint(event) {
        console.log(`${event.pokemon} fainted!`);
    }

    /**
     * Create initial prediction for Pokemon
     * @param {string} pokemon - Pokemon name
     * @returns {Object} - Prediction data
     */
    async createPrediction(pokemon) {
        // Call Python backend or use JS implementation
        // For now, return mock data
        return {
            pokemon: pokemon,
            confidence: 0.65,
            abilities: [
                { name: 'Protosynthesis', prob: 1.0 }
            ],
            items: [
                { name: 'Booster Energy', prob: 0.40 },
                { name: 'Choice Specs', prob: 0.15 },
                { name: 'Leftovers', prob: 0.14 }
            ],
            moves: [
                { name: 'Thunderbolt', prob: 0.71 },
                { name: 'Dragon Pulse', prob: 0.62 },
                { name: 'Thunderclap', prob: 0.96 },
                { name: 'Calm Mind', prob: 0.52 }
            ],
            revealedMoves: []
        };
    }

    /**
     * Update prediction with revealed move
     */
    async updatePredictionWithMove(pokemon, move) {
        const prediction = this.currentBattle.predictions[pokemon];
        if (!prediction) return;

        // Add to revealed moves
        if (!prediction.revealedMoves.includes(move)) {
            prediction.revealedMoves.push(move);
        }

        // Update probabilities (call backend)
        // prediction = await backend.updateWithMove(pokemon, move);

        console.log(`Updated prediction for ${pokemon}`);
    }

    /**
     * Update prediction with revealed ability
     */
    async updatePredictionWithAbility(pokemon, ability) {
        const prediction = this.currentBattle.predictions[pokemon];
        if (!prediction) return;

        prediction.revealedAbility = ability;
        prediction.abilities = [{ name: ability, prob: 1.0 }];

        console.log(`Confirmed ability: ${ability}`);
    }

    /**
     * Update prediction with revealed item
     */
    async updatePredictionWithItem(pokemon, item) {
        const prediction = this.currentBattle.predictions[pokemon];
        if (!prediction) return;

        prediction.revealedItem = item;
        prediction.items = [{ name: item, prob: 1.0 }];

        console.log(`Confirmed item: ${item}`);
    }

    /**
     * Calculate damage for a move
     */
    async calculateDamageForMove(attackerPokemon, move) {
        // Get your active Pokemon
        const yourPokemon = 'Great Tusk'; // TODO: Track dynamically

        console.log(`Calculating ${move} damage from ${attackerPokemon} to ${yourPokemon}...`);

        // Call damage calculator
        // const damage = await backend.calculateDamage(attackerPokemon, yourPokemon, move);
        // console.log(`Damage: ${damage.min}-${damage.max} (${damage.minPercent}%-${damage.maxPercent}%)`);
    }

    /**
     * Predict opponent's next move
     */
    async predictNextMove(pokemon) {
        console.log(`Predicting ${pokemon}'s next move...`);

        // Call next move predictor
        // const predictions = await backend.predictNextMove(pokemon, gameState);
        // console.log('Most likely moves:');
        // predictions.slice(0, 3).forEach(p => {
        //     console.log(`  ${p.move}: ${p.probability*100}% (${p.threat})`);
        // });
    }

    /**
     * Display prediction in UI
     */
    displayPrediction(pokemon, prediction) {
        console.log(`\n=== PREDICTION: ${pokemon} ===`);
        console.log(`Confidence: ${(prediction.confidence * 100).toFixed(0)}%`);

        if (prediction.revealedAbility) {
            console.log(`Ability: ${prediction.revealedAbility} (confirmed)`);
        } else {
            console.log('Top Abilities:');
            prediction.abilities.slice(0, 3).forEach(a => {
                console.log(`  • ${a.name}: ${(a.prob * 100).toFixed(0)}%`);
            });
        }

        if (prediction.revealedItem) {
            console.log(`Item: ${prediction.revealedItem} (confirmed)`);
        } else {
            console.log('Top Items:');
            prediction.items.slice(0, 3).forEach(i => {
                console.log(`  • ${i.name}: ${(i.prob * 100).toFixed(0)}%`);
            });
        }

        console.log('Revealed Moves:', prediction.revealedMoves.join(', ') || 'None');

        console.log('Top Unrevealed Moves:');
        prediction.moves
            .filter(m => !prediction.revealedMoves.includes(m.name))
            .slice(0, 3)
            .forEach(m => {
                console.log(`  • ${m.name}: ${(m.prob * 100).toFixed(0)}%`);
            });

        console.log('===========================\n');
    }

    /**
     * Update UI overlay
     */
    updateUI() {
        // TODO: Update your Chrome extension UI overlay
        // Show predictions, damage calcs, etc.
    }
}

// Initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        const integration = new BattleIntegration();
        integration.init();
    });
} else {
    const integration = new BattleIntegration();
    integration.init();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BattleIntegration;
}
