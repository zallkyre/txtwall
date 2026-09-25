/* The pixel canvas.
 *
 * One <canvas>, painted from a Map of "x,y" -> colour. The server owns
 * the truth; this keeps a cursor into the change feed and repaints only
 * the cells that moved.
 *
 * Controls: click to place, E or right-click to erase, wheel to zoom,
 * drag to pan, G to toggle the gridlines.
 */
TW.feature('canvas', {
  mount() {
    const cv = document.getElementById('board');
    if (!cv) return;
    const ctx = cv.getContext('2d', { alpha: false });

    const size = TW.config.grid_size || 256;
    const palette = TW.config.palette || ['#000000'];
    const pixels = TW.state.pixels;
    let cell = 4;          // on-screen size of one pixel
    let offX = 0, offY = 0; // top-left of the view, in canvas pixels
    let erasing = false;
    let reporting = false;
    let showGrid = true;
    let raf = null;

    cv.width = window.innerWidth;
    cv.height = window.innerHeight - 80;

    // ---------- painting ----------
    function bg() { return getComputedStyle(document.body).backgroundColor || '#0d0d0f'; }

    function draw() {
      raf = null;
      ctx.fillStyle = bg();
      ctx.fillRect(0, 0, cv.width, cv.height);

      // checkerboard behind empty cells so the grid edge is visible
      const x0 = Math.max(0, Math.floor(offX / cell));
      const y0 = Math.max(0, Math.floor(offY / cell));
      const x1 = Math.min(size - 1, Math.ceil((offX + cv.width) / cell));
      const y1 = Math.min(size - 1, Math.ceil((offY + cv.height) / cell));
      if (cell < 5) {
        ctx.fillStyle = 'rgba(255,255,255,0.028)';
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
      ctx.strokeStyle = 'rgba(255,255,255,0.16)';
      ctx.lineWidth = 1;
      ctx.strokeRect(-0.5, -0.5, size * cell + 1, size * cell + 1);

      if (showGrid && cell >= 7) {
        ctx.strokeStyle = 'rgba(255,255,255,0.07)';
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
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.strokeRect(
          Math.round(hover.x * cell - offX) + 0.5,
          Math.round(hover.y * cell - offY) + 0.5,
          cell, cell
        );
      }
      updateHud();
    }

    function schedule() { if (raf === null) raf = requestAnimationFrame(draw); }

    const hover = { x: -1, y: -1 };

    // ---------- coordinates ----------
    function toCell(clientX, clientY) {
      const rect = cv.getBoundingClientRect();
      const x = Math.floor((clientX - rect.left + offX) / cell);
      const y = Math.floor((clientY - rect.top + offY) / cell);
      if (x < 0 || y < 0 || x >= size || y >= size) return { x: -1, y: -1 };
      return { x, y };
    }

    // ---------- view helpers ----------
    function fit() {
      const margin = 24;
      cell = Math.max(1, Math.floor(Math.min(
        (cv.width - margin) / size, (cv.height - margin) / size
      )));
      centre();
    }
    function centre() {
      offX = Math.round((size * cell - cv.width) / 2);
      offY = Math.round((size * cell - cv.height) / 2);
      schedule();
    }
    function clampView() {
      const maxX = Math.max(0, size * cell - cv.width);
      const maxY = Math.max(0, size * cell - cv.height);
      offX = Math.min(0, Math.max(-maxX, offX));
      offY = Math.min(0, Math.max(-maxY, offY));
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
        if (res.noop) TW.toast('nothing to erase there');
      } catch (e) {
        if (e.data && e.data.state) TW.paintMeter(e.data.state);
        TW.toast(e.message);
        // only tick a countdown down when the server actually sent one
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

    // ---------- input ----------
    let dragging = false, dragMoved = false, lastX = 0, lastY = 0;

    cv.addEventListener('mousedown', (e) => {
      dragging = true; dragMoved = false;
      lastX = e.clientX; lastY = e.clientY;
      if (e.button === 2) { erasing = true; markMode(); }
    });
    window.addEventListener('mouseup', (e) => {
      if (!dragging) return;
      dragging = false;
      if (dragMoved) return;
      // toCell returns -1 outside the board, so a release anywhere else
      // (over the toolbar, the page edge) simply does nothing
      const c = toCell(e.clientX, e.clientY);
      if (c.x < 0) return;
      if (reporting) {
        reporting = false;
        erasing = false;
        markMode();
        document.dispatchEvent(new CustomEvent('tw:report', { detail: { x: c.x, y: c.y } }));
        return;
      }
      put(c.x, c.y, erasing || e.button === 2);
      if (e.button === 2) { erasing = false; markMode(); }
    });
    cv.addEventListener('mousemove', (e) => {
      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY;
        if (dx || dy) dragMoved = true;
        offX += dx; offY += dy;
        lastX = e.clientX; lastY = e.clientY;
        clampView(); schedule();
        return;
      }
      const c = toCell(e.clientX, e.clientY);
      if (c.x !== hover.x || c.y !== hover.y) { hover.x = c.x; hover.y = c.y; schedule(); }
    });
    cv.addEventListener('mouseleave', () => { hover.x = -1; schedule(); });
    cv.addEventListener('contextmenu', (e) => e.preventDefault());
    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = cv.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const before = { x: (mx + offX) / cell, y: (my + offY) / cell };
      cell = Math.min(48, Math.max(1, Math.round(cell * (e.deltaY < 0 ? 1.25 : 0.8))));
      offX = Math.round(mx - before.x * cell);
      offY = Math.round(my - before.y * cell);
      clampView(); schedule();
    }, { passive: false });

    window.addEventListener('resize', () => {
      cv.width = window.innerWidth;
      cv.height = window.innerHeight - 80;
      clampView(); schedule();
    });

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
        hud.textContent = pixels.size + ' painted · ' + cell + 'x zoom';
      } else {
        const here = pixels.get(hover.x + ',' + hover.y);
        hud.textContent = hover.x + ', ' + hover.y + (here ? ' · ' + here : ' · empty');
      }
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
        if (data.events && data.events.length) schedule();
        TW.state.cursor = data.cursor;
        TW.paintMeter(data.state);
      } catch (e) { /* the next tick tries again */ }
    }

    buildPalette();
    setColour(selected);
    TW.mountMeter();
    load().then(() => setInterval(poll, 5000));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

    // deep link: #p12.34 focuses that cell
    const m = location.hash.match(/^#p(\d+)\.(\d+)$/);
    if (m) {
      const [tx, ty] = [parseInt(m[1], 10), parseInt(m[2], 10)];
      offX = cv.width / 2 - tx * cell;
      offY = cv.height / 2 - ty * cell;
      schedule();
    }

    TW.state.reportPixel = function (x, y) {
      document.dispatchEvent(new CustomEvent('tw:report', { detail: { x, y } }));
    };
  }
});
