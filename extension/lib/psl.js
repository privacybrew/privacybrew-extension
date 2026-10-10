(function (global) {
  'use strict';
  const ipV4 = /^(?:\d{1,3}\.){3}\d{1,3}$/;
  const ipV6 = /^\[[0-9a-f:]+\]$|^[0-9a-f:]*:[0-9a-f:]+$/i;

  function cleanHost(input) {
    if (!input) return '';
    let host = String(input).trim().toLowerCase();
    try {
      if (/^[a-z][a-z0-9+.-]*:/i.test(host)) host = new URL(host).hostname;
    } catch (_) {}
    host = host.replace(/^\[(.*)\]$/, '$1').replace(/\.$/, '');
    return host;
  }

  function isIp(host) {
    return ipV4.test(host) || ipV6.test(host);
  }

  function initPsl(data) {
    const normal = new Set(data.normal || []);
    const wildcard = new Set(data.wildcard || []);
    const exception = new Set(data.exception || []);

    function publicSuffix(hostInput) {
      const host = cleanHost(hostInput);
      if (!host || host === 'localhost' || isIp(host)) return host;
      const labels = host.split('.');
      let match = '';
      let matchLabels = 1;
      for (let i = 0; i < labels.length; i += 1) {
        const candidate = labels.slice(i).join('.');
        if (exception.has(candidate)) {
          return labels.slice(i + 1).join('.');
        }
        if (normal.has(candidate) && labels.length - i > matchLabels) {
          match = candidate;
          matchLabels = labels.length - i;
        }
        const rest = labels.slice(i + 1).join('.');
        if (rest && wildcard.has(rest) && labels.length - i > matchLabels) {
          match = candidate;
          matchLabels = labels.length - i;
        }
      }
      return match || labels[labels.length - 1];
    }

    function registrableDomain(hostInput) {
      const host = cleanHost(hostInput);
      if (!host || host === 'localhost' || isIp(host)) return host;
      const suffix = publicSuffix(host);
      if (!suffix || suffix === host) return host;
      const h = host.split('.');
      const s = suffix.split('.');
      if (h.length <= s.length) return host;
      return h.slice(h.length - s.length - 1).join('.');
    }

    return { cleanHost, isIp, publicSuffix, registrableDomain };
  }

  global.PB = global.PB || {};
  global.PB.PSL = { initPsl, cleanHost, isIp };
})(typeof globalThis !== 'undefined' ? globalThis : self);
