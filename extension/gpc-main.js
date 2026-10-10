(() => {
  'use strict';
  try {
    Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {
      configurable: true,
      enumerable: true,
      get: () => true
    });
  } catch (_) {}
})();
