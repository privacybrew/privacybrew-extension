(() => {
  'use strict';
  const EVENT_NAME = 'privacybrew:fingerprint';
  const FONT_LIMIT = 20;
  const fontFamilies = new Set();
  const sent = new Set();
  const sentDetails = [];

  function nativeLike(fn, name) {
    try {
      Object.defineProperty(fn, 'toString', { value: () => `function ${name}() { [native code] }` });
    } catch (_) {}
    return fn;
  }

  function scriptOrigin() {
    try {
      const stack = String(new Error().stack || '');
      const matches = stack.match(/(?:https?|file|chrome-extension):\/\/[^\s)]+/g) || [];
      for (const raw of matches) {
        const url = raw.replace(/:\d+:\d+$/, '').replace(/:\d+$/, '');
        if (url.startsWith('chrome-extension://')) continue;
        if (url.endsWith('/content-main.js')) continue;
        return url;
      }
      return 'Script not known';
    } catch (_) {
      return 'Script not known';
    }
  }

  function send(technique, origin) {
    const key = technique + '|' + (origin || 'Unknown script');
    if (sent.has(key)) return;
    sent.add(key);
    try {
      // A page can forge this event. That can only add noise to its own report.
      const detail = { technique, origin: origin || scriptOrigin() };
      sentDetails.push(detail);
      document.dispatchEvent(new CustomEvent(EVENT_NAME, { detail }));
    } catch (_) {}
  }

  function isUsefulCanvas(canvas, width, height) {
    const w = Number(width || (canvas && canvas.width) || 0);
    const h = Number(height || (canvas && canvas.height) || 0);
    return w >= 16 && h >= 16;
  }

  function wrap(obj, name, makeWrapper) {
    try {
      if (!obj || !obj[name]) return;
      const original = obj[name];
      const wrapped = nativeLike(makeWrapper(original), name);
      Object.defineProperty(obj, name, { value: wrapped, configurable: true, writable: true });
    } catch (_) {}
  }

  function replay() {
    try {
      for (const detail of sentDetails) document.dispatchEvent(new CustomEvent(EVENT_NAME, { detail }));
    } catch (_) {}
  }

  document.addEventListener('privacybrew:bridge-ready', replay);
  setTimeout(replay, 50);
  setTimeout(replay, 250);
  setTimeout(replay, 1000);

  wrap(HTMLCanvasElement.prototype, 'toDataURL', (original) => function (...args) {
    try { if (isUsefulCanvas(this)) send('canvas'); } catch (_) {}
    return original.apply(this, args);
  });
  wrap(HTMLCanvasElement.prototype, 'toBlob', (original) => function (...args) {
    try { if (isUsefulCanvas(this)) send('canvas'); } catch (_) {}
    return original.apply(this, args);
  });
  if (self.CanvasRenderingContext2D) {
    wrap(CanvasRenderingContext2D.prototype, 'getImageData', (original) => function (...args) {
      try { if (isUsefulCanvas(this.canvas, args[2], args[3])) send('canvas'); } catch (_) {}
      return original.apply(this, args);
    });
    wrap(CanvasRenderingContext2D.prototype, 'measureText', (original) => function (...args) {
      try {
        const font = String(this.font || '').toLowerCase();
        const family = font.replace(/^.*?\s(.*)$/u, '$1').replace(/["']/g, '').trim();
        if (family) fontFamilies.add(family);
        if (fontFamilies.size >= FONT_LIMIT) send('fonts');
      } catch (_) {}
      return original.apply(this, args);
    });
  }

  function wrapWebGl(proto) {
    if (!proto) return;
    wrap(proto, 'getExtension', (original) => function (...args) {
      try { if (String(args[0]) === 'WEBGL_debug_renderer_info') send('webgl'); } catch (_) {}
      return original.apply(this, args);
    });
    wrap(proto, 'getParameter', (original) => function (...args) {
      try { if (args[0] === 37445 || args[0] === 37446) send('webgl'); } catch (_) {}
      return original.apply(this, args);
    });
  }
  wrapWebGl(self.WebGLRenderingContext && WebGLRenderingContext.prototype);
  wrapWebGl(self.WebGL2RenderingContext && WebGL2RenderingContext.prototype);

  const AudioClass = self.OfflineAudioContext || self.webkitOfflineAudioContext;
  if (AudioClass && AudioClass.prototype) {
    wrap(AudioClass.prototype, 'startRendering', (original) => function (...args) {
      try { send('audio'); } catch (_) {}
      return original.apply(this, args);
    });
  }
})();
