(() => {
  'use strict';
  const EVENT_NAME = 'privacybrew:fingerprint';
  const allowed = new Set(['canvas', 'webgl', 'audio', 'fonts']);
  const loadedNodes = new WeakSet();
  const failedNodes = new WeakSet();
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

  function reportUrl(url, status) {
    if (!url || !/^https?:\/\//.test(url)) return;
    chrome.runtime.sendMessage({ type: 'resource', url, status }).catch(() => {});
  }

  function reportResource(event, blocked) {
    if (blocked) failedNodes.add(event.target);
    else loadedNodes.add(event.target);
    reportUrl(resourceUrl(event.target), blocked ? 'blocked' : 'allowed');
  }

  document.addEventListener('error', (event) => reportResource(event, true), true);
  document.addEventListener('load', (event) => reportResource(event, false), true);
  document.dispatchEvent(new CustomEvent('privacybrew:bridge-ready'));

  function scanResources() {
    try {
      const nodes = document.querySelectorAll('script[src], link[href]');
      for (const node of nodes) {
        const url = resourceUrl(node);
        if (!url || !/^https?:\/\//.test(url)) continue;
        if (failedNodes.has(node)) reportUrl(url, 'blocked');
        else if (loadedNodes.has(node)) reportUrl(url, 'allowed');
        else reportUrl(url, 'blocked');
      }
    } catch (_) {}
  }

  document.addEventListener('DOMContentLoaded', () => setTimeout(scanResources, 250), { once: true });
  window.addEventListener('load', () => setTimeout(scanResources, 250), { once: true });
})();
