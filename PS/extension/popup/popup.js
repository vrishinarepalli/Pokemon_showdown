/**
 * Popup UI Logic
 */

// Load settings and stats
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadStats();
    setupEventListeners();
});

/**
 * Load settings from storage
 */
function loadSettings() {
    chrome.storage.local.get(['enabled', 'showConfidence'], (result) => {
        const enabled = result.enabled !== false; // Default true
        const showConfidence = result.showConfidence !== false; // Default true

        updateToggle('toggle-enabled', enabled);
        updateToggle('toggle-confidence', showConfidence);
    });
}

/**
 * Load statistics
 */
function loadStats() {
    chrome.storage.local.get(['battleHistory', 'totalPredictions'], (result) => {
        const battles = result.battleHistory ? result.battleHistory.length : 0;
        const predictions = result.totalPredictions || 0;

        document.getElementById('battles-count').textContent = battles;
        document.getElementById('predictions-count').textContent = predictions;
    });
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Enable toggle
    document.getElementById('toggle-enabled').addEventListener('click', (e) => {
        const toggle = e.currentTarget;
        const isActive = toggle.classList.contains('active');
        const newState = !isActive;

        updateToggle('toggle-enabled', newState);
        chrome.storage.local.set({ enabled: newState });
    });

    // Confidence toggle
    document.getElementById('toggle-confidence').addEventListener('click', (e) => {
        const toggle = e.currentTarget;
        const isActive = toggle.classList.contains('active');
        const newState = !isActive;

        updateToggle('toggle-confidence', newState);
        chrome.storage.local.set({ showConfidence: newState });
    });

    // Clear history button
    document.getElementById('clear-history').addEventListener('click', () => {
        if (confirm('Clear all battle history?')) {
            chrome.storage.local.set({
                battleHistory: [],
                totalPredictions: 0
            }, () => {
                loadStats();
                alert('Battle history cleared!');
            });
        }
    });
}

/**
 * Update toggle state
 */
function updateToggle(id, isActive) {
    const toggle = document.getElementById(id);
    if (isActive) {
        toggle.classList.add('active');
    } else {
        toggle.classList.remove('active');
    }
}
