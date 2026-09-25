/* Feature: Discord widget toggle. */
(function (TW) {
  'use strict';

  TW.feature('discord', {
    title: 'Discord widget',
    always: true,
    mount() {
      const fab = document.getElementById('discordFab');
      const pop = document.getElementById('discordPop');
      fab.addEventListener('click', () => pop.classList.toggle('open'));
      document.getElementById('discordClose').addEventListener('click', () => pop.classList.remove('open'));
    }
  });
})(window.TW);
