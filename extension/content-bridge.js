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

  function resourceUrl(target) {
    try {
      if (!target) return '';
      return target.currentSrc || target.src || target.href || '';
    } catch (_) {
      return '';
    }
  }

  function reportResource(event, blocked) {
    const url = resourceUrl(event.target);
    if (!url || !/^https?:\/\//.test(url)) return;
    chrome.runtime.sendMessage({ type: 'resource', url, status: blocked ? 'blocked' : 'allowed' }).catch(() => {});
  }

  document.addEventListener('error', (event) => reportResource(event, true), true);
  document.addEventListener('load', (event) => reportResource(event, false), true);

  function scanResources() {
    try {
      const loaded = new Set(performance.getEntriesByType('resource').map((entry) => entry.name));
      const nodes = document.querySelectorAll('script[src], link[href], img[src], iframe[src]');
      for (const node of nodes) {
        const url = resourceUrl(node);
        if (!url || !/^https?:\/\//.test(url)) continue;
        chrome.runtime.sendMessage({ type: 'resource', url, status: 'seen' }).catch(() => {});
      }
    } catch (_) {}
  }

  document.addEventListener('DOMContentLoaded', () => setTimeout(scanResources, 250), { once: true });
  window.addEventListener('load', () => setTimeout(scanResources, 250), { once: true });
})();
