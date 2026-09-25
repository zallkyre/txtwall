/* Feature: the message wall — render, post, attach images, poll. */
(function (TW) {
  'use strict';

  const $ = TW.dom.$;
  const esc = TW.dom.escape;

  let input, postbtn, wall, composer, imgBtn, imgPreview, upgrade;
  let pendingImage = null;
  let pollTimer = null;

  function canPost() {
    return input.value.trim().length > 0 || !!pendingImage;
  }

  function refreshButton() {
    postbtn.disabled = !canPost();
  }

  // ---------- rendering ----------
  function timeOf(created) {
    return new Date(created * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function cardHTML(m) {
    const reacts = Object.entries(m.reactions || {}).map(([e, n]) =>
      `<button class="react" data-action="react" data-id="${m.id}" data-emoji="${esc(e)}">${esc(e)}<span class="n">${n}</span></button>`
    ).join('');
    const addReact = `<button class="react react-add" data-action="react-add" data-id="${m.id}">+</button>`;
    return `<div class="msg" data-id="${m.id}">` +
      (m.text ? `<div class="text">${esc(m.text)}</div>` : '') +
      (m.image ? `<img src="/uploads/${m.image}" loading="lazy" alt="image">` : '') +
      `<div class="meta">` +
        `<button class="id-link" data-action="link" data-id="${m.id}" title="copy link to this message">#${m.id}</button>` +
        `<span>${m.time}</span>` +
      `</div>` +
      `<div class="reacts">${reacts}${addReact}</div>` +
    `</div>`;
  }

  async function refresh() {
    try {
      const data = await TW.api('/api/messages');
      const tail = data[data.length - 1];
      const viewers = tail && tail.viewers !== undefined ? data.pop().viewers : 0;
      TW.state.viewers = viewers;
      const vnode = $('#viewerCount');
      if (vnode) vnode.textContent = viewers;

      const all = [];
      for (const m of data) {
        let text = '';
        if (m.ct) {
          try { text = await TW.crypto.decrypt(m.ct, m.iv); }
          catch (e) { continue; }  // encrypted with an older key: skip
        }
        all.push({ id: m.id, text: text, time: timeOf(m.created_at), image: m.image, reactions: m.reactions || {} });
      }
      TW.state.messages = all;

      if (!all.length) {
        wall.innerHTML = '<div class="empty">nothing here yet. post the first message.</div>';
        return;
      }
      wall.innerHTML = all.map(cardHTML).join('');
      TW.renderHooks.forEach((fn) => {
        try { fn(wall); } catch (e) { console.error(e); }
      });
      if (TW.search) TW.search.apply();
      if (TW.permalink) TW.permalink.apply();
    } catch (e) {
      console.error(e);
    }
  }

  // ---------- posting ----------
  function setImage(file) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { TW.toast('that is not an image', 'err'); return; }
    const max = (TW.config.max_image_bytes || 5242880) / 1048576;
    if (file.size > TW.config.max_image_bytes) { TW.toast('image too large (max ' + max + 'MB)', 'err'); return; }
    pendingImage = file;
    imgPreview.src = URL.createObjectURL(file);
    imgPreview.classList.add('show');
    refreshButton();
  }

  async function post() {
    const text = input.value.trim();
    if (!text && !pendingImage) return;
    postbtn.disabled = true;
    try {
      if (pendingImage) {
        const res = await fetch('/api/post/image', { method: 'POST', body: pendingImage });
        if (!res.ok) {
          const j = await res.json().catch(() => ({}));
          TW.toast(j.error || 'image rejected', 'err');
          refreshButton();
          return;
        }
        pendingImage = null;
        imgPreview.classList.remove('show');
        imgPreview.src = '';
      }
      if (text) {
        const { ct, iv } = await TW.crypto.encrypt(text);
        try {
          await TW.api('/api/post', { method: 'POST', body: { ct: ct, iv: iv } });
        } catch (e) {
          if (e.status === 429 && (e.data.error || '').includes('limit')) upgrade.classList.add('show');
          TW.toast(e.message, 'err');
          refreshButton();
          return;
        }
      }
      input.value = '';
      refreshButton();
      if (TW.search) TW.search.apply();
      await refresh();
      if (TW.accounts) await TW.accounts.refreshMe();
    } catch (e) {
      console.error(e);
      refreshButton();
    }
  }

  TW.feature('wall', {
    title: 'Message wall',
    mount() {
      input = $('#input');
      postbtn = $('#postbtn');
      wall = $('#wall');
      imgBtn = $('#imgBtn');
      imgPreview = $('#imgPreview');
      composer = $('#composer');
      upgrade = $('#upgrade');

      // char counter, from the server config
      const maxLen = TW.config.max_text_len || 500;
      input.setAttribute('maxlength', maxLen);
      const count = $('#charCount');
      const syncCount = () => {
        const n = input.value.length;
        count.textContent = n + '/' + maxLen;
        count.className = 'count' + (n >= maxLen ? ' full' : (n > maxLen * 0.8 ? ' warn' : ''));
        refreshButton();
      };
      input.addEventListener('input', syncCount);
      syncCount();

      postbtn.addEventListener('click', post);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); post(); }
      });

      // image: picker, paste, drag
      imgBtn.addEventListener('click', () => {
        const f = document.createElement('input');
        f.type = 'file';
        f.accept = 'image/*';
        f.onchange = () => setImage(f.files[0]);
        f.click();
      });
      document.addEventListener('paste', (e) => {
        const items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        for (const item of items) {
          if (item.type.startsWith('image/')) {
            const file = item.getAsFile();
            if (file) { setImage(file); e.preventDefault(); return; }
          }
        }
      });
      ['dragenter', 'dragover'].forEach((ev) => composer.addEventListener(ev, (e) => {
        e.preventDefault(); composer.classList.add('drag');
      }));
      ['dragleave', 'drop'].forEach((ev) => composer.addEventListener(ev, (e) => {
        e.preventDefault(); composer.classList.remove('drag');
      }));
      composer.addEventListener('drop', (e) => {
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) setImage(file);
      });

      refresh();
      pollTimer = setInterval(refresh, 5000);
    }
  });

  TW.wall = { refresh: refresh, post: post };
})(window.TW);
