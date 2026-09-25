/* The pixel canvas.
 *
 * One <canvas>, painted from a Map of "x,y" -> colour. The server owns
 * the truth; this keeps a cursor into the change feed and repaints only
 * the cells that moved.
 *
 * Controls: click to place, E or right-click to erase, wheel to zoom,
 * drag to pan, G toggles gridlines. Touch: one finger pans, two pinch.
 *
 * The view (zoom, pan, centre, goto) is published on TW.state.view so the
 * minimap, the zoom buttons and the keyboard shortcuts in nav.js can all
 * drive this one canvas instead of fighting over it.
 */
TW.feature('canvas', {
  mount() {
    const cv = document.getElementById('board');
    const stage = document.getElementById('stage');
    if (!cv || !stage) return;
    const ctx = cv.getContext('2d', { alpha: false });

    const size = TW.config.grid_size || 256;
    const palette = TW.config.palette || ['#000000'];
    const pixels = TW.state.pixels;
    let cell = 4;            // on-screen size of one pixel
    let offX = 0, offY = 0;  // top-left of the view, in canvas pixels
    let erasing = false;
    let reporting = false;
    let showGrid = true;
    let raf = null;

    const listeners = [];
    function onView(fn) { listeners.push(fn); }
    function notifyView() { listeners.forEach((f) => { try { f(); } catch (e) {} }); }

    // ---------- sizing ----------
    function resize() {
      const r = stage.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      // the backing store is CSS size x dpr so the board stays sharp on
      // retina screens; all drawing below then works in CSS pixels
      const cssW = Math.max(1, Math.floor(r.width));
      const cssH = Math.max(1, Math.floor(r.height));
      cv.width = Math.floor(cssW * dpr);
      cv.height = Math.floor(cssH * dpr);
      cv.style.width = cssW + 'px';
      cv.style.height = cssH + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.__scale = dpr;
      cv.__W = cssW;
      cv.__H = cssH;
      clampView();
      schedule();
    }
    // the draw calls use CSS pixel maths, so undo the dpr transform
    function paint() {
      const s = ctx.__scale || 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(s, s);
    }

    // ---------- painting ----------
    function bg() { return getComputedStyle(document.body).backgroundColor || '#0d0d0f'; }

    function draw() {
      raf = null;
      paint();
      const W = viewW(), H = viewH();
      ctx.fillStyle = bg();
      ctx.fillRect(0, 0, W, H);

      // checkerboard behind empty cells so the grid edge is visible
      const x0 = Math.max(0, Math.floor(offX / cell));
      const y0 = Math.max(0, Math.floor(offY / cell));
      const x1 = Math.min(size - 1, Math.ceil((offX + W) / cell));
      const y1 = Math.min(size - 1, Math.ceil((offY + H) / cell));
      if (cell < 5) {
        ctx.fillStyle = 'rgba(128,128,128,0.07)';
        for (let y = y0; y <= y1; y += 1) {
          for (let x = x0 + ((y % 2) ? 1 : 0); x <= x1; x += 2) {
            ctx.fillRect(x * cell - offX, y * cell - offY, cell, cell);
          }
        }
      }

      pixels.forEach((color, key) => {
        const [x, y] = key.split(',');
        ctx.fillStyle = color;
        ctx.fillRect(x * cell - offX, y * cell - offY, cell + 1, cell + 1);
      });

      // canvas border
      ctx.strokeStyle = 'rgba(128,128,128,0.35)';
      ctx.lineWidth = 1;
      ctx.strokeRect(-0.5, -0.5, size * cell + 1, size * cell + 1);

      if (showGrid && cell >= 7) {
        ctx.strokeStyle = 'rgba(128,128,128,0.12)';
        ctx.beginPath();
        for (let x = 0; x <= size; x += 8) {
          ctx.moveTo(Math.round(x * cell - offX) + 0.5, 0);
          ctx.lineTo(Math.round(x * cell - offX) + 0.5, size * cell);
        }
        for (let y = 0; y <= size; y += 8) {
          ctx.moveTo(0, Math.round(y * cell - offY) + 0.5);
          ctx.lineTo(size * cell, Math.round(y * cell - offY) + 0.5);
        }
        ctx.stroke();
      }

      // hover readout
      if (hover.x >= 0) {
        ctx.strokeStyle = 'rgba(255,255,255,0.6)';
        ctx.strokeRect(
          Math.round(hover.x * cell - offX) + 0.5,
          Math.round(hover.y * cell - offY) + 0.5,
          cell, cell
        );
      }

      // edge arrows: when the board is bigger than the view, show which
      // way there is more to see
      drawEdges(W, H);
      updateHud();
    }

    function drawEdges(W, H) {
      const left = offX < -1, right = offX + W < size * cell - 1;
      const top = offY < -1, bottom = offY + H < size * cell - 1;
      if (!left && !right && !top && !bottom) return;
      const m = 18, a = 0.5;
      ctx.fillStyle = 'rgba(255,255,255,' + a + ')';
      ctx.beginPath();
      if (left) { ctx.moveTo(m, H / 2 - 9); ctx.lineTo(m + 7, H / 2); ctx.lineTo(m, H / 2 + 9); }
      if (right) { ctx.moveTo(W - m, H / 2 - 9); ctx.lineTo(W - m - 7, H / 2); ctx.lineTo(W - m, H / 2 + 9); }
      if (top) { ctx.moveTo(W / 2 - 9, m); ctx.lineTo(W / 2, m + 7); ctx.lineTo(W / 2 + 9, m); }
      if (bottom) { ctx.moveTo(W / 2 - 9, H - m); ctx.lineTo(W / 2, H - m - 7); ctx.lineTo(W / 2 + 9, H - m); }
      ctx.fill();
    }

    function schedule() { if (raf === null) raf = requestAnimationFrame(draw); }

    const hover = { x: -1, y: -1 };

    // ---------- coordinates ----------
    function viewW() { return cv.__W || cv.width; }
    function viewH() { return cv.__H || cv.height; }

    function toCell(clientX, clientY) {
      const rect = cv.getBoundingClientRect();
      const x = Math.floor((clientX - rect.left + offX) / cell);
      const y = Math.floor((clientY - rect.top + offY) / cell);
      if (x < 0 || y < 0 || x >= size || y >= size) return { x: -1, y: -1 };
      return { x, y };
    }

    // ---------- view helpers ----------
    function clampCell(c) { return Math.min(48, Math.max(1, Math.round(c))); }

    function fit() {
      const margin = 28;
      cell = Math.max(1, Math.floor(Math.min(
        (viewW() - margin) / size, (viewH() - margin) / size
      )));
      centre();
    }
    // put the middle of the board in the middle of the view
    function centre() {
      offX = Math.round((viewW() - size * cell) / 2);
      offY = Math.round((viewH() - size * cell) / 2);
      schedule(); notifyView();
    }
    function clampView() {
      const maxX = Math.max(0, size * cell - viewW());
      const maxY = Math.max(0, size * cell - viewH());
      offX = Math.min(0, Math.max(-maxX, offX));
      offY = Math.min(0, Math.max(-maxY, offY));
    }
    // zoom keeping the cell under (mx,my) — both stage-relative — fixed
    function zoomTo(next, mx, my) {
      const W = viewW(), H = viewH();
      if (mx === undefined) { mx = W / 2; my = H / 2; }
      const before = { x: (mx + offX) / cell, y: (my + offY) / cell };
      cell = clampCell(next);
      offX = Math.round(mx - before.x * cell);
      offY = Math.round(my - before.y * cell);
      clampView(); schedule(); notifyView();
    }
    function zoomBy(factor, mx, my) { zoomTo(cell * factor, mx, my); }
    function panBy(dx, dy) {
      offX += dx; offY += dy;
      clampView(); schedule(); notifyView();
    }
    // centre a given cell in the view (its middle, not its top-left corner)
    function goto(x, y) {
      x = Math.max(0, Math.min(size - 1, x));
      y = Math.max(0, Math.min(size - 1, y));
      offX = Math.round(viewW() / 2 - (x + 0.5) * cell);
      offY = Math.round(viewH() / 2 - (y + 0.5) * cell);
      clampView(); schedule(); notifyView();
    }

    // ---------- painting pixels ----------
    let selected = palette[0] || '#000000';
    function setColour(c) {
      selected = c;
      TW.dom.$$('.swatch').forEach((s) => s.classList.toggle('on', s.dataset.colour === c));
      document.documentElement.style.setProperty('--selected', c);
    }
    function buildPalette() {
      const box = document.getElementById('palette');
      if (!box) return;
      palette.forEach((c) => {
        const s = TW.dom.el('button', {
          class: 'swatch', title: c, 'data-colour': c,
          style: 'background:' + c,
          onclick: () => { setColour(c); erasing = false; reporting = false; markMode(); }
        });
        box.appendChild(s);
      });
    }

    function markMode() {
      const b = document.getElementById('eraseBtn');
      if (b) b.classList.toggle('on', erasing);
      cv.classList.toggle('erasing', erasing);
      cv.classList.toggle('reporting', reporting);
      const hint = document.getElementById('reportHint');
      if (hint) hint.classList.toggle('on', reporting);
    }

    async function put(x, y, erase) {
      if (x < 0) return;
      const path = erase ? '/api/pixel/erase' : '/api/pixel';
      const body = erase ? { x, y } : { x, y, color: selected };
      try {
        const res = await TW.api(path, { method: 'POST', body });
        if (erase) pixels.delete(x + ',' + y);
        else pixels.set(x + ',' + y, res.color);
        TW.paintMeter(res.state);
        schedule();
        document.dispatchEvent(new CustomEvent('tw:painted', {
          detail: { x, y, color: erase ? null : res.color, erased: !!erase }
        }));
        if (res.noop) TW.toast('nothing to erase there');
      } catch (e) {
        if (e.data && e.data.state) TW.paintMeter(e.data.state);
        TW.toast(e.message);
        const cd = e.data && e.data.cooldown;
        if (e.status === 429 && cd > 0) {
          let left = cd;
          const tick = setInterval(() => {
            left -= 1;
            const a = TW.state.allowance || {};
            TW.paintMeter(Object.assign({}, a, { cooldown: Math.max(0, left) }));
            if (left <= 0) clearInterval(tick);
          }, 1000);
        }
      }
    }

    // ---------- input: pointer events cover mouse, touch and pen ----------
    const pointers = new Map();
    let dragging = false, dragMoved = false, lastX = 0, lastY = 0;
    let pinch = null;

    cv.addEventListener('contextmenu', (e) => e.preventDefault());

    cv.addEventListener('pointerdown', (e) => {
      // capture is an optimisation, not a requirement: if the browser
      // refuses it, input must still work
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* not capturable */ }
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) {
        dragging = true; dragMoved = false;
        lastX = e.clientX; lastY = e.clientY;
        if (e.button === 2) { erasing = true; markMode(); }
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = {
          dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
          cell: cell,
          mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
        };
        dragging = false;
      }
    });

    cv.addEventListener('pointermove', (e) => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pinch && pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
        const rect = cv.getBoundingClientRect();
        const mx = pinch.mid.x - rect.left, my = pinch.mid.y - rect.top;
        const before = { x: (mx + offX) / cell, y: (my + offY) / cell };
        cell = clampCell(pinch.cell * (dist / pinch.dist));
        offX = Math.round(mx - before.x * cell);
        offY = Math.round(my - before.y * cell);
        clampView(); schedule(); notifyView();
        return;
      }

      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY;
        if (dx || dy) dragMoved = true;
        offX += dx; offY += dy;
        lastX = e.clientX; lastY = e.clientY;
        clampView(); schedule(); notifyView();
        return;
      }
      const c = toCell(e.clientX, e.clientY);
      if (c.x !== hover.x || c.y !== hover.y) { hover.x = c.x; hover.y = c.y; schedule(); }
    });

    function release(e) {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      if (!dragging) return;
      dragging = false;
      if (dragMoved) return;
      const c = toCell(e.clientX, e.clientY);
      if (c.x < 0) return;
      if (reporting) {
        reporting = false; erasing = false; markMode();
        document.dispatchEvent(new CustomEvent('tw:report', { detail: { x: c.x, y: c.y } }));
        return;
      }
      put(c.x, c.y, erasing || e.button === 2);
      if (e.button === 2) { erasing = false; markMode(); }
    }
    cv.addEventListener('pointerup', release);
    cv.addEventListener('pointercancel', (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      dragging = false;
    });
    cv.addEventListener('pointerleave', () => { hover.x = -1; hover.y = -1; schedule(); });

    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = cv.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      zoomBy(e.deltaY < 0 ? 1.25 : 0.8, mx, my);
    }, { passive: false });

    cv.addEventListener('dblclick', (e) => {
      const rect = cv.getBoundingClientRect();
      zoomBy(1.6, e.clientX - rect.left, e.clientY - rect.top);
    });

    window.addEventListener('resize', resize);
    if (window.ResizeObserver) {
      new ResizeObserver(resize).observe(stage);
    }

    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'e' || e.key === 'E') { erasing = !erasing; reporting = false; markMode(); }
      if (e.key === 'r' || e.key === 'R') { reporting = !reporting; erasing = false; markMode(); }
      if (e.key === 'g' || e.key === 'G') { showGrid = !showGrid; schedule(); }
      if (e.key === 'f' || e.key === 'F') { fit(); }
      const n = parseInt(e.key, 10);
      if (n >= 1 && n <= palette.length) setColour(palette[n - 1]);
    });

    // ---------- HUD ----------
    function updateHud() {
      const hud = document.getElementById('hud');
      if (!hud) return;
      if (hover.x < 0) {
        hud.textContent = pixels.size + ' painted · ' + cell + 'x';
      } else {
        const here = pixels.get(hover.x + ',' + hover.y);
        hud.textContent = hover.x + ', ' + hover.y + (here ? ' · ' + here : ' · empty');
      }
      const z = document.getElementById('zoomLabel');
      if (z) z.textContent = cell + 'x';
    }

    // ---------- sync with the server ----------
    async function load() {
      const data = await TW.api('/api/canvas');
      pixels.clear();
      (data.pixels || []).forEach(([x, y, c]) => pixels.set(x + ',' + y, c));
      TW.state.size = data.size;
      TW.state.palette = data.palette;
      TW.state.cursor = data.cursor;
      TW.paintMeter(data.state);
      const painted = document.getElementById('painted');
      if (painted) painted.textContent = data.painted;
      resize();
      fit();
    }

    async function poll() {
      if (document.hidden) return;
      try {
        const data = await TW.api('/api/canvas?since=' + TW.state.cursor);
        (data.events || []).forEach(([id, x, y, colour]) => {
          if (colour === null) pixels.delete(x + ',' + y);
          else pixels.set(x + ',' + y, colour);
        });
        if (data.events && data.events.length) {
          schedule();
          notifyView();
          // hand the newest placements to the activity feed
          data.events.slice().reverse().forEach(([id, x, y, colour]) => {
            document.dispatchEvent(new CustomEvent('tw:remote', {
              detail: { id, x, y, color: colour }
            }));
          });
        }
        TW.state.cursor = data.cursor;
        TW.paintMeter(data.state);
      } catch (e) { /* the next tick tries again */ }
    }

    buildPalette();
    setColour(selected);
    TW.mountMeter();
    resize();
    load().then(() => setInterval(poll, 5000));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

    // deep link: #p12.34 focuses that cell
    const m = location.hash.match(/^#p(\d+)\.(\d+)$/);
    if (m) {
      const [tx, ty] = [parseInt(m[1], 10), parseInt(m[2], 10)];
      goto(tx, ty);
    }

    // ---------- shared view API for nav.js ----------
    TW.state.view = {
      size: size,
      get cell() { return cell; },
      get pixels() { return pixels; },
      get offX() { return offX; },
      get offY() { return offY; },
      get hover() { return hover; },
      viewW: viewW,
      viewH: viewH,
      toCell: toCell,
      zoomBy: zoomBy,
      zoomTo: zoomTo,
      fit: fit,
      centre: centre,
      goto: goto,
      panBy: panBy,
      onView: onView,
      toggleGrid: function () { showGrid = !showGrid; schedule(); return showGrid; },
      isGrid: function () { return showGrid; }
    };

    TW.state.reportPixel = function (x, y) {
      document.dispatchEvent(new CustomEvent('tw:report', { detail: { x, y } }));
    };
  }
});
