/* Feature: light / dark mode.
 *
 * The canvas reads its background from computed CSS, so switching the
 * theme on <html> repaints the board correctly. The choice is stored and
 * applied before first paint (see the inline snippet in index.html) so
 * there is no white flash for dark-mode visitors.
 */
(function (TW) {
  'use strict';

  const KEY = 'txtwall.theme';
  const ICONS = { dark: '☾', light: '☀' };

  function current() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function apply(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    try { localStorage.setItem(KEY, mode); } catch (e) { /* private mode */ }

    const btn = document.getElementById('themeBtn');
    if (btn) {
      btn.textContent = ICONS[mode];
      btn.title = mode === 'dark' ? 'switch to light mode' : 'switch to dark mode';
      btn.setAttribute('aria-label', btn.title);
    }
    // the discord widget picks its own colours, so keep it in step
    const frame = document.querySelector('.discord-pop iframe');
    if (frame) frame.src = frame.src.replace(/theme=(dark|light)/, 'theme=' + mode);

    document.dispatchEvent(new CustomEvent('tw:theme', { detail: { mode: mode } }));
  }

  TW.feature('theme', {
    title: 'Light and dark mode',
    mount() {
      const btn = document.getElementById('themeBtn');
      if (btn) {
        btn.addEventListener('click', () => apply(current() === 'dark' ? 'light' : 'dark'));
      }
      apply(current());

      // follow the OS only while the visitor has not chosen for themselves
      const mq = window.matchMedia('(prefers-color-scheme: light)');
      const onChange = (e) => {
        let stored = null;
        try { stored = localStorage.getItem(KEY); } catch (err) { /* ignore */ }
        if (!stored) apply(e.matches ? 'light' : 'dark');
      };
      if (mq.addEventListener) mq.addEventListener('change', onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  });
})(window.TW);
