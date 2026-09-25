/* Account panel: sign in, sign up, see what it buys you.
 *
 * Signup is rate limited to one account per IP per week, so the error
 * from the server is shown verbatim — the wait time is useful.
 */
TW.feature('accounts', {
  mount() {
    const tab = document.getElementById('acctTab');
    const panel = document.getElementById('panel');
    const authRow = document.getElementById('authRow');
    const info = document.getElementById('authInfo');
    const err = document.getElementById('errBox');
    const user = document.getElementById('user');
    const pass = document.getElementById('pass');
    const loginBtn = document.getElementById('loginBtn');
    const signupBtn = document.getElementById('signupBtn');
    const turnstileBox = document.getElementById('turnstileBox');
    if (!tab) return;

    let turnstileWidget = null;

    function say(text, bad) {
      if (!err) return;
      err.textContent = text;
      err.style.display = text ? 'block' : 'none';
      err.className = bad ? 'err bad' : 'err good';
    }

    function panelOpen(open) {
      panel.classList.toggle('open', open);
      tab.classList.toggle('on', open);
    }

    tab.addEventListener('click', () => panelOpen(!panel.classList.contains('open')));

    // Cloudflare Turnstile, only if keys are configured server-side
    const siteKey = TW.config.turnstile_site_key;
    if (siteKey && turnstileBox && window.turnstile) {
      turnstileBox.style.display = 'block';
      turnstileWidget = window.turnstile.render(turnstileBox, {
        sitekey: siteKey, theme: 'dark', size: 'flexible'
      });
    }

    async function refresh() {
      try {
        const me = await TW.api('/api/me');
        TW.state.me = me;
        TW.paintMeter(me.state);

        if (me.logged_in) {
          authRow.style.display = 'none';
          info.style.display = 'block';
          info.innerHTML =
            '<b>' + TW.dom.escape(me.username) + '</b>' +
            '<span class="acct-num">' + TW.dom.escape(me.account_number) + '</span>' +
            '<span class="acct-note">' + me.state.base + ' pixels a day, plus any credits</span>' +
            '<div class="acct-actions">' +
            '<button class="btn-sm btn-ghost" id="permBtn">' +
            (me.permanent ? 'unlock number' : 'keep my number') + '</button>' +
            '<button class="btn-sm btn-ghost" id="logoutBtn">log out</button></div>';

          document.getElementById('logoutBtn').onclick = async () => {
            await TW.api('/api/logout', { method: 'POST' });
            TW.toast('logged out');
            refresh();
          };
          document.getElementById('permBtn').onclick = async (e) => {
            await TW.api('/api/account/permanent', {
              method: 'POST', body: { permanent: !me.permanent }
            });
            e.target.textContent = me.permanent ? 'keep my number' : 'unlock number';
            TW.toast(me.permanent ? 'your number now rotates on each login' : 'your number is fixed');
          };
        } else {
          authRow.style.display = 'flex';
          info.style.display = 'none';
        }
      } catch (e) { /* the panel just stays as it is */ }
    }

    loginBtn.onclick = async () => {
      say('');
      try {
        const res = await TW.api('/api/login', {
          method: 'POST', body: { username: user.value, password: pass.value }
        });
        pass.value = '';
        TW.toast('welcome back, ' + res.username);
        refresh();
      } catch (e) { say(e.message, true); }
    };

    signupBtn.onclick = async () => {
      say('');
      const body = {
        username: user.value, password: pass.value,
        turnstile_token: turnstileWidget ? window.turnstile.getResponse(turnstileWidget) : ''
      };
      try {
        const res = await TW.api('/api/signup', { method: 'POST', body });
        pass.value = '';
        TW.toast('account made — ' + res.daily_pixels + ' pixels a day');
        if (turnstileWidget) window.turnstile.reset(turnstileWidget);
        refresh();
      } catch (e) {
        say(e.message, true);
        if (turnstileWidget) window.turnstile.reset(turnstileWidget);
      }
    };

    [user, pass].forEach((el) => el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loginBtn.click();
    }));

    refresh();
  }
});
