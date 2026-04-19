/**
 * WebSocket Interceptor for Pokemon Showdown
 * Intercepts WebSocket messages to get raw battle protocol
 *
 * This is the MOST ACCURATE method - gets exact protocol data
 */

class WebSocketInterceptor {
    constructor() {
        this.onMessage = null;
        this.originalWebSocket = window.WebSocket;
        this.activeConnections = [];
    }

    /**
     * Start intercepting WebSocket messages
     * @param {Function} callback - Called with (message, isSent)
     */
    start(callback) {
        this.onMessage = callback;

        // Override WebSocket constructor
        const self = this;

        window.WebSocket = function(...args) {
            const ws = new self.originalWebSocket(...args);

            console.log('✓ WebSocket connection intercepted:', args[0]);
            self.activeConnections.push(ws);

            // Intercept incoming messages
            const originalOnMessage = ws.onmessage;
            ws.onmessage = function(event) {
                // Call original handler
                if (originalOnMessage) {
                    originalOnMessage.call(this, event);
                }

                // Call our callback
                if (self.onMessage) {
                    self.onMessage(event.data, false);
                }
            };

            // Intercept outgoing messages
            const originalSend = ws.send;
            ws.send = function(data) {
                // Call original send
                originalSend.call(this, data);

                // Call our callback
                if (self.onMessage) {
                    self.onMessage(data, true);
                }
            };

            return ws;
        };

        // Copy static properties
        Object.setPrototypeOf(window.WebSocket, this.originalWebSocket);
        window.WebSocket.prototype = this.originalWebSocket.prototype;

        console.log('✓ WebSocket interceptor started');
    }

    /**
     * Stop intercepting (restore original WebSocket)
     */
    stop() {
        window.WebSocket = this.originalWebSocket;
        this.activeConnections = [];
        console.log('✓ WebSocket interceptor stopped');
    }

    /**
     * Parse battle message
     * Pokemon Showdown sends messages like:
     * >battle-gen9ou-123456789
     * |turn|5
     * |move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
     * |-damage|p1a: Great Tusk|65/100
     *
     * @param {string} message - Raw WebSocket message
     * @returns {Object|null} - Parsed battle data
     */
    parseBattleMessage(message) {
        // Skip non-battle messages
        if (!message.includes('|')) {
            return null;
        }

        const lines = message.split('\n');
        const events = [];

        for (const line of lines) {
            if (line.startsWith('|')) {
                events.push(this.parseBattleLine(line));
            }
        }

        return events.filter(e => e !== null);
    }

    /**
     * Parse a single battle protocol line
     * @param {string} line - Battle protocol line (starts with |)
     * @returns {Object|null} - Parsed event
     */
    parseBattleLine(line) {
        const parts = line.split('|').slice(1); // Remove empty first element
        if (parts.length === 0) return null;

        const command = parts[0];

        switch (command) {
            case 'switch':
            case 'drag':
                // |switch|p2a: Kingambit|Kingambit, L50, M|100/100
                return {
                    type: 'switch',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[2].split(',')[0].trim(),
                    hp: parts[3]
                };

            case 'move':
                // |move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
                return {
                    type: 'move',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim(),
                    move: parts[2].trim(),
                    target: parts[3] ? parts[3].trim() : null
                };

            case '-damage':
                // |-damage|p1a: Great Tusk|65/100
                return {
                    type: 'damage',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim(),
                    hp: parts[2]
                };

            case '-heal':
                // |-heal|p2a: Kingambit|25/100|[from] item: Leftovers
                return {
                    type: 'heal',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim(),
                    hp: parts[2],
                    source: parts[3] ? parts[3].replace('[from]', '').trim() : null
                };

            case '-ability':
                // |-ability|p2a: Raging Bolt|Protosynthesis
                return {
                    type: 'ability',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim(),
                    ability: parts[2].trim()
                };

            case '-item':
                // |-item|p2a: Kingambit|Leftovers
                return {
                    type: 'item',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim(),
                    item: parts[2].trim()
                };

            case 'turn':
                // |turn|5
                return {
                    type: 'turn',
                    turn: parseInt(parts[1])
                };

            case '-weather':
            case 'weather':
                // |-weather|SunnyDay
                return {
                    type: 'weather',
                    weather: parts[1].trim()
                };

            case '-fieldstart':
                // |-fieldstart|move: Electric Terrain
                if (parts[1].includes('Terrain')) {
                    return {
                        type: 'terrain',
                        terrain: parts[1].replace('move:', '').trim()
                    };
                }
                break;

            case 'faint':
                // |faint|p2a: Kingambit
                return {
                    type: 'faint',
                    player: parts[1].split(':')[0].trim(),
                    pokemon: parts[1].split(':')[1].trim()
                };

            default:
                return null;
        }

        return null;
    }
}

// Usage:
// const interceptor = new WebSocketInterceptor();
// interceptor.start((message, isSent) => {
//     if (!isSent) { // Only process incoming messages
//         const events = interceptor.parseBattleMessage(message);
//         if (events && events.length > 0) {
//             console.log('Battle events:', events);
//             // Send to your predictor
//         }
//     }
// });

// Export for use in content script
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketInterceptor;
}
