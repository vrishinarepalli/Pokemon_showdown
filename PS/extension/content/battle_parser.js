/**
 * Battle Parser for Pokemon Showdown
 * Parses battle log messages and extracts game state
 */

class BattleParser {
    constructor() {
        this.battleState = {
            turn: 0,
            playerSide: null, // 'p1' or 'p2'
            opponentSide: null,
            opponentTeam: new Map(), // pokemon_id -> PokemonState
            playerTeam: new Map()
        };

        this.observers = [];
    }

    /**
     * Subscribe to battle events
     */
    subscribe(callback) {
        this.observers.push(callback);
    }

    /**
     * Notify all observers of an event
     */
    notify(event) {
        this.observers.forEach(callback => callback(event));
    }

    /**
     * Parse a battle message line
     * Format: |command|arg1|arg2|...
     */
    parseLine(line) {
        if (!line || !line.startsWith('|')) return null;

        const parts = line.split('|').slice(1); // Remove leading empty string
        const command = parts[0];

        switch (command) {
            case 'player':
                return this.parsePlayer(parts);
            case 'switch':
            case 'drag':
                return this.parseSwitch(parts);
            case 'move':
                return this.parseMove(parts);
            case 'turn':
                return this.parseTurn(parts);
            case '-damage':
                return this.parseDamage(parts);
            case '-heal':
                return this.parseHeal(parts);
            case '-ability':
                return this.parseAbility(parts);
            case '-item':
                return this.parseItem(parts);
            case '-enditem':
                return this.parseEndItem(parts);
            case 'faint':
                return this.parseFaint(parts);
            default:
                return null;
        }
    }

    /**
     * Parse player assignment
     * |player|p1|Username|avatar
     */
    parsePlayer(parts) {
        const [_, side, username] = parts;

        if (!this.battleState.playerSide) {
            // Assume first player is us (this might need adjustment)
            this.battleState.playerSide = side;
            this.battleState.opponentSide = side === 'p1' ? 'p2' : 'p1';
        }

        return { type: 'player', side, username };
    }

    /**
     * Parse Pokemon switch
     * |switch|p2a: Kingambit|Kingambit, L75, M|100/100
     */
    parseSwitch(parts) {
        const [_, pokemonId, details, condition] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const { species, level, gender } = this.parseDetails(details);
        const { hp, maxHp, status } = this.parseCondition(condition);

        // Get or create Pokemon state
        const pokemon = this.getOrCreatePokemon(side, species, nickname);
        pokemon.active = true;
        pokemon.hp = hp;
        pokemon.maxHp = maxHp;

        const event = {
            type: 'switch',
            side,
            pokemon,
            species,
            nickname,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse move usage
     * |move|p2a: Kingambit|Sucker Punch|p1a: Great Tusk
     */
    parseMove(parts) {
        const [_, pokemonId, moveName, targetId] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const pokemon = this.findPokemon(side, nickname);

        if (pokemon) {
            pokemon.revealedMoves.add(moveName);
        }

        const event = {
            type: 'move',
            side,
            pokemon,
            moveName,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse turn number
     * |turn|5
     */
    parseTurn(parts) {
        const [_, turnNum] = parts;
        this.battleState.turn = parseInt(turnNum);

        const event = {
            type: 'turn',
            turn: this.battleState.turn
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse damage
     * |-damage|p2a: Kingambit|65/100
     */
    parseDamage(parts) {
        const [_, pokemonId, condition, source] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const { hp, maxHp, status } = this.parseCondition(condition);

        const pokemon = this.findPokemon(side, nickname);
        if (pokemon) {
            pokemon.hp = hp;
            pokemon.maxHp = maxHp;
        }

        // Check if damage is from entry hazards
        const isHazardDamage = source && (
            source.includes('[from] Stealth Rock') ||
            source.includes('[from] Spikes') ||
            source.includes('[from] spikes')
        );

        const event = {
            type: 'damage',
            side,
            pokemon,
            hp,
            maxHp,
            isHazardDamage,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse healing
     * |-heal|p2a: Kingambit|70/100|[from] item: Leftovers
     */
    parseHeal(parts) {
        const [_, pokemonId, condition, source] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const { hp, maxHp } = this.parseCondition(condition);

        const pokemon = this.findPokemon(side, nickname);
        if (pokemon) {
            pokemon.hp = hp;
            pokemon.maxHp = maxHp;
        }

        // Extract item name from source if explicitly mentioned
        // Format: "[from] item: Leftovers" or "[from] Leftovers"
        let confirmedItem = null;
        if (source) {
            // Match "item: ItemName" or just "ItemName" after [from]
            const itemMatch = source.match(/item:\s*(.+)/i) || source.match(/\[from\]\s*(.+)/i);
            if (itemMatch) {
                const itemName = itemMatch[1].trim();
                // Check if it's a healing item
                if (itemName === 'Leftovers' || itemName === 'Black Sludge') {
                    confirmedItem = itemName;
                    if (pokemon) {
                        pokemon.revealedItem = itemName;
                    }
                }
            }
        }

        // Check healing source for probability boost (if not confirmed)
        const isPassiveHealing = source && (
            source.includes('Leftovers') ||
            source.includes('Black Sludge')
        );

        const event = {
            type: 'heal',
            side,
            pokemon,
            hp,
            maxHp,
            isPassiveHealing,
            confirmedItem,  // NEW: Explicit item confirmation
            source,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse ability reveal
     * |-ability|p2a: Kingambit|Supreme Overlord
     */
    parseAbility(parts) {
        const [_, pokemonId, abilityName] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const pokemon = this.findPokemon(side, nickname);

        if (pokemon) {
            pokemon.revealedAbility = abilityName;
        }

        const event = {
            type: 'ability',
            side,
            pokemon,
            abilityName,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse item reveal
     * |-item|p2a: Kingambit|Leftovers
     */
    parseItem(parts) {
        const [_, pokemonId, itemName] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const pokemon = this.findPokemon(side, nickname);

        if (pokemon) {
            pokemon.revealedItem = itemName;
        }

        const event = {
            type: 'item',
            side,
            pokemon,
            itemName,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse item end (consumed or knocked off)
     * |-enditem|p2a: Kingambit|Leftovers|[from] move: Knock Off
     */
    parseEndItem(parts) {
        const [_, pokemonId, itemName, source] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const pokemon = this.findPokemon(side, nickname);

        if (pokemon && !pokemon.revealedItem) {
            pokemon.revealedItem = itemName;
        }

        const event = {
            type: 'enditem',
            side,
            pokemon,
            itemName,
            source,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Parse Pokemon fainting
     * |faint|p2a: Kingambit
     */
    parseFaint(parts) {
        const [_, pokemonId] = parts;

        const { side, position, nickname } = this.parsePokemonId(pokemonId);
        const pokemon = this.findPokemon(side, nickname);

        if (pokemon) {
            pokemon.active = false;
            pokemon.fainted = true;
        }

        const event = {
            type: 'faint',
            side,
            pokemon,
            isOpponent: side === this.battleState.opponentSide
        };

        this.notify(event);
        return event;
    }

    /**
     * Helper: Parse Pokemon ID
     * Format: "p2a: Kingambit" or "p1a: Great Tusk"
     */
    parsePokemonId(pokemonId) {
        const match = pokemonId.match(/([p][12])([a-z]):\s*(.+)/);
        if (!match) return { side: null, position: null, nickname: pokemonId };

        return {
            side: match[1],        // p1 or p2
            position: match[2],    // a, b, c, etc.
            nickname: match[3].trim()
        };
    }

    /**
     * Helper: Parse Pokemon details
     * Format: "Kingambit, L75, M" or "Great Tusk"
     */
    parseDetails(details) {
        const parts = details.split(',').map(p => p.trim());
        const species = parts[0];

        let level = 100;
        let gender = null;

        for (const part of parts.slice(1)) {
            if (part.startsWith('L')) {
                level = parseInt(part.substring(1));
            } else if (part === 'M' || part === 'F') {
                gender = part;
            }
        }

        return { species, level, gender };
    }

    /**
     * Helper: Parse condition (HP/status)
     * Format: "100/100" or "50/100 brn"
     */
    parseCondition(condition) {
        if (!condition) return { hp: 0, maxHp: 0, status: null };

        const parts = condition.split(' ');
        const hpPart = parts[0];
        const status = parts[1] || null;

        if (hpPart === '0 fnt') {
            return { hp: 0, maxHp: 0, status: 'fnt' };
        }

        const [hp, maxHp] = hpPart.split('/').map(x => parseInt(x));

        return { hp: hp || 0, maxHp: maxHp || 0, status };
    }

    /**
     * Get or create Pokemon state
     */
    getOrCreatePokemon(side, species, nickname) {
        const team = side === this.battleState.playerSide ?
            this.battleState.playerTeam : this.battleState.opponentTeam;

        const key = `${species}-${nickname}`;

        if (!team.has(key)) {
            team.set(key, {
                species,
                nickname,
                active: false,
                fainted: false,
                hp: 0,
                maxHp: 0,
                revealedMoves: new Set(),
                revealedAbility: null,
                revealedItem: null,
                revealedTera: null
            });
        }

        return team.get(key);
    }

    /**
     * Find Pokemon by nickname
     */
    findPokemon(side, nickname) {
        const team = side === this.battleState.playerSide ?
            this.battleState.playerTeam : this.battleState.opponentTeam;

        for (const [key, pokemon] of team.entries()) {
            if (pokemon.nickname === nickname) {
                return pokemon;
            }
        }

        return null;
    }

    /**
     * Get current opponent's active Pokemon
     */
    getOpponentActivePokemon() {
        for (const [key, pokemon] of this.battleState.opponentTeam.entries()) {
            if (pokemon.active && !pokemon.fainted) {
                return pokemon;
            }
        }
        return null;
    }

    /**
     * Reset battle state
     */
    reset() {
        this.battleState = {
            turn: 0,
            playerSide: null,
            opponentSide: null,
            opponentTeam: new Map(),
            playerTeam: new Map()
        };
    }
}
