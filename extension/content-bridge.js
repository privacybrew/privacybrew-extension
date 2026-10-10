(() => {
  'use strict';
  const EVENT_NAME = 'privacybrew:fingerprint';
  const allowed = new Set(['canvas', 'webgl', 'audio', 'fonts']);
  document.addEventListener(EVENT_NAME, (event) => {
    const detail = event && event.detail ? event.detail : {};
    if (!allowed.has(detail.technique)) return;
    chrome.runtime.sendMessage({
      type: 'fingerprint',
      technique: detail.technique,
      origin: String(detail.origin || 'Unknown script').slice(0, 200)
    }).catch(() => {});
  }, true);
})();
