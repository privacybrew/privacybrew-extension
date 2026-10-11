(() => {
  'use strict';
  const ACCEPT = /\b(accept|allow all|agree|got it|ok)\b/i;
  const REJECT = /\b(reject|decline|deny|necessary only|essential only|manage|settings|preferences|customize)\b/i;
  function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 120 && rect.height > 40 && style.display !== 'none' && style.visibility !== 'hidden';
  }
  function maybeCookieText(text) {
    return /cookie|consent|privacy/i.test(text || '');
  }
  async function enabled() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'getCookiePopupEnabled' });
      return response && response.enabled;
    } catch (_) {
      return false;
    }
  }
  async function scan() {
    if (!(await enabled())) return;
    const nodes = [...document.querySelectorAll('[role="dialog"], dialog, div, section')].slice(0, 300);
    for (const node of nodes) {
      if (!visible(node)) continue;
      const text = (node.innerText || '').slice(0, 1000);
      if (!maybeCookieText(text)) continue;
      const buttons = [...node.querySelectorAll('button, a, input[type="button"], input[type="submit"]')];
      const labels = buttons.map((button) => button.innerText || button.value || button.getAttribute('aria-label') || '').join(' ');
      if (ACCEPT.test(labels) && !REJECT.test(labels)) {
        node.style.setProperty('display', 'none', 'important');
        chrome.runtime.sendMessage({ type: 'cookiePopupFallbackHidden' }).catch(() => {});
        return;
      }
    }
  }
  setTimeout(scan, 1800);
})();
