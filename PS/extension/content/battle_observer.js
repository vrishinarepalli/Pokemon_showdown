/**
 * Battle Observer for Pokemon Showdown
 * Watches the battle log and extracts events WITHOUT webscraping
 */

class BattleObserver {
    constructor() {
        this.battleLogContainer = null;
        this.observer = null;
        this.onBattleEvent = null; // Callback for battle events
    }

    /**
     * Start observing battle logs
     * @param {Function} callback - Called when new battle event occurs
     */
    start(callback) {
        this.onBattleEvent = callback;

        // Find battle log container
        // Pokemon Showdown uses: <div class="battle-log">
        this.battleLogContainer = document.querySelector('.battle-log');

        if (!this.battleLogContainer) {
            console.error('Battle log container not found');
            return false;
        }

        console.log('✓ Battle log container found');

        // Create a MutationObserver to watch for new log entries
        this.observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    // New battle log entries added
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            this.processBattleLogEntry(node);
                        }
                    });
                }
            });
        });

        // Start observing
        this.observer.observe(this.battleLogContainer, {
            childList: true,
            subtree: true
        });

        console.log('✓ Battle observer started');
        return true;
    }

    /**
     * Stop observing
     */
    stop() {
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
        }
    }

    /**
     * Process a single battle log entry
     * @param {Element} element - The log entry element
     */
    processBattleLogEntry(element) {
        // Extract text content
        const text = element.textContent || element.innerText;

        // Parse the log entry
        const event = this.parseBattleLogText(text);

        if (event && this.onBattleEvent) {
            this.onBattleEvent(event);
        }
    }

    /**
     * Parse battle log text to extract event
     * @param {string} text - Log text
     * @returns {Object|null} - Parsed event
     */
    parseBattleLogText(text) {
        // Example log texts:
        // "Kingambit used Sucker Punch!"
        // "Great Tusk lost 35% of its health!"
        // "Raging Bolt's Protosynthesis raised its Special Attack!"
        // "Go! Kingambit!"

        // Switch in
        if (text.includes('Go!') || text.includes('sent out')) {
            const match = text.match(/(?:Go!|sent out)\s+([^!]+)/);
            if (match) {
                return {
                    type: 'switch',
                    pokemon: match[1].trim()
                };
            }
        }

        // Move used
        if (text.includes('used')) {
            const match = text.match(/(.+?)\s+used\s+([^!]+)/);
            if (match) {
                return {
                    type: 'move',
                    pokemon: match[1].trim(),
                    move: match[2].trim()
                };
            }
        }

        // Ability activation
        if (text.includes("'s ") && (text.includes('raised') || text.includes('lowered') ||
            text.includes('ability') || text.includes('activated'))) {
            const match = text.match(/(.+?)'s\s+([^!\s]+)/);
            if (match) {
                return {
                    type: 'ability',
                    pokemon: match[1].trim(),
                    ability: match[2].trim()
                };
            }
        }

        // Damage
        if (text.includes('lost') && text.includes('health')) {
            const match = text.match(/(.+?)\s+lost\s+(\d+)%/);
            if (match) {
                return {
                    type: 'damage',
                    pokemon: match[1].trim(),
                    percent: parseInt(match[2])
                };
            }
        }

        // Item reveal (Leftovers, etc.)
        if (text.includes('restored') || text.includes('Leftovers') ||
            text.includes('Black Sludge')) {
            const match = text.match(/(.+?)\s+restored.+?using its\s+([^!]+)/);
            if (match) {
                return {
                    type: 'item',
                    pokemon: match[1].trim(),
                    item: match[2].trim()
                };
            }
        }

        return null;
    }
}

// Usage:
// const observer = new BattleObserver();
// observer.start((event) => {
//     console.log('Battle event:', event);
//     // Send to your predictor
// });
