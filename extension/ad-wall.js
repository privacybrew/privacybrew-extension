(() => {
  'use strict';
  if (window.top !== window) return;
  const WORDS = /ad ?block|adblocker|disable|whitelist|allowlist|turn off|werbeblocker|bloqueur|bloqueador|blocco/i;
  function visible(el) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > innerWidth * 0.4 && r.height > innerHeight * 0.35 && s.display !== 'none' && s.visibility !== 'hidden';
  }
  function scan() {
    try {
      const nodes = [...document.querySelectorAll('body *')].slice(0, 700);
      let hidden = false;
      for (const el of nodes) {
        const text = (el.innerText || '').slice(0, 800);
        if (!WORDS.test(text)) continue;
        const s = getComputedStyle(el);
        const z = Number.parseInt(s.zIndex || '0', 10) || 0;
        const fixed = s.position === 'fixed' || s.position === 'absolute';
        if (visible(el) && (fixed || z > 100)) {
          chrome.runtime.sendMessage({ type: 'adWall', status: 'detected' }).catch(() => {});
          return;
        }
        if (s.display === 'none' && (document.documentElement.style.overflow === 'hidden' || document.body.style.overflow === 'hidden')) hidden = true;
      }
      if (hidden) {
        document.documentElement.style.overflow = '';
        document.body.style.overflow = '';
        chrome.runtime.sendMessage({ type: 'adWall', status: 'hidden' }).catch(() => {});
      }
    } catch (_) {}
  }
  setTimeout(scan, 3000);
  setTimeout(scan, 8000);
})();
