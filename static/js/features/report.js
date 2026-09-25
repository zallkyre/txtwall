/* Feature: report a pixel to the owner.
 *
 * The visitor never sees an email address — the server forwards the report
 * to the Cloudflare mail worker, which emails the owner and pings Discord.
 * If delivery fails, the dialog offers the address as a fallback.
 *
 * A report the owner agrees with pays the reporter in credits, so this is
 * one of the two ways to earn pixels without any payment processor.
 */
(function (TW) {
  'use strict';

  let back, reasonBox, submitBtn, current = null;

  function close() {
    back.classList.remove('open');
    current = null;
    reasonBox.value = '';
  }

  async function submit() {
    if (!current) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'sending...';
    try {
      await TW.api('/api/report', {
        method: 'POST',
        body: { x: current.x, y: current.y, reason: reasonBox.value.trim() }
      });
      close();
      TW.toast('reported — if the owner agrees, this earns you pixels', 'ok');
      if (TW.state.refreshCredits) TW.state.refreshCredits();
    } catch (e) {
      const fallback = e.data && e.data.fallback_email;
      TW.toast(fallback ? 'could not send — email ' + fallback : e.message, 'err');
      submitBtn.disabled = false;
      submitBtn.textContent = 'send report';
    }
  }

  TW.feature('report', {
    title: 'Report a pixel',
    mount() {
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
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && back.classList.contains('open')) close();
      });

      // the canvas dispatches this when a pixel is picked for reporting
      document.addEventListener('tw:report', (e) => {
        current = e.detail;
        document.getElementById('reportId').textContent = current.x + ',' + current.y;
        reasonBox.value = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'send report';
        back.classList.add('open');
        reasonBox.focus();
      });

      // holding R while clicking a pixel opens this dialog
      document.getElementById('reportHint').addEventListener('click', () => {
        TW.toast('press R then click a pixel to report it');
      });
    }
  });
})(window.TW);
