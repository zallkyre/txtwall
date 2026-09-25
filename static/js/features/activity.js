/* Feature: live activity.
 *
 * Two read-only views of who is doing what: a rolling feed of the newest
 * placements, and a leaderboard of the accounts with the most pixels still
 * standing. Clicking a feed row or a leaderboard name jumps the canvas
 * there, so the feed is a way of exploring, not just decoration.
 */
(function (TW) {
  'use strict';

  let panel, body, tabFeed, tabBoard, mode = 'feed';

  function ago(seconds) {
    if (seconds < 60) return seconds + 's';
    if (seconds < 3600) return Math.round(seconds / 60) + 'm';
    if (seconds < 86400) return Math.round(seconds / 3600) + 'h';
    return Math.round(seconds / 86400) + 'd';
  }

  function jumpTo(x, y) {
    const v = TW.state.view;
    if (v) {
      v.goto(x, y);
      TW.toast('showing ' + x + ',' + y);
    }
  }

  async function showFeed() {
    mode = 'feed';
    panel.classList.add('on');
    body.textContent = 'loading...';
    try {
      const data = await TW.api('/api/activity?limit=20');
      const events = data.events || [];
      if (!events.length) { body.textContent = 'nothing yet today'; return; }
      body.textContent = '';
      events.forEach((ev) => {
        const row = TW.dom.el('button', {
          class: 'feed-row',
          title: 'jump to ' + ev.x + ',' + ev.y,
          onclick: () => jumpTo(ev.x, ev.y)
        }, [
          TW.dom.el('i', { class: 'dot', style: 'background:' + ev.color }),
          TW.dom.el('span', { class: 'feed-cell', text: ev.x + ',' + ev.y }),
          TW.dom.el('span', { class: 'feed-ago', text: ago(ev.ago) + ' ago' })
        ]);
        body.appendChild(row);
      });
    } catch (e) {
      body.textContent = 'feed unavailable';
    }
  }

  async function showBoard() {
    mode = 'board';
    panel.classList.add('on');
    body.textContent = 'loading...';
    try {
      const data = await TW.api('/api/leaderboard?limit=10');
      const artists = data.artists || [];
      if (!artists.length) { body.textContent = 'no pixels painted yet'; return; }
      body.textContent = '';
      const top = artists[0].pixels || 1;
      artists.forEach((a) => {
        const pct = Math.max(3, Math.round((a.pixels / top) * 100));
        const row = TW.dom.el('div', { class: 'board-row' }, [
          TW.dom.el('span', { class: 'rank', text: '#' + a.rank }),
          TW.dom.el('span', { class: 'board-name', text: a.name }),
          TW.dom.el('span', { class: 'board-bar' }, [
            TW.dom.el('i', { style: 'width:' + pct + '%' })
          ]),
          TW.dom.el('span', { class: 'board-n', text: String(a.pixels) })
        ]);
        body.appendChild(row);
      });
    } catch (e) {
      body.textContent = 'leaderboard unavailable';
    }
  }

  TW.feature('activity', {
    title: 'Live activity and leaderboard',
    mount() {
      panel = document.getElementById('activityPanel');
      body = document.getElementById('activityBody');
      tabFeed = document.getElementById('tabFeed');
      tabBoard = document.getElementById('tabBoard');
      if (!panel || !body) return;

      const open = document.getElementById('activityBtn');
      if (open) {
        open.addEventListener('click', () => {
          if (panel.classList.contains('on')) panel.classList.remove('on');
          else (mode === 'feed' ? showFeed : showBoard)();
        });
      }
      const close = document.getElementById('activityClose');
      if (close) close.addEventListener('click', () => panel.classList.remove('on'));

      if (tabFeed) tabFeed.addEventListener('click', () => {
        tabFeed.classList.add('on');
        tabBoard.classList.remove('on');
        showFeed();
      });
      if (tabBoard) tabBoard.addEventListener('click', () => {
        tabBoard.classList.add('on');
        tabFeed.classList.remove('on');
        showBoard();
      });

      // a pixel landing anywhere refreshes an open feed
      document.addEventListener('tw:remote', () => {
        if (panel.classList.contains('on') && mode === 'feed') showFeed();
      });

      // keyboard shortcuts: i opens the feed, l the leaderboard.
      // (a/w/s/d belong to panning, so they are not reused here)
      document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const k = e.key.toLowerCase();
        if (k === 'i') {
          if (panel.classList.contains('on') && mode === 'feed') panel.classList.remove('on');
          else {
            tabFeed.classList.add('on');
            tabBoard.classList.remove('on');
            showFeed();
          }
        }
        if (k === 'l') {
          tabBoard.classList.add('on');
          tabFeed.classList.remove('on');
          showBoard();
        }
        if (e.key === 'Escape') panel.classList.remove('on');
      });
    }
  });
})(window.TW);
