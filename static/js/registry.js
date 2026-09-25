/* Front-end feature registry.
 *
 * A front-end feature is a file in js/features/ that calls TW.feature():
 *
 *   TW.feature('search', { mount() { ... } });
 *
 * app.js imports every file in that folder, then mounts the ones the
 * server says are enabled (GET /api/config -> features). Adding a
 * front-end feature never means editing index.html or app.js.
 */
(function (TW) {
  'use strict';

  TW.feature = function (name, def) {
    TW.features.push(Object.assign({ name: name, mount: function () {} }, def));
  };

  TW.mountFeatures = function (enabled) {
    const on = enabled || {};
    const mounted = [];
    TW.features.forEach((f) => {
      // a feature is hidden when the server has no matching routes for it
      if (on[f.name] === false) return;
      try {
        f.mount();
        mounted.push(f.name);
      } catch (e) {
        console.error('feature ' + f.name + ' failed to mount', e);
      }
    });
    return mounted;
  };
})(window.TW);
