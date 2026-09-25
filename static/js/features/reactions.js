/* Feature: emoji reactions. One delegated listener, survives re-render. */
(function (TW) {
  'use strict';

  async function add(messageId, emoji) {
    try {
      await TW.api('/api/react', { method: 'POST', body: { message_id: messageId, emoji: emoji } });
      if (TW.wall) await TW.wall.refresh();
    } catch (e) {
      TW.toast(e.message, 'err');
    }
  }

  TW.feature('reactions', {
    title: 'Reactions',
    mount() {
      const wall = document.getElementById('wall');

      wall.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const action = btn.dataset.action;
        if (action === 'react') {
          add(parseInt(btn.dataset.id, 10), btn.dataset.emoji);
        } else if (action === 'react-add') {
          const pick = prompt('emoji to add:');
          if (pick && pick.trim()) add(parseInt(btn.dataset.id, 10), pick.trim().slice(0, 8));
        }
      });
    }
  });
})(window.TW);
