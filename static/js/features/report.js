/* Feature: report a message to the owner.
 *
 * The visitor never sees an email address or a mail client — the server
 * forwards the report to the Cloudflare mail worker, which emails the
 * owner and pings Discord. If delivery fails, the dialog offers the
 * address as a fallback.
 */
(function (TW) {
  'use strict';

  let back, reasonBox, submitBtn, currentId = null;

  function close() {
    back.classList.remove('open');
    currentId = null;
    reasonBox.value = '';
  }

  async function submit() {
    if (!currentId) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'sending...';
    try {
      await TW.api('/api/report', {
        method: 'POST',
        body: { message_id: currentId, reason: reasonBox.value.trim() }
      });
      close();
      TW.toast('reported. the owner has been notified.', 'ok');
    } catch (e) {
      const fallback = e.data && e.data.fallback_email;
      TW.toast(fallback ? 'could not send — email ' + fallback : e.message, 'err');
      submitBtn.disabled = false;
      submitBtn.textContent = 'send report';
    }
  }

  function addReportButton(card, id) {
    if (!card.querySelector('[data-action="report"]')) {
      const btn = TW.dom.el('button', {
        class: 'react report',
        'data-action': 'report',
        'data-id': id,
        title: 'report this message to the owner',
        text: 'report'
      });
      const reacts = card.querySelector('.reacts');
      (reacts || card).appendChild(btn);
    }
  }

  TW.feature('report', {
    title: 'Report a message',
    mount() {
      // register the render hook first: a missing element below must not
      // stop report buttons from being attached
      TW.onRender((wall) => {
        wall.querySelectorAll('.msg').forEach((c) => addReportButton(c, c.dataset.id));
      });

      back = document.getElementById('reportBack');
      reasonBox = document.getElementById('reportReason');
      submitBtn = document.getElementById('reportSubmit');
      if (!back || !reasonBox || !submitBtn) {
        console.error('report: dialog markup missing');
        return;
      }

      document.getElementById('reportCancel').addEventListener('click', close);
      submitBtn.addEventListener('click', submit);
      back.addEventListener('click', (e) => { if (e.target === back) close(); });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && back.classList.contains('open')) close(); });

      document.getElementById('wall').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action="report"]');
        if (!btn) return;
        currentId = parseInt(btn.dataset.id, 10);
        document.getElementById('reportId').textContent = '#' + currentId;
        reasonBox.value = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'send report';
        back.classList.add('open');
        reasonBox.focus();
      });
    }
  });
})(window.TW);
