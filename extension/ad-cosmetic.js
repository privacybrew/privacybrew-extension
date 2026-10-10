(() => {
  'use strict';
  const STYLE_ID = 'privacybrew-ad-cosmetic';
  const LINK_ID = 'privacybrew-ad-generic';
  function addStyle(id, css) {
    try {
      if (!css || document.getElementById(id)) return;
      const style = document.createElement('style');
      style.id = id;
      style.textContent = css;
      (document.documentElement || document.head || document).appendChild(style);
    } catch (_) {}
  }
  chrome.runtime.sendMessage({ type: 'getAdCss', host: location.hostname }).then((response) => {
    try {
      const start = performance.now();
      if (!response || (!response.css && !response.genericUrl)) return;
      if (response.genericUrl && !document.getElementById(LINK_ID)) {
        const link = document.createElement('link');
        link.id = LINK_ID;
        link.rel = 'stylesheet';
        link.href = response.genericUrl;
        (document.documentElement || document.head || document).appendChild(link);
      }
      addStyle(STYLE_ID, response.css || '');
      chrome.runtime.sendMessage({ type: 'adCosmeticApplied', durationMs: Math.round(performance.now() - start) }).catch(() => {});
    } catch (_) {}
  }).catch(() => {});
})();
