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
  TW.renderHooks = [];
  TW.state = { messages: [], me: null, viewers: 0 };

  // Run a callback after every wall re-render. Features that decorate
  // messages (report buttons, highlighting) register here instead of
  // polling the DOM.
  TW.onRender = function (fn) {
    TW.renderHooks.push(fn);
  };

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

  // ---------- encryption ----------
  // One shared key for the whole wall: everyone reads and writes the same
  // messages. The server only ever sees ciphertext.
  const KEY_STRING = 'txtwall-shared-key-v1';
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  let keyPromise = null;
  function getKey() {
    if (!keyPromise) {
      keyPromise = crypto.subtle
        .digest('SHA-256', enc.encode(KEY_STRING))
        .then((digest) => crypto.subtle.importKey('raw', digest, 'AES-GCM', false, ['encrypt', 'decrypt']));
    }
    return keyPromise;
  }

  const b64 = (u8) => btoa(String.fromCharCode.apply(null, u8));
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

  TW.crypto = {
    async encrypt(text) {
      const key = await getKey();
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(text));
      return { ct: b64(new Uint8Array(ct)), iv: b64(iv) };
    },
    async decrypt(ctB64, ivB64) {
      const key = await getKey();
      const pt = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: unb64(ivB64) }, key, unb64(ctB64)
      );
      return dec.decode(pt);
    }
  };
})(window.TW);
