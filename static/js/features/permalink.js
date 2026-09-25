/* Feature: permalinks. Click a message number to copy a link to it.
 * Opening site.example/#m12 scrolls to that message and flashes it.
 */
(function (TW) {
  'use strict';

  function flash(node) {
    if (!node) return;
    node.scrollIntoView({ behavior: 'smooth', block: 'center' });
    node.classList.add('flash');
    setTimeout(() => node.classList.remove('flash'), 2500);
  }

  function apply() {
    const m = /^#m(\d+)$/.exec(window.location.hash || '');
    if (!m) return;
    flash(document.querySelector('.msg[data-id="' + m[1] + '"]'));
  }

  TW.feature('permalink', {
    title: 'Message links',
    always: true,
    mount() {
      document.getElementById('wall').addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-action="link"]');
        if (!btn) return;
        const id = btn.dataset.id;
        const url = window.location.origin + window.location.pathname + '#m' + id;
        history.replaceState(null, '', '#m' + id);
        const ok = await TW.copy(url);
        TW.toast(ok ? 'link copied: #' + id : url, ok ? 'ok' : '');
      });

      window.addEventListener('hashchange', apply);
      // the wall polls in, so retry the jump for a few seconds
      let tries = 0;
      const timer = setInterval(() => {
        apply();
        if (++tries > 12) clearInterval(timer);
      }, 500);
    }
  });

  TW.permalink = { apply: apply };
})(window.TW);
