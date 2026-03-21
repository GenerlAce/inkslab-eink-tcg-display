// Mobile Quick Switch Collection — bottom sheet + cooldown toast
(function() {
  var _sheet   = null;
  var _overlay = null;
  var _toast   = null;
  var _SHORT   = {lorcana:'Lorcana', mtg:'Magic', pokemon:'Pokemon', manga:'Manga', comics:'Comics', custom:'Custom'};

  function closeSheet() {
    if (_sheet)   _sheet.classList.remove('mqs-open');
    if (_overlay) _overlay.classList.remove('mqs-open');
  }
  function openSheet() {
    if (_sheet)   _sheet.classList.add('mqs-open');
    if (_overlay) _overlay.classList.add('mqs-open');
  }

  function buildOverlayAndSheet() {
    _overlay = document.createElement('div');
    _overlay.className = 'mqs-overlay';
    _overlay.addEventListener('click', closeSheet);

    _sheet = document.createElement('div');
    _sheet.className = 'mqs-sheet';

    var handle = document.createElement('div');
    handle.className = 'mqs-handle';

    var title = document.createElement('div');
    title.className = 'mqs-sheet-title';
    title.textContent = 'Quick Switch Collection';

    var grid = document.createElement('div');
    grid.className = 'mqs-grid';
    grid.id = 'mqs-grid';

    _sheet.appendChild(handle);
    _sheet.appendChild(title);
    _sheet.appendChild(grid);
    document.body.appendChild(_overlay);
    document.body.appendChild(_sheet);
  }

  function buildTrigger() {
    var qsEl = document.getElementById('quick-switch-btns');
    if (!qsEl) return;
    qsEl.innerHTML = '';

    var btn = document.createElement('button');
    btn.id        = 'mqs-trigger';
    btn.className = 'btn mqs-trigger';
    btn.type      = 'button';

    var dot = document.createElement('span');
    dot.className = 'source-dot mqs-trigger-dot';
    btn.appendChild(dot);

    var lbl = document.createElement('span');
    lbl.className = 'mqs-trigger-lbl';
    lbl.textContent = 'Select Collection';
    btn.appendChild(lbl);

    var chev = document.createElement('span');
    chev.className   = 'mqs-chev';
    chev.textContent = '\u25B2';
    btn.appendChild(chev);

    btn.addEventListener('click', openSheet);
    qsEl.appendChild(btn);
  }

  function populateGrid(sorted) {
    var grid = document.getElementById('mqs-grid');
    if (!grid) return;
    grid.innerHTML = '';
    sorted.forEach(function(e) {
      var tcg   = e[0];
      var info  = e[1];
      var color = info.color || '#36A5CA';
      var b = document.createElement('button');
      b.className       = 'btn mqs-grid-btn';
      b.dataset.tcg     = tcg;
      b.dataset.color   = color;
      b.style.cssText   = 'background:transparent;color:' + color + ';border:1px solid ' + color + ';';
      b.textContent     = _SHORT[tcg] || info.name;
      b.addEventListener('click', function() {
        closeSheet();
        if (window.switchTCG) switchTCG(tcg, b);
      });
      grid.appendChild(b);
    });
  }

  function updateTrigger(tcg) {
    var btn = document.getElementById('mqs-trigger');
    if (!btn) return;
    var info  = window._tcgRegistry && window._tcgRegistry[tcg];
    var color = (info && info.color) || '#36A5CA';
    var dot   = btn.querySelector('.mqs-trigger-dot');
    var lbl   = btn.querySelector('.mqs-trigger-lbl');
    if (dot) dot.style.background = color;
    if (lbl) lbl.textContent = _SHORT[tcg] || (info && info.name) || tcg;
    btn.style.borderColor = color;
    btn.style.color       = color;
    // Mirror active state in sheet grid
    var grid = document.getElementById('mqs-grid');
    if (!grid) return;
    grid.querySelectorAll('.mqs-grid-btn').forEach(function(b) {
      var c = b.dataset.color || '#36A5CA';
      if (b.dataset.tcg === tcg) {
        b.style.background = c;
        b.style.color      = 'var(--bg)';
      } else {
        b.style.background = 'transparent';
        b.style.color      = c;
      }
    });
  }

  function showCooldownToast(tcg, remaining) {
    if (_toast) { _toast.remove(); _toast = null; }
    var info = window._tcgRegistry && window._tcgRegistry[tcg];
    var name = (info && info.name) || tcg.toUpperCase();
    _toast = document.createElement('div');
    _toast.className = 'mqs-cooldown-toast';
    _toast.innerHTML =
      '<span class="mqs-toast-msg">Display refreshes in ~' + remaining + 's. Switch to ' + name + ' now anyway?</span>' +
      '<div class="mqs-toast-btns">' +
        '<button class="btn btn-sm btn-secondary mqs-toast-cancel">Cancel</button>' +
        '<button class="btn btn-sm mqs-toast-confirm">Switch Anyway</button>' +
      '</div>';
    _toast.querySelector('.mqs-toast-cancel').addEventListener('click', function() {
      if (_toast) { _toast.remove(); _toast = null; }
    });
    _toast.querySelector('.mqs-toast-confirm').addEventListener('click', function() {
      if (_toast) { _toast.remove(); _toast = null; }
      if (window._doSwitchTCG) window._doSwitchTCG(tcg);
    });
    document.body.appendChild(_toast);
    requestAnimationFrame(function() {
      requestAnimationFrame(function() { if (_toast) _toast.classList.add('mqs-toast-in'); });
    });
    setTimeout(function() {
      if (_toast) {
        _toast.classList.remove('mqs-toast-in');
        setTimeout(function() { if (_toast) { _toast.remove(); _toast = null; } }, 300);
      }
    }, 12000);
  }

  window.initMobileQS = function(sorted) {
    var qsEl = document.getElementById('quick-switch-btns');
    if (!qsEl || qsEl.offsetParent === null) return; // not visible on desktop
    buildOverlayAndSheet();
    buildTrigger();
    populateGrid(sorted);
    window._mobileQSHook     = updateTrigger;
    window._mobileQSCooldown = showCooldownToast;
  };
})();
