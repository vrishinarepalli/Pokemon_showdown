/**
 * UI Overlay for Pokemon Showdown
 * Displays set predictions
 */

class PredictionUI {
    constructor() {
        this.overlayElement = null;
        this.currentPrediction = null;
    }

    /**
     * Initialize the overlay UI
     */
    init() {
        this.createOverlay();
        this.injectStyles();
    }

    /**
     * Create overlay element
     */
    createOverlay() {
        // Create main overlay container
        this.overlayElement = document.createElement('div');
        this.overlayElement.id = 'ps-set-predictor-overlay';
        this.overlayElement.className = 'ps-predictor-hidden';

        // Add to page
        document.body.appendChild(this.overlayElement);

        console.log('✓ Set Predictor overlay injected');
    }

    /**
     * Show prediction for a Pokemon
     */
    showPrediction(pokemon, prediction, topPredictions) {
        this.currentPrediction = { pokemon, prediction, topPredictions };

        const confidence = Math.round(prediction.confidence * 100);

        // Build HTML
        const html = `
            <div class="ps-predictor-header">
                <div class="ps-predictor-title">
                    <span class="ps-predictor-pokemon-name">${pokemon}</span>
                    <span class="ps-predictor-confidence">${confidence}% confident</span>
                </div>
                <button class="ps-predictor-close" id="ps-predictor-close">×</button>
            </div>

            <div class="ps-predictor-body">
                ${this.renderAbility(topPredictions)}
                ${this.renderItem(topPredictions, prediction)}
                ${this.renderMoves(topPredictions)}
            </div>
        `;

        this.overlayElement.innerHTML = html;
        this.overlayElement.classList.remove('ps-predictor-hidden');

        // Add event listeners
        document.getElementById('ps-predictor-close').addEventListener('click', () => {
            this.hide();
        });
    }

    /**
     * Render ability section
     */
    renderAbility(topPredictions) {
        if (!topPredictions.abilities || topPredictions.abilities.length === 0) {
            return '';
        }

        const [topAbility, prob] = topPredictions.abilities[0];
        const isConfirmed = prob === 1.0;

        const abilityHtml = topPredictions.abilities.slice(0, 3).map(([ability, prob]) => {
            const percentage = Math.round(prob * 100);
            const icon = prob === 1.0 ? '✓' : (prob > 0.5 ? '●' : '○');
            return `
                <div class="ps-predictor-item ${prob === 1.0 ? 'confirmed' : ''}">
                    <span class="ps-predictor-icon">${icon}</span>
                    <span class="ps-predictor-name">${ability}</span>
                    <span class="ps-predictor-prob">${percentage}%</span>
                </div>
            `;
        }).join('');

        return `
            <div class="ps-predictor-section">
                <div class="ps-predictor-section-title">
                    Ability ${isConfirmed ? '(Confirmed)' : ''}
                </div>
                ${abilityHtml}
            </div>
        `;
    }

    /**
     * Render item section
     */
    renderItem(topPredictions, prediction) {
        if (!topPredictions.items || topPredictions.items.length === 0) {
            return '';
        }

        const [topItem, prob] = topPredictions.items[0];
        const isConfirmed = prob === 1.0;

        const ruledOut = Array.from(prediction.impossibleItems);

        const itemHtml = topPredictions.items.slice(0, 3).map(([item, prob]) => {
            const percentage = Math.round(prob * 100);
            const icon = prob === 1.0 ? '✓' : (prob > 0.5 ? '●' : '○');
            return `
                <div class="ps-predictor-item ${prob === 1.0 ? 'confirmed' : ''}">
                    <span class="ps-predictor-icon">${icon}</span>
                    <span class="ps-predictor-name">${item}</span>
                    <span class="ps-predictor-prob">${percentage}%</span>
                </div>
            `;
        }).join('');

        const ruledOutHtml = ruledOut.length > 0 ? `
            <div class="ps-predictor-ruled-out">
                <span class="ps-predictor-ruled-out-label">Ruled out:</span>
                ${ruledOut.map(item => `<span class="ps-predictor-ruled-out-item">${item}</span>`).join(', ')}
            </div>
        ` : '';

        return `
            <div class="ps-predictor-section">
                <div class="ps-predictor-section-title">
                    Item ${isConfirmed ? '(Confirmed)' : ''}
                </div>
                ${itemHtml}
                ${ruledOutHtml}
            </div>
        `;
    }

    /**
     * Render moves section
     */
    renderMoves(topPredictions) {
        const revealedHtml = topPredictions.revealedMoves.length > 0 ? `
            <div class="ps-predictor-subsection">
                <div class="ps-predictor-subsection-title">Known Moves</div>
                ${topPredictions.revealedMoves.map(move => `
                    <div class="ps-predictor-item confirmed">
                        <span class="ps-predictor-icon">✓</span>
                        <span class="ps-predictor-name">${move}</span>
                    </div>
                `).join('')}
            </div>
        ` : '';

        const remainingSlots = 4 - topPredictions.revealedMoves.length;
        const predictedHtml = topPredictions.moves.length > 0 && remainingSlots > 0 ? `
            <div class="ps-predictor-subsection">
                <div class="ps-predictor-subsection-title">
                    Predicted Moves (${remainingSlots} slot${remainingSlots !== 1 ? 's' : ''})
                </div>
                ${topPredictions.moves.slice(0, 5).map(([move, prob]) => {
                    const percentage = Math.round(prob * 100);
                    const icon = prob > 0.5 ? '●' : '○';
                    return `
                        <div class="ps-predictor-item">
                            <span class="ps-predictor-icon">${icon}</span>
                            <span class="ps-predictor-name">${move}</span>
                            <span class="ps-predictor-prob">${percentage}%</span>
                        </div>
                    `;
                }).join('')}
            </div>
        ` : '';

        return `
            <div class="ps-predictor-section">
                <div class="ps-predictor-section-title">Moves</div>
                ${revealedHtml}
                ${predictedHtml}
            </div>
        `;
    }

    /**
     * Update existing prediction
     */
    update(pokemon, prediction, topPredictions) {
        this.showPrediction(pokemon, prediction, topPredictions);
    }

    /**
     * Hide overlay
     */
    hide() {
        if (this.overlayElement) {
            this.overlayElement.classList.add('ps-predictor-hidden');
        }
    }

    /**
     * Show overlay
     */
    show() {
        if (this.overlayElement) {
            this.overlayElement.classList.remove('ps-predictor-hidden');
        }
    }

    /**
     * Inject CSS styles
     */
    injectStyles() {
        // Styles are loaded from overlay.css
    }
}
