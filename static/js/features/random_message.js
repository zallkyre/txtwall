/* Feature: "surprise me" — pull one random message and highlight it. */
(function (TW) {
  'use strict';

  TW.feature('random_message', {
    title: 'Surprise me',
    mount() {
      document.getElementById('surpriseBtn').addEventListener('click', async () => {
        const wall = document.getElementById('wall');
        try {
          const m = await TW.api('/api/messages/random');
          if (!m.found) { TW.toast('nothing to surprise you with yet', 'err'); return; }

          // already on screen? just point at it
          const existing = wall.querySelector('.msg[data-id="' + m.id + '"]');
          if (existing) { existing.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }

          let text = '';
          if (m.ct) {
            try { text = await TW.crypto.decrypt(m.ct, m.iv); } catch (e) { text = '(undecryptable)'; }
          }
          const esc = TW.dom.escape;
          const time = new Date(m.created_at * 1000)
            .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const el = TW.dom.el('div', {
            class: 'msg flash',
            'data-id': m.id,
            html: (text ? '<div class="text">' + esc(text) + '</div>' : '') +
              (m.image ? '<img src="/uploads/' + m.image + '" loading="lazy" alt="image">' : '') +
              '<div class="meta"><button class="id-link" data-action="link" data-id="' + m.id +
              '">#' + m.id + ' (random)</button><span>' + time + '</span></div>'
          });
          wall.prepend(el);
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setTimeout(() => el.classList.remove('flash'), 4000);
        } catch (e) { console.error(e); }
      });
    }
  });
})(window.TW);
