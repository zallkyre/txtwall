/* Feature: search the loaded wall. Client-side only — nothing is uploaded.
 * A query of #12 jumps straight to that message.
 */
(function (TW) {
  'use strict';

  function apply() {
    const raw = (document.getElementById('searchInput') || {}).value || '';
    const q = raw.trim().toLowerCase();
    const wall = document.getElementById('wall');
    if (!wall) return;
    const cards = Array.from(wall.querySelectorAll('.msg'));
    const count = document.getElementById('searchCount');
    let shown = 0;

    if (q.startsWith('#') && /^#\d+$/.test(q)) {
      const id = q.slice(1);
      cards.forEach((c) => {
        const match = c.dataset.id === id;
        c.classList.toggle('hidden', !match);
        if (match) shown++;
      });
    } else if (q) {
      cards.forEach((c) => {
        const text = c.querySelector('.text');
        const hay = (text ? text.textContent : '[image]').toLowerCase();
        const match = hay.includes(q);
        c.classList.toggle('hidden', !match);
        if (match) shown++;
      });
    } else {
      cards.forEach((c) => c.classList.remove('hidden'));
    }

    if (count) {
      count.textContent = q
        ? shown + ' of ' + cards.length
        : (cards.length ? cards.length + ' shown' : '');
    }
  }

  TW.feature('search', {
    title: 'Search',
    mount() {
      const input = document.getElementById('searchInput');
      const clear = document.getElementById('searchClear');
      if (!input) return;
      document.getElementById('searchbar').style.display = 'flex';
      input.addEventListener('input', apply);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { input.value = ''; apply(); }
      });
      clear.addEventListener('click', () => { input.value = ''; apply(); input.focus(); });

      // "/" focuses search, like most code hosts
      document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement !== input &&
            ['INPUT', 'TEXTAREA'].indexOf(document.activeElement.tagName) === -1) {
          e.preventDefault();
          input.focus();
        }
      });
    }
  });

  TW.search = { apply: apply };
})(window.TW);
