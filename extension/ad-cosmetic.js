(() => {
  'use strict';
  const STYLE_ID = 'privacybrew-ad-cosmetic';
  const start = performance.now();
  function addStyle(css) {
    try {
      if (!css || document.getElementById(STYLE_ID)) return;
      const style = document.createElement('style');
      style.id = STYLE_ID;
      style.textContent = css;
      (document.documentElement || document.head || document).appendChild(style);
      chrome.runtime.sendMessage({ type: 'adCosmeticApplied', durationMs: Math.round(performance.now() - start) }).catch(() => {});
    } catch (_) {}
  }
  chrome.runtime.sendMessage({ type: 'getAdCss', host: location.hostname }).then((response) => {
    if (response && response.css) addStyle(response.css);
  }).catch(() => {});
})();
