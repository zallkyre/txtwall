/* Feature: support panel — the owner's address plus a few live numbers.
 * The address comes from the server config, so changing it never means
 * editing this file or the HTML.
 */
(function (TW) {
  'use strict';

  TW.feature('support_panel', {
    title: 'Support contact',
    mount() {
      const email = TW.config.support_email || '';
      const label = TW.config.support_label || 'email support';
      const line = document.getElementById('supportLine');
      if (!line) return;

      if (email) {
        const link = TW.dom.el('a', {
          class: 'mail',
          href: 'mailto:' + email,
          text: email,
          title: 'click to copy, or open your mail app'
        });
        link.addEventListener('click', async (e) => {
          if (!e.ctrlKey && !e.metaKey && !e.shiftKey) e.preventDefault();
          const ok = await TW.copy(email);
          TW.toast(ok ? 'copied ' + email : email, ok ? 'ok' : '');
        });
        line.appendChild(TW.dom.el('span', { class: 'support-line' }, [
          TW.dom.el('span', { text: 'need a human? ' }),
          link,
          TW.dom.el('span', { text: ' — ' + label })
        ]));
      }

      const stats = document.getElementById('supportStats');
      if (!stats) return;
      const plural = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');
      TW.api('/api/stats').then((s) => {
        stats.textContent = s.painted + ' of ' + s.cells + ' cells painted · ' +
          s.painted_today + ' today · ' + plural(s.artists || 0, 'artist') + ' · ' +
          plural(s.accounts, 'account') + ' · nothing expires';
      }).catch(() => { stats.textContent = ''; });
    }
  });
})(window.TW);
