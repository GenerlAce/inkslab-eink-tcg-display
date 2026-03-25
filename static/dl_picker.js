// Download source picker — pill selector + action buttons
(function() {
  var _dlTcg = null;
  var _dlRegistry = {};

  var SEARCH_PANELS = {
    lorcana: 'dl-lorcana-search',
    mtg:     'dl-mtg-search',
    pokemon: 'dl-pokemon-search',
    manga:   'dl-manga-search',
    comics:  'dl-comics-search'
  };
  var SEARCH_LABELS = {
    lorcana: 'Search Sets',
    mtg:     'Search Sets',
    pokemon: 'Search Sets',
    manga:   'Search Series',
    comics:  'Search Series'
  };
  var SHORT_NAMES = {
    comics:  'Comics',
    lorcana: 'Disney Lorcana',
    mtg:     'Magic: The Gathering',
    manga:   'Manga',
    pokemon: 'Pok\u00e9mon'
  };
  var ACCENT_COLORS = {
    comics:  '#f97316',
    lorcana: '#a855f7',
    mtg:     '#2dd4bf',
    manga:   '#ec4899',
    pokemon: '#22d3ee'
  };

  function closeDlDropdown() {
    var dd  = document.getElementById('dl-source-dd');
    var btn = document.getElementById('dl-source-pill-btn');
    if (dd)  dd.style.display = 'none';
    if (btn) btn.classList.remove('open');
  }

  function updateDlPill(tcg) {
    var info  = _dlRegistry[tcg];
    if (!info) return;
    var color = ACCENT_COLORS[tcg] || info.color || '#36A5CA';
    var btn   = document.getElementById('dl-source-pill-btn');
    if (!btn) return;
    btn.style.borderColor = color;
    btn.style.color       = color;
    btn.style.boxShadow   = '0 0 0 2px ' + color + '33';
    var dot = btn.querySelector('.source-dot');
    var lbl = btn.querySelector('.dl-pill-label');
    if (dot) dot.style.background = color;
    if (lbl) { lbl.textContent = SHORT_NAMES[tcg] || info.name; lbl.style.color = color; }
    document.querySelectorAll('.dl-dd-item').forEach(function(el) {
      el.classList.toggle('active', el.dataset.tcg === tcg);
    });
  }

  function updateDlActionBtns(tcg) {
    var info     = _dlRegistry[tcg];
    if (!info) return;
    var color    = info.color || '#36A5CA';
    var panelId  = SEARCH_PANELS[tcg];
    var sLabel   = SEARCH_LABELS[tcg] || 'Search';

    var dlBtn = document.querySelector('[data-dl-btn]');
    if (dlBtn) {
      dlBtn.style.color       = color;
      dlBtn.style.borderColor = color;
      dlBtn.dataset.tcg       = tcg;
    }
    var sBtn = document.querySelector('[data-search-btn]');
    if (sBtn) {
      sBtn.style.background  = color;
      sBtn.dataset.panelId   = panelId || '';
      sBtn.dataset.color     = color;
      sBtn.textContent       = sLabel;
      sBtn.style.display     = panelId ? '' : 'none';
    }
  }

  function setDlTcg(tcg) {
    _dlTcg = tcg;
    closeDlDropdown();
    updateDlPill(tcg);
    updateDlActionBtns(tcg);
    if (window.closeAllDlSearch) closeAllDlSearch();
  }

  window.setDlTcg = setDlTcg;

  window.initDlPicker = function(sorted, activeTcg) {
    var dlSorted = sorted.filter(function(e) { return e[1].download_script; });
    if (!dlSorted.length) return;

    sorted.forEach(function(e) { _dlRegistry[e[0]] = e[1]; });

    var container = document.getElementById('dl-picker');
    if (!container) return;
    container.innerHTML = '';

    // --- Pill selector ---
    var picker = document.createElement('div');
    picker.className = 'source-picker';

    var pillBtn = document.createElement('button');
    pillBtn.id        = 'dl-source-pill-btn';
    pillBtn.className = 'dl-pill-btn';
    pillBtn.type      = 'button';

    var dot = document.createElement('span');
    dot.className = 'source-dot';
    pillBtn.appendChild(dot);

    var lbl = document.createElement('span');
    lbl.className = 'dl-pill-label';
    pillBtn.appendChild(lbl);

    var chev = document.createElement('span');
    chev.className   = 'source-pill-chevron';
    chev.textContent = '\u25BC';
    pillBtn.appendChild(chev);

    // --- Dropdown ---
    var dd = document.createElement('div');
    dd.id        = 'dl-source-dd';
    dd.className = 'source-dd';
    dd.style.display = 'none';

    dlSorted.forEach(function(e) {
      var tcg   = e[0];
      var info  = e[1];
      var color = info.color || '#36A5CA';
      var item  = document.createElement('div');
      item.className    = 'dl-dd-item source-dd-item';
      item.dataset.tcg  = tcg;

      var idot = document.createElement('span');
      idot.className         = 'source-dot';
      idot.style.background  = color;
      item.appendChild(idot);
      item.appendChild(document.createTextNode(SHORT_NAMES[tcg] || info.name));
      item.addEventListener('click', function() { setDlTcg(tcg); });
      dd.appendChild(item);
    });

    pillBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (dd.style.display !== 'none') { closeDlDropdown(); }
      else { dd.style.display = 'block'; pillBtn.classList.add('open'); }
    });
    document.addEventListener('click', function(e) {
      if (!picker.contains(e.target)) closeDlDropdown();
    });

    picker.appendChild(pillBtn);
    picker.appendChild(dd);
    container.appendChild(picker);

    // --- Action buttons ---
    var actionRow = document.createElement('div');
    actionRow.id       = 'dl-action-btns';
    actionRow.style.cssText = 'display:flex;gap:8px;margin-top:8px;';

    var dlBtn = document.createElement('button');
    dlBtn.className = 'btn btn-block';
    dlBtn.setAttribute('data-dl-btn', '1');
    dlBtn.style.cssText = 'background:transparent;border:1px solid;flex:1;font-weight:600;';
    dlBtn.textContent   = 'Download All';
    dlBtn.addEventListener('click', function() { if (_dlTcg && window.startDownload) startDownload(_dlTcg); });

    var sBtn = document.createElement('button');
    sBtn.className = 'btn';
    sBtn.setAttribute('data-search-btn', '1');
    sBtn.style.cssText = 'color:#010001;border:none;white-space:nowrap;padding:8px 16px;font-weight:600;flex:1;';
    sBtn.addEventListener('click', function() {
      var panelId = sBtn.dataset.panelId;
      if (panelId && window.toggleDlSearch) toggleDlSearch(panelId, sBtn);
    });

    actionRow.appendChild(dlBtn);
    actionRow.appendChild(sBtn);
    container.appendChild(actionRow);

    // Init with active TCG if it has a download script, else first option
    var defaultTcg = (activeTcg && _dlRegistry[activeTcg] && _dlRegistry[activeTcg].download_script)
      ? activeTcg : dlSorted[0][0];
    setDlTcg(defaultTcg);
  };
})();
