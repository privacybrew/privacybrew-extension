(() => {
  'use strict';
  try {
    Object.defineProperty(Navigator.prototype, 'doNotTrack', {
      configurable: true,
      enumerable: true,
      get: () => '1'
    });
  } catch (_) {}
})();
