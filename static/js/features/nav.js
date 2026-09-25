/* Feature: navigation.
 *
 * The board is 256x256. At fit-zoom it is smaller than the screen; zoomed
 * in it is 12,000px across. This module owns the "how do I get around"
 * problem so the canvas only has to own the pixels:
 *
 *   - a minimap with a draggable viewport rectangle
 *   - zoom buttons and a live zoom readout
 *   - arrow / WASD panning, +/- zoom, 0 fit, C centre
 *   - a jump box for coordinates and #12.34 deep links
 *
 * It never mutates the view directly; it asks TW.state.view, which the
 * canvas publishes.
 */
(function (TW) {
  'use strict';

  const STEP = 60;          // pixels per arrow-key press
  const HOLD_MS = 380;      // how long a held key keeps repeating

  function view() { return TW.state.view; }

  function pan(dx, dy) {
    const v = view();
    if (v) v.panBy(dx, dy);
  }

  // ---------- minimap ----------
  function mountMinimap() {
    const wrap = document.getElementById('minimap');
    const cv = document.getElementById('miniCanvas');
    const box = document.getElementById('miniBox');
    if (!wrap || !cv) return;
    const ctx = cv.getContext('2d');

    const draw = () => {
      const v = view();
      if (!v) return;
      const size = v.size;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const side = cv.clientWidth || 132;
      if (cv.width !== side * dpr) {
        cv.width = side * dpr;
        cv.height = side * dpr;
      }
      const k = (side * dpr) / size;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, cv.width, cv.height);

      // every painted cell, one dot each
      v.pixels.forEach((colour, key) => {
        const [x, y] = key.split(',');
        ctx.fillStyle = colour;
        ctx.fillRect(x * k, y * k, Math.max(1, k), Math.max(1, k));
      });

      // viewport rectangle
      const W = v.viewW(), H = v.viewH();
      const rx = (-v.offX / v.cell) * k;
      const ry = (-v.offY / v.cell) * k;
      const rw = (W / v.cell) * k;
      const rh = (H / v.cell) * k;
      ctx.strokeStyle = getComputedStyle(document.documentElement)
        .getPropertyValue('--accent').trim() || '#7dd3fc';
      ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.fillStyle = 'rgba(125,211,252,0.12)';
      ctx.fillRect(rx, ry, rw, rh);
    };

    // redraw when the view moves or pixels change
    const v = view();
    if (v) {
      v.onView(draw);
      document.addEventListener('tw:painted', draw);
      document.addEventListener('tw:remote', draw);
      document.addEventListener('tw:theme', draw);
    }
    setInterval(draw, 4000);
    setTimeout(draw, 100);

    // drag the rectangle to move around
    const jump = (ev) => {
      const vv = view();
      if (!vv) return;
      const rect = cv.getBoundingClientRect();
      const k = (rect.width) / vv.size;
      const x = (ev.clientX - rect.left) / k;
      const y = (ev.clientY - rect.top) / k;
      vv.goto(Math.floor(x), Math.floor(y));
    };
    let dragging = false;
    cv.addEventListener('pointerdown', (e) => {
      dragging = true;
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* not capturable */ }
      jump(e);
    });
    cv.addEventListener('pointermove', (e) => { if (dragging) jump(e); });
    cv.addEventListener('pointerup', () => { dragging = false; });
    cv.addEventListener('pointercancel', () => { dragging = false; });

    if (box) {
      box.addEventListener('click', () => {
        const vv = view();
        if (vv) vv.toggleGrid();
      });
    }
  }

  // ---------- zoom buttons ----------
  function mountControls() {
    const on = (id, fn) => {
      const b = document.getElementById(id);
      if (b) b.addEventListener('click', fn);
    };
    on('zoomIn', () => { const v = view(); if (v) v.zoomBy(1.5); });
    on('zoomOut', () => { const v = view(); if (v) v.zoomBy(1 / 1.5); });
    on('fitBtn', () => { const v = view(); if (v) v.fit(); });
    on('centreBtn', () => { const v = view(); if (v) v.centre(); });

    // share the cell currently under the cursor, or the middle of the
    // view if the pointer is off the board. The canvas reads #p128.127.
    on('linkBtn', () => {
      const v = view();
      if (!v) return;
      let x, y;
      if (v.hover && v.hover.x >= 0) { x = v.hover.x; y = v.hover.y; }
      else {
        x = Math.floor((v.viewW() / 2 - v.offX) / v.cell);
        y = Math.floor((v.viewH() / 2 - v.offY) / v.cell);
      }
      const link = location.origin + '/#p' + x + '.' + y;
      const done = () => TW.toast('link to ' + x + ',' + y + ' copied', 'ok');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, () => {
          prompt('copy this link', link);
        });
      } else {
        TW.copy(link).then(done);
      }
    });

    // jump box: "128,127" jumps there and centres
    const input = document.getElementById('jump');
    const go = () => {
      const v = view();
      if (!v || !input) return;
      const m = input.value.trim().match(/^(\d+)\s*[,.\s]\s*(\d+)$/);
      if (!m) { TW.toast('type a cell like 128,127'); return; }
      v.goto(parseInt(m[1], 10), parseInt(m[2], 10));
      TW.toast('jumped to ' + m[1] + ',' + m[2], 'ok');
    };
    if (input) {
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    }
    on('jumpBtn', go);
  }

  // ---------- keyboard ----------
  function mountKeys() {
    const typing = (e) =>
      e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
      e.target.isContentEditable;

    document.addEventListener('keydown', (e) => {
      if (typing(e)) return;
      const v = view();
      if (!v) return;

      const key = e.key.toLowerCase();
      const fast = e.shiftKey ? 2.5 : 1;
      let handled = true;
      switch (key) {
        case 'arrowleft': case 'a': pan(STEP * fast, 0); break;
        case 'arrowright': case 'd': pan(-STEP * fast, 0); break;
        case 'arrowup': case 'w': pan(0, STEP * fast); break;
        case 'arrowdown': case 's': pan(0, -STEP * fast); break;
        case '+': case '=': v.zoomBy(1.5); break;
        case '-': case '_': v.zoomBy(1 / 1.5); break;
        case '0': v.fit(); break;
        case 'c': v.centre(); break;
        default: handled = false;
      }
      if (handled) e.preventDefault();
    });
  }

  TW.feature('nav', {
    title: 'Minimap, zoom and keyboard navigation',
    mount() {
      // the canvas registers TW.state.view during its own mount, which
      // happens first; wait a tick anyway so order can never bite us
      if (!view()) setTimeout(() => mountAll(), 0);
      else mountAll();

      function mountAll() {
        mountMinimap();
        mountControls();
        mountKeys();
        const v = view();
        if (v) {
          const z = document.getElementById('zoomLabel');
          v.onView(() => { if (z) z.textContent = v.cell + 'x'; });
        }
      }
    }
  });
})(window.TW);
