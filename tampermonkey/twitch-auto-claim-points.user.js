// ==UserScript==
// @name         Twitch Auto Claim Channel Points
// @namespace    https://github.com/mag1xzj/mag1cz
// @version      1.0.0
// @description  Automatically clicks the "Claim Bonus" channel points button on Twitch as soon as it appears (points become claimable roughly every ~15 minutes while watching a stream).
// @author       you
// @match        https://www.twitch.tv/*
// @icon         https://www.twitch.tv/favicon.ico
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // How often we actively poll the page for a claim button, as a
    // fallback in case the MutationObserver below misses the DOM change.
    const POLL_INTERVAL_MS = 15 * 1000; // 15 seconds

    // Twitch changes its internal class names fairly often, so we try a
    // handful of known selectors first, then fall back to scanning every
    // button on the page for a "claim bonus" label/tooltip.
    const KNOWN_SELECTORS = [
        'button[data-test-selector="community-points-summary__claim-button"]',
        'button[aria-label="Claim Bonus"]',
        '.claimable-bonus__icon',
        '.community-points-summary-bonus-cta',
    ];

    function findClaimButton() {
        for (const selector of KNOWN_SELECTORS) {
            const el = document.querySelector(selector);
            if (el) {
                const btn = el.closest('button') || el;
                if (btn instanceof HTMLElement && !btn.disabled) return btn;
            }
        }

        // Fallback: scan all buttons for a label/tooltip that mentions
        // "claim bonus" (case-insensitive). Covers Twitch UI changes that
        // break the selectors above.
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            const label = (
                btn.getAttribute('aria-label') ||
                btn.getAttribute('title') ||
                btn.textContent ||
                ''
            ).trim().toLowerCase();
            if (label.includes('claim bonus') && !btn.disabled) {
                return btn;
            }
        }

        return null;
    }

    let lastClaimAt = 0;

    function tryClaim() {
        const btn = findClaimButton();
        if (!btn) return;

        // Simple debounce so a burst of mutation events doesn't double-click.
        const now = Date.now();
        if (now - lastClaimAt < 2000) return;
        lastClaimAt = now;

        btn.click();
        console.log(`[Twitch Auto Claim] Claimed channel points bonus at ${new Date().toLocaleTimeString()}`);
    }

    // React immediately whenever the button shows up in the DOM.
    const observer = new MutationObserver(() => tryClaim());
    observer.observe(document.documentElement, { childList: true, subtree: true });

    // Fallback polling loop.
    setInterval(tryClaim, POLL_INTERVAL_MS);

    // Try once shortly after the page/script loads too.
    setTimeout(tryClaim, 3000);
})();
