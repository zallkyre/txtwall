/* Feature: accounts — optional, raises daily limits. */
(function (TW) {
  'use strict';

  const $ = TW.dom.$;
  const esc = TW.dom.escape;
  const LIMITS = (TW.config && TW.config.limits) || { user: { messages: 250, images: 50 } };

  let panel, acctTab, authRow, authInfo, authErr, userIn, passIn;

  function showErr(msg) {
    authErr.textContent = msg;
    authErr.style.display = 'block';
    setTimeout(() => { authErr.style.display = 'none'; }, 4000);
  }

  function render(me) {
    TW.state.me = me;
    const [mUsed, mMax] = me.quota ? me.quota.messages : [0, 0];
    const [iUsed, iMax] = me.quota ? me.quota.images : [0, 0];
    const qClass = mUsed >= mMax ? 'full' : (mUsed >= mMax * 0.8 ? 'warn' : '');
    const upgrade = $('#upgrade');

    if (!me.logged_in) {
      authRow.style.display = 'flex';
      acctTab.textContent = 'account';
      acctTab.classList.remove('logged');
      authInfo.innerHTML =
        '<span class="quota ' + qClass + '">anonymous — messages <b>' + mUsed + '/' + mMax +
        '</b> · images <b>' + iUsed + '/' + iMax + '</b> today</span><br>' +
        '<span class="info">log in or sign up for ' + LIMITS.user.messages +
        ' messages / ' + LIMITS.user.images + ' images a day.</span>';
      authInfo.style.display = 'block';
      if (mUsed >= mMax || iUsed >= iMax) upgrade.classList.add('show');
      else upgrade.classList.remove('show');
      return;
    }

    authRow.style.display = 'none';
    acctTab.textContent = me.username;
    acctTab.classList.add('logged');
    authInfo.innerHTML =
      '<b>' + esc(me.username) + '</b> — account #' + esc(me.account_number) +
      (me.permanent ? ' (permanent)' : ' (rotates on login)') + '<br>' +
      '<span class="quota ' + qClass + '">messages <b>' + mUsed + '/' + mMax +
      '</b> · images <b>' + iUsed + '/' + iMax + '</b> today</span><br>' +
      '<label class="perm-row"><input type="checkbox" id="permBox"' +
      (me.permanent ? ' checked' : '') + '> keep this account number permanent</label> ' +
      '<button class="btn-sm btn-ghost" id="logoutBtn">log out</button>';
    authInfo.style.display = 'block';
    upgrade.classList.remove('show');

    $('#permBox').addEventListener('change', async (e) => {
      await TW.api('/api/account/permanent', { method: 'POST', body: { permanent: e.target.checked } });
      refreshMe();
    });
    $('#logoutBtn').addEventListener('click', async () => {
      await TW.api('/api/logout', { method: 'POST' });
      refreshMe();
    });
  }

  async function refreshMe() {
    try {
      render(await TW.api('/api/me'));
    } catch (e) { console.error(e); }
  }

  async function doAuth(mode) {
    const username = userIn.value.trim();
    const password = passIn.value;
    if (!username || !password) { showErr('enter username and password'); return; }
    try {
      await TW.api('/api/' + mode, { method: 'POST', body: { username: username, password: password } });
      userIn.value = '';
      passIn.value = '';
      await refreshMe();
    } catch (e) { showErr(e.message); }
  }

  TW.feature('accounts', {
    title: 'Optional accounts',
    mount() {
      panel = $('#panel');
      acctTab = $('#acctTab');
      authRow = $('#authRow');
      authInfo = $('#authInfo');
      authErr = $('#authErr');
      userIn = $('#user');
      passIn = $('#pass');

      acctTab.addEventListener('click', () => panel.classList.toggle('open'));
      $('#upgradeBtn').addEventListener('click', () => {
        panel.classList.add('open');
        $('#upgrade').classList.remove('show');
      });
      $('#loginBtn').addEventListener('click', () => doAuth('login'));
      $('#signupBtn').addEventListener('click', () => doAuth('signup'));

      refreshMe();
      panel.classList.add('open');
    }
  });

  TW.accounts = { refreshMe: refreshMe };
})(window.TW);
