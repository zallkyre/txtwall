/* Pixel credits: the balance, what it did, and buying more.
 *
 * Buying is off until a Stripe account exists (they require an 18+
 * holder), so the buy button only appears when the server says payments
 * are enabled. The rest of this works today: reporting abuse earns
 * credits, and the owner can /grant them from Discord.
 */
TW.feature('credits', {
  mount() {
    const box = document.getElementById('creditsBox');
    if (!box) return;

    const buyRow = document.getElementById('buyRow');
    const earnNote = document.getElementById('earnNote');
    if (TW.config.payments_enabled) {
      buyRow.style.display = 'block';
    } else {
      earnNote.textContent =
        'reports the owner agrees with earn you ' + (TW.config.reward || 25) + ' pixels.';
    }

    async function refresh() {
      try {
        const data = await TW.api('/api/credits');
        if (!data.logged_in) {
          document.getElementById('balance').textContent = '—';
          document.getElementById('ledger').textContent = 'sign in to see your balance';
          return;
        }
        document.getElementById('balance').textContent = data.balance;
        const list = document.getElementById('ledger');
        if (!data.ledger.length) {
          list.textContent = 'no credits yet';
          return;
        }
        list.innerHTML = data.ledger.slice(0, 6).map((c) =>
          '<li><span>' + c.kind + '</span><span>+' + c.amount + '</span>' +
          '<span class="left">' + c.remaining + ' left</span></li>'
        ).join('');
      } catch (e) { /* leave the previous text alone */ }
    }

    if (TW.config.payments_enabled && TW.config.credit_packs.length) {
      const row = document.getElementById('packRow');
      TW.config.credit_packs.forEach((pack) => {
        const b = TW.dom.el('button', {
          class: 'btn-sm', text: pack.label + ' · ' + (TW.config.credit_prices[pack.id] || '?')
        });
        b.onclick = async () => {
          const me = TW.state.me;
          if (!me || !me.logged_in) { TW.toast('sign in first'); return; }
          try {
            const res = await TW.api('/api/payments/checkout', {
              method: 'POST', body: { pack_id: pack.id, username: me.username }
            });
            location.href = res.url;
          } catch (e) { TW.toast(e.message); }
        };
        row.appendChild(b);
      });
    }

    refresh();
    TW.state.refreshCredits = refresh;
  }
});
