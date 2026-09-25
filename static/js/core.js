/* txtwall — shared core.
 *
 * Everything hangs off the global `TW`. A feature module never needs to
 * know about another feature; it only uses TW.config, TW.api and TW.dom.
 */
window.TW = window.TW || {};

(function (TW) {
  'use strict';

  TW.config = {};
  TW.features = [];
  TW.state = { pixels: new Map(), cursor: 0, me: null, size: 256, palette: [] };

  // ---------- tiny DOM helper ----------
  TW.dom = {
    $: (sel, root) => (root || document).querySelector(sel),
    $$: (sel, root) => Array.from((root || document).querySelectorAll(sel)),
    el(tag, attrs, children) {
      const node = document.createElement(tag);
      for (const k in (attrs || {})) {
        if (k === 'class') node.className = attrs[k];
        else if (k === 'text') node.textContent = attrs[k];
        else if (k === 'html') node.innerHTML = attrs[k];
        else if (k === 'style') node.setAttribute('style', attrs[k]);
        else if (k.startsWith('on')) node.addEventListener(k.slice(2), attrs[k]);
        else if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]);
      }
      (children || []).forEach((c) => node.appendChild(c));
      return node;
    },
    escape: (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  };

  // ---------- fetch wrapper that always gives you parsed JSON ----------
  TW.api = async function (path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string' && !(opts.body instanceof Blob)) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) {
      const err = new Error(data.error || ('request failed: ' + res.status));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  // ---------- toast ----------
  let toastTimer = null;
  TW.toast = function (message, kind) {
    let node = document.getElementById('toast');
    if (!node) {
      node = TW.dom.el('div', { id: 'toast', class: 'toast' });
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.className = 'toast show ' + (kind || '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('show'), 2600);
  };

  // ---------- clipboard ----------
  TW.copy = async function (text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = TW.dom.el('textarea', { style: 'position:fixed;opacity:0' });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    }
  };

  // ---------- allowance meter ----------
  // One place that knows how to render "how many pixels do I have left",
  // so the canvas and the accounts panel cannot disagree.
  TW.paintMeter = function (state) {
    if (!state) return;
    TW.state.allowance = state;
    const bar = document.getElementById('meterBar');
    const text = document.getElementById('meterText');
    if (!bar || !text) return;

    const pct = state.allowed ? Math.min(100, (state.used / state.allowed) * 100) : 0;
    bar.style.width = pct + '%';
    bar.className = 'meter-bar' + (state.left === 0 ? ' spent' : '');

    let msg = state.left + ' / ' + state.allowed + ' pixels left today';
    if (state.credits > 0) msg += ' · ' + state.credits + ' credit' + (state.credits === 1 ? '' : 's') + ' in reserve';
    if (state.cooldown > 0) msg += ' · ready in ' + state.cooldown + 's';
    text.textContent = msg;
  };

  TW.mountMeter = function () {
    const wrap = document.getElementById('meter');
    if (wrap) wrap.style.display = 'flex';
  };
})(window.TW);
