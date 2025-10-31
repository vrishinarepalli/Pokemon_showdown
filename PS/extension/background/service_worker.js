/**
 * Background Service Worker
 * Handles extension lifecycle and data management
 */

console.log('Set Predictor service worker loaded');

// Listen for extension installation
chrome.runtime.onInstalled.addListener((details) => {
    if (details.reason === 'install') {
        console.log('Set Predictor installed!');

        // Set default settings
        chrome.storage.local.set({
            enabled: true,
            showConfidence: true,
            autoHide: false
        });
    } else if (details.reason === 'update') {
        console.log('Set Predictor updated to version', chrome.runtime.getManifest().version);
    }
});

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'getPrediction') {
        // Handle prediction requests
        sendResponse({ success: true });
    }

    if (message.type === 'saveBattleHistory') {
        // Save battle history to storage
        chrome.storage.local.get(['battleHistory'], (result) => {
            const history = result.battleHistory || [];
            history.push(message.battle);

            // Keep last 100 battles
            if (history.length > 100) {
                history.shift();
            }

            chrome.storage.local.set({ battleHistory: history });
        });
    }

    return true;
});
