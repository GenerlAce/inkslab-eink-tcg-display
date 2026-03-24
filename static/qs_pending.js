// qs_pending.js — Quick Switch pending banner and button badges
(function() {
  'use strict';

  var WINDOW = 180;
  var _sbBanner = null;
  var _mobBanner = null;
  var _currentTcg = null;

  // --- Build a banner element ---
  function makeBanner(id) {
    var d = document.createElement('div');
    d.className = 'qs-pending-banner';
    d.id = id;
    d.innerHTML = [
      '<div class="qs-pb-row">',
        '<span class="qs-pb-dot"></span>',
        '<span class="qs-pb-text"></span>',
      '</div>',
      '<div class="qs-pb-sub"></div>',
      '<div class="qs-pb-track"><div class="qs-pb-bar"></div></div>'
    ].join('');
    return d;
  }

  // --- Inject banners into the DOM ---
  function init() {
    // Desktop: right after the sidebar brand header (visible on all tabs)
    var brand = document.querySelector('.sidebar-brand');
    if (brand && brand.parentNode) {
      _sbBanner = makeBanner('qs-pending-banner-sb');
      brand.parentNode.insertBefore(_sbBanner, brand.nextSibling);
    }
    // Mobile: below the status pill
    var pill = document.querySelector('.status-pill');
    if (pill && pill.parentNode) {
      _mobBanner = makeBanner('qs-pending-banner-mob');
      pill.parentNode.insertBefore(_mobBanner, pill.nextSibling);
    }
  }

  // --- Helpers ---
  function applyContent(banner, name, color, currentName) {
    if (!banner) return;
    banner.style.setProperty('--qs-color', color);
    var dot  = banner.querySelector('.qs-pb-dot');
    var text = banner.querySelector('.qs-pb-text');
    var sub  = banner.querySelector('.qs-pb-sub');
    if (dot)  dot.style.background = color;
    if (text) { text.textContent = 'Switching to ' + name + '\u2026'; text.style.color = color; }
    if (sub)  sub.textContent = 'Fires at next card interval \u2014 or cancel to stay on ' + (currentName || 'current');
  }

  function setBar(banner, pct) {
    if (!banner) return;
    var bar = banner.querySelector('.qs-pb-bar');
    if (bar) bar.style.width = Math.max(0, pct) + '%';
  }

  function setPendingBadge(tcg, show) {
    ['#quick-switch-btns', '#sb-quick-switch-btns'].forEach(function(sel) {
      var container = document.querySelector(sel);
      if (!container) return;
      container.querySelectorAll('.btn').forEach(function(b) {
        var existing = b.querySelector('.qs-pending-badge');
        if (existing) existing.remove();
        if (show && b.dataset.tcg === tcg) {
          var badge = document.createElement('span');
          badge.className = 'qs-pending-badge';
          badge.textContent = 'pending';
          b.appendChild(badge);
        }
      });
    });
  }

  // --- Public API ---
  window._qsPendingShow = function(label, meta) {
    if (!meta || !meta.tcg) return; // only handle quick-switch actions
    _currentTcg = meta.tcg;
    var color = meta.color || '#36A5CA';
    var name  = meta.name  || meta.tcg;

    var currentInfo = window._tcgRegistry && window._lastStatus &&
                      window._tcgRegistry[window._lastStatus.tcg];
    var currentName = (currentInfo && currentInfo.name) || 'current collection';

    var rem = window._CooldownGate ? _CooldownGate.remaining() : WINDOW;
    var pct = (rem / WINDOW) * 100;

    [_sbBanner, _mobBanner].forEach(function(b) {
      if (!b) return;
      applyContent(b, name, color, currentName);
      setBar(b, pct);
      b.classList.add('visible');
    });

    setPendingBadge(_currentTcg, true);
  };

  window._qsPendingUpdate = function(rem) {
    var pct = (rem / WINDOW) * 100;
    setBar(_sbBanner,  pct);
    setBar(_mobBanner, pct);
  };

  window._qsPendingHide = function() {
    [_sbBanner, _mobBanner].forEach(function(b) {
      if (b) b.classList.remove('visible');
    });
    setPendingBadge(_currentTcg, false);
    _currentTcg = null;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 100);
  }
})();
