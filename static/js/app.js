/* Boot.
 *
 * 1. ask the server what this site is called, where support lives and
 *    which features are enabled
 * 2. paint the static text from that config
 * 3. mount every enabled feature module
 *
 * If /api/config fails the site still runs, just with the built-in
 * defaults — a broken config should never blank the wall.
 */
(function (TW) {
  'use strict';

  async function boot() {
    let config = {};
    try {
      config = await TW.api('/api/config');
    } catch (e) {
      console.error('config unavailable, using defaults', e);
    }
    TW.config = config;

    if (config.site_name) {
      document.title = config.site_name;
      const h1 = document.querySelector('.brand h1');
      if (h1) h1.textContent = config.site_name;
    }
    if (config.tagline) {
      const tag = document.querySelector('.brand p');
      if (tag) tag.textContent = config.tagline;
    }
    if (config.footer_note) {
      const note = document.getElementById('footerNote');
      if (note) note.textContent = config.footer_note;
    }
    if (config.limits && config.limits.user) {
      const up = document.getElementById('upgradeText');
      if (up) {
        up.textContent = 'sign in for ' + config.limits.user + ' pixels a day instead of ' +
          config.limits.anon + '.';
      }
      const hint = document.getElementById('limitsHint');
      if (hint) {
        let msg = config.limits.anon + ' a day anonymous · ' +
          config.limits.user + ' a day with an account';
        if (config.cooldown > 0) msg += ' · ' + config.cooldown + 's apart';
        hint.textContent = msg;
      }
    }

    // let the canvas know the free allowance for the sign-up nudge
    TW.state.anonDaily = config.limits ? config.limits.anon : null;

    const mounted = TW.mountFeatures(config.features);
    console.log('txtwall features:', mounted.join(', '));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window.TW);
