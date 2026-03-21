const API = '';

// --- CSRF: inject token into all POST fetches automatically ---
(function() {
  var _orig = window.fetch;
  window.fetch = function(url, opts) {
    opts = opts || {};
    if (opts.method && opts.method.toUpperCase() === 'POST') {
      opts.headers = opts.headers || {};
      if (!opts.headers['X-CSRF-Token']) {
        opts.headers['X-CSRF-Token'] = window.CSRF_TOKEN || '';
      }
    }
    return _orig.call(this, url, opts);
  };
})();

// --- Auth UI ---
function showAuthOverlay(setupMode) {
  var el = document.getElementById('auth-overlay');
  if (!el) return;
  document.getElementById('auth-setup-section').style.display = setupMode ? 'block' : 'none';
  document.getElementById('auth-login-section').style.display = setupMode ? 'none' : 'block';
  el.style.display = 'flex';
  setTimeout(function() {
    var inp = document.getElementById(setupMode ? 'setup-pin-input' : 'login-pin-input');
    if (inp) inp.focus();
  }, 100);
}

function hideAuthOverlay() {
  var el = document.getElementById('auth-overlay');
  if (el) el.style.display = 'none';
  document.body.classList.remove('auth-pending');
}

function submitLogin() {
  var pin = document.getElementById('login-pin-input').value.trim();
  var errEl = document.getElementById('login-error');
  errEl.textContent = '';
  fetch(API + '/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pin: pin})})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        window.CSRF_TOKEN = d.csrf_token || window.CSRF_TOKEN;
        hideAuthOverlay();
        initApp();
      } else {
        errEl.textContent = d.error || 'Incorrect PIN';
        document.getElementById('login-pin-input').value = '';
        document.getElementById('login-pin-input').focus();
      }
    }).catch(function() { errEl.textContent = 'Connection error'; });
}

function submitSetup(skip) {
  var pin = skip ? '' : document.getElementById('setup-pin-input').value.trim();
  var errEl = document.getElementById('setup-error');
  errEl.textContent = '';
  if (!skip && !pin) { errEl.textContent = 'Enter a PIN or click Skip'; return; }
  fetch(API + '/api/auth/setup', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pin: pin})})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        if (d.csrf_token) window.CSRF_TOKEN = d.csrf_token;
        hideAuthOverlay();
        initApp();
      } else {
        errEl.textContent = d.error || 'Setup failed';
      }
    }).catch(function() { errEl.textContent = 'Connection error'; });
}

function checkAuth(callback) {
  fetch(API + '/api/auth/status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.setup_done) {
        showAuthOverlay(true);  // first boot: prompt to set or skip PIN
      } else if (d.authenticated) {
        callback();
      } else {
        showAuthOverlay(false);  // PIN set, not logged in
      }
    }).catch(function() { callback(); });
}

// --- UI Themes ---
var THEMES = {
  'default': {
    '--bg-card': '#16303E', '--bg-panel': '#132E3E', '--bg-input': '#1F333F', '--border': '#1F333F',
    '--text': '#D8E6E4', '--text-dim': '#6BCCBD', '--text-hi': '#FCFDF0',
    '--accent': '#36A5CA', '--accent2': '#6BCCBD', '--border-hi': '#36A5CA44'
  },
  'lorcana': {
    '--bg-card': '#1A0B2E', '--bg-panel': '#130823', '--bg-input': '#211040', '--border': '#2D1554',
    '--text': '#E8D0F8', '--text-dim': '#C084FC', '--text-hi': '#F5EEFF',
    '--accent': '#C084FC', '--accent2': '#A855F7', '--border-hi': '#C084FC44'
  },
  'pokemon': {
    '--bg-card': '#0D1E2E', '--bg-panel': '#091629', '--bg-input': '#122035', '--border': '#1A3550',
    '--text': '#C8E8F8', '--text-dim': '#36A5CA', '--text-hi': '#E8F4FA',
    '--accent': '#36A5CA', '--accent2': '#5bbfe0', '--border-hi': '#36A5CA44'
  },
  'mtg': {
    '--bg-card': '#0E1E1C', '--bg-panel': '#091816', '--bg-input': '#132220', '--border': '#1C3330',
    '--text': '#C8E8E4', '--text-dim': '#6BCCBD', '--text-hi': '#E8F8F5',
    '--accent': '#6BCCBD', '--accent2': '#4db8a8', '--border-hi': '#6BCCBD44'
  },
  'manga': {
    '--bg-card': '#2A0F20', '--bg-panel': '#200B18', '--bg-input': '#33102A', '--border': '#401535',
    '--text': '#F8D0E8', '--text-dim': '#F472B6', '--text-hi': '#FFF0F8',
    '--accent': '#F472B6', '--accent2': '#EC4899', '--border-hi': '#F472B644'
  },
  'comics': {
    '--bg-card': '#2A1000', '--bg-panel': '#200C00', '--bg-input': '#301500', '--border': '#3D1800',
    '--text': '#F8DCC0', '--text-dim': '#F97316', '--text-hi': '#FFF4EC',
    '--accent': '#F97316', '--accent2': '#EA580C', '--border-hi': '#F9731644'
  },
  'custom': {
    '--bg-card': '#241600', '--bg-panel': '#1B1000', '--bg-input': '#2E1C00', '--border': '#392200',
    '--text': '#F8E8C0', '--text-dim': '#F59E0B', '--text-hi': '#FFF8E8',
    '--accent': '#F59E0B', '--accent2': '#D97706', '--border-hi': '#F59E0B44'
  }
};

function applyTheme(themeKey) {
  var palette = THEMES[themeKey] || THEMES['default'];
  var root = document.documentElement;
  Object.keys(palette).forEach(function(k) { root.style.setProperty(k, palette[k]); });
}

function saveTheme(mode) {
  localStorage.setItem('inkslab_theme', mode);
  if (mode === 'auto') {
    applyTheme((_lastStatus && _lastStatus.tcg) || 'default');
  } else {
    applyTheme(mode);
  }
}

// Apply saved theme on load (use cached last TCG for auto mode to avoid flash)
(function() {
  var t = localStorage.getItem('inkslab_theme') || 'default';
  applyTheme(t === 'auto' ? (localStorage.getItem('inkslab_last_tcg') || 'default') : t);
})();

// --- Global swipe guard: prevents onclick from firing during a scroll ---
var _touchMoved = false;
document.addEventListener('touchstart', function() { _touchMoved = false; }, {passive: true});
document.addEventListener('touchmove', function() { _touchMoved = true; }, {passive: true});
document.addEventListener('touchend', function(e) {
  if (e.changedTouches.length) {
    window._lastTouchEnd = {x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY};
  }
}, {passive: true});

// --- HTML escaping for safe innerHTML ---
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// --- Tab persistence ---
function equalizeSearchBtns() {
  var btns = document.querySelectorAll('[data-search-btn]');
  btns.forEach(function(b) { b.style.width = ''; });
  var maxW = 0;
  btns.forEach(function(b) { maxW = Math.max(maxW, b.offsetWidth); });
  if (maxW > 0) btns.forEach(function(b) { b.style.width = maxW + 'px'; });
}

function toggleDlLog() {
  var log = document.getElementById('dl-log');
  var btn = document.getElementById('btn-dl-log-toggle');
  if (!log) return;
  var visible = log.style.display !== 'none';
  log.style.display = visible ? 'none' : 'block';
  if (btn) btn.textContent = visible ? 'Show Log' : 'Hide Log';
}

function showTab(name) {
  localStorage.setItem('inkslab_tab', name);
  document.querySelectorAll('.nav-item').forEach(function(t) { t.classList.remove('active'); });
  document.querySelector('.nav-item[data-tab="' + name + '"]').classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  var content = document.querySelector('.content');
  if (content) content.scrollTop = 0;
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
  if (name === 'collection') { loadSets(); loadRarities(); }
  if (name === 'settings') { loadSettings(); loadWifiInfo(); loadAutoUpdateStatus(); loadMetronStatus(); initPrecacheStatus(); loadPinStatus(); }
  if (name === 'downloads') { loadStorage(); pollDownload(); loadCustomFolders(); equalizeSearchBtns(); }
  if (name === 'display') refreshStatus();
}

// --- Toast ---
var _toastTimer = null;
function showToast(msg, duration) {
  duration = duration || 2000;
  var el = document.getElementById('toast');
  if (_toastTimer) { clearTimeout(_toastTimer); _toastTimer = null; }
  el.textContent = msg;
  el.style.transition = 'none';
  el.style.opacity = '1';
  el.style.display = 'block';
  el.offsetHeight; // force reflow
  el.style.transition = '';
  _toastTimer = setTimeout(function() {
    el.style.opacity = '0';
    setTimeout(function() { el.style.display = 'none'; _toastTimer = null; }, 300);
  }, duration);
}

// --- Tab data cache (instant re-render on tab switch) ---
var _cache = {sets: {}, rarities: {}, autoUpdate: null};
var _browseTcg = null;
function getEffectiveBrowseTcg() {
  return _browseTcg || (_lastStatus && _lastStatus.tcg) || 'pokemon';
}
function updateBrowsePills(activeTcg) {
  var btn = document.getElementById('source-pill-btn');
  if (!btn) return;
  var info = _tcgRegistry && _tcgRegistry[activeTcg];
  var color = (info && info.color) || '#36A5CA';
  var shortN = {lorcana:'Lorcana',mtg:'Magic',pokemon:'Pokemon',manga:'Manga',comics:'Comics',custom:'Custom'};
  var name = shortN[activeTcg] || (info && info.name) || activeTcg;
  btn.style.borderColor = color;
  btn.style.color = color;
  var lbl = btn.querySelector('.source-pill-label');
  if (lbl) lbl.textContent = name;
  document.querySelectorAll('.source-dd-item').forEach(function(el) {
    el.classList.toggle('active', el.dataset.tcg === activeTcg);
  });
}
function closeSourceDropdown() {
  var dd = document.getElementById('source-dd');
  var btn = document.getElementById('source-pill-btn');
  if (dd) dd.style.display = 'none';
  if (btn) btn.classList.remove('open');
}
function setBrowseTcg(tcg) {
  _browseTcg = tcg;
  updateBrowsePills(tcg || (_lastStatus && _lastStatus.tcg) || '');
  var t = tcg || (_lastStatus && _lastStatus.tcg) || '';
  delete _cache.sets[t]; delete _cache.rarities[t];
  try { localStorage.removeItem('inkslab_sets_' + t); } catch(e) {}
  loadSets(); loadRarities();
  document.getElementById('search-results').innerHTML = '';
  var inp = document.getElementById('search-input');
  if (inp) inp.value = '';
  var cb = document.getElementById('search-clear');
  if (cb) cb.style.display = 'none';
}

// --- Display ---
var _lastStatus = {};
var _rapidPoll = null;
var _pendingAction = false;
var _mainPoll = null;
var _countdownTimer = null;

function lorcanaSearch() {
  var q = document.getElementById('lorcana-search-input').value.trim().toLowerCase();
  var resultsEl = document.getElementById('lorcana-search-results');
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:#888;">Loading sets...</div>';
  fetch(API + '/api/lorcana/sets')
    .then(r => r.json())
    .then(function(data) {
      var sets = data.results || [];
      if (q) sets = sets.filter(function(s) { return s.name.toLowerCase().indexOf(q) !== -1; });
      if (!sets.length) {
        resultsEl.innerHTML = '<div style="padding:10px;color:#888;">No sets found.</div>';
        return;
      }
      resultsEl.innerHTML = sets.map(function(s) {
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #222;">'
          + '<div><div style="font-weight:600;">' + esc(s.name) + '</div>'
          + '<div style="color:#888;font-size:12px;">' + esc(s.released) + (s.card_count ? ' &middot; ' + s.card_count + ' cards' : '') + '</div></div>'
          + '<button data-code="' + esc(s.code) + '" data-name="' + esc(s.name) + '" onclick="lorcanaDownloadSet(this)"'
          + ' style="padding:6px 14px;background:#C084FC;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;">Download</button>'
          + '</div>';
      }).join('');
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Failed to load sets. Check connection.</div>';
    });
}

function lorcanaDownloadSet(btn) {
  var code = btn.dataset.code;
  var name = btn.dataset.name;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'lorcana', set_code: code})
  }).then(r => r.json()).then(function(d) {
    if (d.ok) {
      showToast('Downloading ' + name + '!');
      closeAllDlSearch();
      document.getElementById('lorcana-search-results').style.display = 'none';
      document.getElementById('lorcana-search-input').value = '';
      setDownloadUI(true, 'lorcana');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download';
    }
  });
}

function mangaSearch() {
  var q = document.getElementById('manga-search-input').value.trim();
  if (!q) return;
  var resultsEl = document.getElementById('manga-search-results');
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:#888;">Searching...</div>';
  fetch(API + '/api/manga/search?q=' + encodeURIComponent(q))
    .then(r => r.json())
    .then(function(data) {
      if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML = '<div style="padding:10px;color:#888;">No results found.</div>';
        return;
      }
      resultsEl.innerHTML = data.results.map(function(m) {
        var info = [m.year, m.status, m.demographic].filter(Boolean).join(' · ');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #222;">'
          + '<div>'
          + '<div style="font-weight:600;"><a href="https://mangadex.org/title/' + m.id + '" target="_blank" style="color:#F472B6;text-decoration:none;">' + esc(m.title) + '</a></div>'
          + '<div style="color:#888;font-size:12px;">' + esc(info) + '</div>'
          + '</div>'
          + '<button onclick="mangaDownloadSeries(this)" data-id="' + m.id + '" data-title="' + esc(m.title) + '"'
          + ' style="padding:6px 14px;background:#F472B6;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;">Download All</button>'
          + '</div>';
      }).join('');
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Search failed. Check connection.</div>';
    });
}

function mangaDownloadSeries(btn) {
  var id = btn.getAttribute('data-id');
  var title = btn.getAttribute('data-title');
  if (!id) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'manga', manga_id: id, manga_title: title})
  }).then(r => r.json()).then(function(d) {
    if (d.ok) {
      showToast('Downloading covers for ' + title + '!');
      closeAllDlSearch();
      document.getElementById('manga-search-results').style.display = 'none';
      document.getElementById('manga-search-input').value = '';
      setDownloadUI(true, 'manga');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download All';
    }
  });
}

function comicSearch() {
  var q = document.getElementById('comics-search-input').value.trim();
  if (!q) return;
  var resultsEl = document.getElementById('comics-search-results');
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:#888;">Searching...</div>';
  fetch(API + '/api/comics/search?q=' + encodeURIComponent(q))
    .then(r => r.json())
    .then(function(data) {
      if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML = '<div style="padding:10px;color:#888;">No results found.</div>';
        return;
      }
      resultsEl.innerHTML = data.results.map(function(m) {
        var info = [m.issue_count + ' issues', '#' + m.id].filter(Boolean).join(' · ');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #222;">'
          + '<div>'
          + '<div style="font-weight:600;"><a href="https://metron.cloud/series/' + m.id + '/" target="_blank" style="color:#F97316;text-decoration:none;">' + esc(m.title) + '</a></div>'
          + '<div style="color:#888;font-size:12px;">' + esc(info) + '</div>'
          + '</div>'
          + '<button onclick="comicDownloadSeries(this)" data-id="' + m.id + '" data-title="' + esc(m.title) + '"'
          + ' style="padding:6px 14px;background:#F97316;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;">Download All</button>'
          + '</div>';
      }).join('');
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Search failed. Check connection.</div>';
    });
}

function comicDownloadSeries(btn) {
  var id = btn.getAttribute('data-id');
  var title = btn.getAttribute('data-title');
  if (!id) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'comics', comic_id: id, comic_title: title})
  }).then(r => r.json()).then(function(d) {
    if (d.ok) {
      showToast('Downloading covers for ' + title + '!');
      closeAllDlSearch();
      document.getElementById('comics-search-results').style.display = 'none';
      document.getElementById('comics-search-input').value = '';
      setDownloadUI(true, 'comics');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download All';
    }
  });
}

function startMainPoll() {
  if (_mainPoll) clearInterval(_mainPoll);
  _mainPoll = setInterval(refreshStatus, 10000);
}

function showPreviewLoading(msg) {
  var overlay = document.getElementById('st-preview-loading');
  document.getElementById('st-preview-loading-text').textContent = msg || 'Loading...';
  overlay.style.display = 'flex';
  overlay.querySelector('div').className = 'preview-spin';
}
function hidePreviewLoading() {
  var overlay = document.getElementById('st-preview-loading');
  overlay.style.display = 'none';
}

function updateCountdown() {
  var el = document.getElementById('countdown');
  if (_lastStatus.paused) {
    el.innerHTML = '<span class="paused-label">Paused</span>';
    return;
  }
  var nc = _lastStatus.next_change;
  if (!nc) { el.textContent = ''; return; }
  var remain = Math.max(0, nc - Math.floor(Date.now() / 1000));
  if (remain <= 0) { el.innerHTML = '<span class="time">Changing soon...</span>'; return; }
  var m = Math.floor(remain / 60);
  var s = remain % 60;
  el.innerHTML = 'Next card in <span class="time">' + m + ':' + (s < 10 ? '0' : '') + s + '</span>';
}

function startCountdown() {
  if (_countdownTimer) clearInterval(_countdownTimer);
  _countdownTimer = setInterval(updateCountdown, 1000);
  updateCountdown();
}

var _lastQueueKey = '';
var _lastPrevKey = '';
function _qCardHtml(tcg, c) {
  var thumbUrl = '/api/card_thumbnail/' + encodeURIComponent(tcg) + '/' + encodeURIComponent(c.set_id) + '/' + encodeURIComponent(c.card_id);
  var isMangaComics = (tcg === 'manga' || tcg === 'comics');
  var qNum = isMangaComics
    ? (c.set_info ? (c.set_info.match(/^(\d{4})/) || [])[1] || '\u2014' : '\u2014')
    : esc(c.card_num);
  var setName = esc(c.set_name || (c.set_info || '').replace(/^\d{4}\s+/, ''));
  var isMC = isMangaComics;
  return '<div class="q-card" data-thumb="' + thumbUrl + '"'
    + ' data-num="' + (isMC ? esc(c.rarity || '') : qNum) + '"'
    + ' data-rarity="' + (isMC ? qNum : esc(c.rarity || '')) + '"'
    + ' data-set="' + setName + '"'
    + ' data-num-label="' + (isMC ? (tcg === 'manga' ? 'Volume #' : 'Issue #') : 'Card #') + '"'
    + ' data-rarity-label="' + (isMC ? 'Year' : 'Rarity') + '">'
    + '<img class="q-thumb" src="' + thumbUrl + '" onerror="this.style.display=\'none\'">'
    + '<div class="q-num">' + qNum + '</div>'
    + '<div class="q-rarity">' + esc(c.rarity || '') + '</div>'
    + '<div class="q-set-info">' + setName + '</div></div>';
}
function _attachQCardClicks(listEl) {
  listEl.querySelectorAll('.q-card').forEach(function(card) {
    card.addEventListener('click', function() {
      if (_touchMoved) return;
      var previewImg = document.getElementById('preview-img');
      var previewModal = document.getElementById('preview-modal');
      if (previewModal && previewImg) {
        previewImg.style.opacity = '0';
        previewImg.onload = function() { this.style.opacity = '1'; };
        previewImg.src = card.dataset.thumb;
        var previewName = document.getElementById('preview-name');
        if (previewName) previewName.textContent = '';
        // Populate stat bubbles in preview modal
        var pmNumLbl = document.getElementById('pm-num-label');
        var pmNum = document.getElementById('pm-num');
        var pmRarityLbl = document.getElementById('pm-rarity-label');
        var pmRarity = document.getElementById('pm-rarity');
        var pmSet = document.getElementById('pm-set');
        if (pmNumLbl) pmNumLbl.textContent = card.dataset.numLabel || 'Card #';
        if (pmNum) pmNum.textContent = card.dataset.num || '\u2014';
        if (pmRarityLbl) pmRarityLbl.textContent = card.dataset.rarityLabel || 'Rarity';
        if (pmRarity) pmRarity.textContent = card.dataset.rarity || '\u2014';
        if (pmSet) pmSet.textContent = card.dataset.set || '\u2014';
        previewModal.classList.add('open');
      }
    });
  });
}
function renderQueue(d) {
  var tcg = (d.tcg || '').toLowerCase();
  var isDesktop = window.innerWidth >= 600;

  // --- Up Next ---
  var next = (d.next_cards || []).slice(0, isDesktop ? 5 : 4);
  var queueKey = JSON.stringify(next.map(function(c){return c.card_id}));
  if (queueKey !== _lastQueueKey) {
    _lastQueueKey = queueKey;
    var queueCard = document.getElementById('queue-card');
    queueCard.style.display = 'block';
    var listEl = document.getElementById('q-next-list');
    var maxNext = isDesktop ? 5 : 4;
    listEl.style.gridTemplateColumns = 'repeat(' + maxNext + ', 1fr)';
    var html = next.map(function(c) { return _qCardHtml(tcg, c); }).join('');
    for (var i = next.length; i < maxNext; i++) {
      html += '<div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>';
    }
    listEl.innerHTML = html;
    _attachQCardClicks(listEl);
  }

  // --- Previous ---
  var prev = (d.prev_cards || []).slice(0, 5);
  var prevKey = JSON.stringify(prev.map(function(c){return c.card_id}));
  if (prevKey !== _lastPrevKey) {
    _lastPrevKey = prevKey;
    var prevListEl = document.getElementById('q-prev-list');
    if (prevListEl) {
      var html = prev.map(function(c) { return _qCardHtml(tcg, c); }).join('');
      for (var i = prev.length; i < 5; i++) {
        html += '<div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>';
      }
      prevListEl.innerHTML = html;
      _attachQCardClicks(prevListEl);
    }
  }
}

function updatePauseBtn(paused) {
  var btn = document.getElementById('btn-pause');
  if (paused) {
    btn.innerHTML = '&#9654;';
    btn.classList.add('paused');
    btn.title = 'Resume';
  } else {
    btn.innerHTML = '&#10074;&#10074;';
    btn.classList.remove('paused');
    btn.title = 'Pause';
  }
}

function updatePillTcg(tcg) {
  var explicit = !!tcg;
  var pill = document.getElementById('pill-tcg');
  if (!pill) return;
  // While TCG is unknown, show neutral "InkSlab" placeholder
  if (!tcg) {
    var accentColor = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#36A5CA';
    pill.textContent = 'InkSlab';
    pill.dataset.color = accentColor;
    var sbTcgPlaceholder = document.getElementById('sb-tcg');
    if (sbTcgPlaceholder) { sbTcgPlaceholder.textContent = 'InkSlab'; sbTcgPlaceholder.dataset.color = accentColor; }
    return;
  }
  var shortNames = {lorcana: 'Lorcana', mtg: 'Magic', pokemon: 'Pokemon', manga: 'Manga', comics: 'Comics', custom: 'Custom'};
  var info = _tcgRegistry && _tcgRegistry[tcg];
  var color = (info && info.color) || '#36A5CA';
  var name = shortNames[tcg] || (info && info.name) || tcg.toUpperCase();
  pill.textContent = name;
  pill.dataset.color = color;
  var sbTcg = document.getElementById('sb-tcg');
  if (sbTcg) { sbTcg.textContent = name; sbTcg.dataset.color = color; }
  // Auto theme: only apply when tcg was explicitly provided (not a null fallback)
  if (explicit && (localStorage.getItem('inkslab_theme') || 'default') === 'auto') {
    localStorage.setItem('inkslab_last_tcg', tcg);
    applyTheme(tcg);
  }
}

function updatePillStyle(collectionOnly) {
  var pill = document.getElementById('pill-tcg');
  if (!pill) return;
  var color = pill.dataset.color || 'var(--accent)';
  if (collectionOnly) {
    pill.style.background = color;
    pill.style.color = 'var(--bg)';
  } else {
    pill.style.background = '';
    pill.style.color = color;
  }
  var sbTcg = document.getElementById('sb-tcg');
  if (sbTcg) {
    var sbColor = sbTcg.dataset.color || color;
    if (collectionOnly) { sbTcg.style.background = sbColor; sbTcg.style.color = 'var(--bg)'; }
    else { sbTcg.style.background = ''; sbTcg.style.color = sbColor; }
  }
}

function updateQuickSwitchActive(tcg) {
  document.querySelectorAll('#quick-switch-btns .btn, #sb-quick-switch-btns .btn').forEach(function(b) {
    var color = b.dataset.color || 'var(--accent)';
    if (b.dataset.tcg === tcg) {
      b.style.background = color;
      b.style.color = 'var(--bg)';
    } else {
      b.style.background = 'transparent';
      b.style.color = color;
    }
    b.style.borderColor = color;
  });
  if (window._mobileQSHook) window._mobileQSHook(tcg);
}

function pillTcgTap() {
  var tcgs = Object.keys(_tcgRegistry || {});
  if (!tcgs.length) return;
  var cur = (_lastStatus && _lastStatus.tcg) || tcgs[0];
  var idx = tcgs.indexOf(cur);
  var next = tcgs[(idx + 1) % tcgs.length];
  switchTCG(next, null);
}

function refreshStatus() {
  fetch(API + '/api/status').then(r => r.json()).then(d => {
    document.getElementById('st-tcg').textContent = (d.tcg || '\u2014').toUpperCase();
    var cardLbl = document.getElementById('st-card-label');
    var rarityLbl = document.getElementById('st-rarity-label');
    var totalLbl = document.getElementById('st-total-label');
    var siCardLbl = document.getElementById('si-card-label');
    var siRarityLbl = document.getElementById('si-rarity-label');
    var siTotalLbl = document.getElementById('si-total-label');
    if (d.tcg === 'manga') {
      if (cardLbl) cardLbl.textContent = 'Volume #';
      if (rarityLbl) rarityLbl.textContent = 'Year';
      if (totalLbl) totalLbl.textContent = 'Volumes in Series';
      if (siCardLbl) siCardLbl.textContent = 'Volume #';
      if (siRarityLbl) siRarityLbl.textContent = 'Year';
      if (siTotalLbl) siTotalLbl.textContent = 'Volumes in Series';
    } else if (d.tcg === 'comics') {
      if (cardLbl) cardLbl.textContent = 'Issue #';
      if (rarityLbl) rarityLbl.textContent = 'Year';
      if (totalLbl) totalLbl.textContent = 'Issues in Series';
      if (siCardLbl) siCardLbl.textContent = 'Issue #';
      if (siRarityLbl) siRarityLbl.textContent = 'Year';
      if (siTotalLbl) siTotalLbl.textContent = 'Issues in Series';
    } else {
      if (cardLbl) cardLbl.textContent = 'Card #';
      if (rarityLbl) rarityLbl.textContent = 'Rarity';
      if (totalLbl) totalLbl.textContent = 'Cards in Deck';
      if (siCardLbl) siCardLbl.textContent = 'Card #';
      if (siRarityLbl) siRarityLbl.textContent = 'Rarity';
      if (siTotalLbl) siTotalLbl.textContent = 'Cards in Deck';
    }
    updatePillTcg(d.tcg);
    updateQuickSwitchActive(d.tcg || '');
    if (!_browseTcg) updateBrowsePills(d.tcg);
    var collOnly = !!d.collection_only;
    updatePillStyle(collOnly);
    var collCb = document.getElementById('cfg-collection');
    if (collCb) collCb.checked = collOnly;
    var errRow = document.getElementById('st-error-row');
    var errEl = document.getElementById('st-error');
    if (d.error) {
      errEl.textContent = d.error;
      errRow.style.display = 'block';
      errEl.style.color = 'var(--danger)';
    } else {
      errRow.style.display = 'none';
    }
    if (!d.pending) {
      var isMangaComics = (d.tcg === 'manga' || d.tcg === 'comics');
      var cardNum = isMangaComics
        ? (d.number && d.number !== '?' ? d.number : '\u2014')
        : ((d.card_num || '').replace(/^#/, '') || '\u2014');
      document.getElementById('st-card').textContent = cardNum;
      document.getElementById('st-set').textContent = d.set_name || d.set_info || '\u2014';
      var rarityVal = d.rarity || '\u2014';
      if (isMangaComics && d.set_info) {
        var yrMatch = d.set_info.match(/^(\d{4})/);
        rarityVal = yrMatch ? yrMatch[1] : '\u2014';
      }
      document.getElementById('st-rarity').textContent = rarityVal;
      document.getElementById('st-total').textContent = d.total_cards || '\u2014';
      // Inline stat bubbles (desktop only, below card)
      var siCard = document.getElementById('si-card');
      var siSet = document.getElementById('si-set');
      var siRarity = document.getElementById('si-rarity');
      var siTotal = document.getElementById('si-total');
      var siTcg = document.getElementById('si-tcg');
      if (siCard) siCard.textContent = cardNum;
      if (siSet) siSet.textContent = d.set_name || d.set_info || '\u2014';
      if (siRarity) siRarity.textContent = rarityVal;
      if (siTotal) siTotal.textContent = d.total_cards || '\u2014';
      if (siTcg) siTcg.textContent = (d.tcg || '\u2014').toUpperCase();
      var img = document.getElementById('st-preview');
      if (d.card_path) {
        img.style.visibility = '';
        var needsReload = (!img.getAttribute('src')
          || d.card_path !== _lastStatus.card_path
          || d.tcg !== _lastStatus.tcg
          || (_lastStatus.pending && !d.pending));
        if (needsReload) {
          if (d.tcg && d.set_id && d.card_id) {
            var base = encodeURIComponent(d.tcg) + '/' + encodeURIComponent(d.set_id) + '/' + encodeURIComponent(d.card_id);
            img.src = '/api/card_image/' + base;
          } else {
            img.src = '/api/card_image?t=' + Date.now();
          }
        }
      } else {
        img.style.visibility = '';
        if (img.src.indexOf('/static/inkslab-booting.png') === -1) {
          img.src = '/static/inkslab-booting.png';
        }
      }
      // Show/hide loading overlay based on display state
      if (d.display_updating) {
        showPreviewLoading('Updating display...');
      } else {
        hidePreviewLoading();
      }
    }
    // Always render queue (even during pending — Previous shows placeholders)
    renderQueue(d);
    // Update pause button and countdown
    updatePauseBtn(d.paused);
    updateCountdown();
    // Disable prev button if no history
    document.getElementById('btn-prev').disabled = !(d.prev_cards && d.prev_cards.length);
    // Stop rapid polling once fully settled (not pending AND not updating display)
    if (_rapidPoll && !d.pending && !d.display_updating) {
      clearInterval(_rapidPoll);
      _rapidPoll = null;
      _pendingAction = false;
      startMainPoll();
    }
    _lastStatus = d;
    var tempWrap = document.getElementById('pill-temp-wrap');
    var tempEl = document.getElementById('pill-temp');
    if (tempEl && tempWrap && d.cpu_temp != null) {
      tempEl.textContent = d.cpu_temp + '\u00b0C';
      tempEl.style.color = d.cpu_temp >= 75 ? '#f87171' : d.cpu_temp >= 61 ? '#fb923c' : '';
      tempWrap.style.display = '';
    }
    var sbTempWrap = document.getElementById('sb-temp-wrap');
    var sbTempEl = document.getElementById('sb-temp');
    if (sbTempEl && sbTempWrap) {
      if (d.cpu_temp != null) {
        sbTempEl.textContent = d.cpu_temp + '\u00b0C';
        sbTempEl.style.color = d.cpu_temp >= 75 ? '#f87171' : d.cpu_temp >= 61 ? '#fb923c' : 'var(--text-dim)';
        sbTempWrap.style.display = '';
      }
    }
  }).catch(() => {});
}

function startRapidPoll() {
  _pendingAction = true;
  if (_mainPoll) { clearInterval(_mainPoll); _mainPoll = null; }
  if (_rapidPoll) clearInterval(_rapidPoll);
  _rapidPoll = setInterval(refreshStatus, 2000);
  setTimeout(function() {
    if (_rapidPoll) { clearInterval(_rapidPoll); _rapidPoll = null; _pendingAction = false; startMainPoll(); }
  }, 60000);
}

function setOptimisticLoading(msg) {
  showPreviewLoading(msg);
  document.getElementById('st-card').textContent = '\u2014';
  document.getElementById('st-set').textContent = '\u2014';
  document.getElementById('st-rarity').textContent = '\u2014';
  var siCard = document.getElementById('si-card'); if (siCard) siCard.textContent = '\u2014';
  var siSet = document.getElementById('si-set'); if (siSet) siSet.textContent = '\u2014';
  var siRarity = document.getElementById('si-rarity'); if (siRarity) siRarity.textContent = '\u2014';
}

function showCardInfoModal() {
  document.getElementById('card-info-modal').classList.add('open');
}

function _warnShortDisplay() {
  var ds = _lastStatus && (_lastStatus.display_start || _lastStatus.timestamp);
  if (!ds) return true;
  var elapsed = Math.floor(Date.now() / 1000) - ds;
  if (elapsed < 180) {
    var remaining = 180 - elapsed;
    return confirm('This card has only been on the display for ' + elapsed + 's.\n\nWaveshare recommends at least 3 minutes between refreshes to avoid display wear.\n\nAdvance anyway? (' + remaining + 's remaining)');
  }
  return true;
}

function nextCard() {
  if (!_warnShortDisplay()) return;
  var btn = document.getElementById('btn-next');
  btn.disabled = true;
  fetch(API + '/api/next', {method:'POST'})
    .then(function() {
      btn.disabled = false;
      showToast('Next card...');
      setOptimisticLoading('Loading next card...');
      startRapidPoll();
    })
    .catch(function() { btn.disabled = false; showToast('Failed'); });
}

function prevCard() {
  if (!_warnShortDisplay()) return;
  var btn = document.getElementById('btn-prev');
  btn.disabled = true;
  fetch(API + '/api/prev', {method:'POST'})
    .then(function() {
      btn.disabled = false;
      showToast('Previous card...');
      setOptimisticLoading('Loading previous card...');
      startRapidPoll();
    })
    .catch(function() { btn.disabled = false; showToast('Failed'); });
}

function togglePause() {
  fetch(API + '/api/pause', {method:'POST'})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      updatePauseBtn(d.paused);
      _lastStatus.paused = d.paused;
      if (d.paused) {
        _lastStatus.next_change = 0;
        showToast('Paused');
      } else {
        _lastStatus.next_change = Math.floor(Date.now() / 1000) + (_lastStatus.interval || 600);
        showToast('Resumed');
      }
      updateCountdown();
    });
}

function _doSwitchTCG(tcg) {
  var btns = document.querySelectorAll('#quick-switch-btns .btn, #sb-quick-switch-btns .btn');
  btns.forEach(function(b) { b.disabled = true; });
  updatePillTcg(tcg);
  updatePillStyle(!!((_lastStatus && _lastStatus.collection_only)));
  fetch(API + '/api/config', {method:'POST', body: JSON.stringify({active_tcg: tcg}),
    headers:{'Content-Type':'application/json'}})
    .then(function() {
      btns.forEach(function(b) { b.disabled = false; });
      var name = (_tcgRegistry[tcg] && _tcgRegistry[tcg].name) || tcg.toUpperCase();
      showToast('Switching to ' + name + '...');
      document.getElementById('st-tcg').textContent = name;
      updatePillTcg(tcg);
      updateQuickSwitchActive(tcg);
      setOptimisticLoading('Switching to ' + name + '...');
      startRapidPoll();
    })
    .catch(function() {
      btns.forEach(function(b) { b.disabled = false; });
      showToast('Switch failed');
    });
}
window._doSwitchTCG = _doSwitchTCG;

function _showSwitchCooldownBanner(tcg, remaining) {
  if (window._mobileQSCooldown) { window._mobileQSCooldown(tcg, remaining); return; }
  var existing = document.getElementById('switch-cooldown-banner');
  if (existing) existing.remove();
  var name = (_tcgRegistry[tcg] && _tcgRegistry[tcg].name) || tcg.toUpperCase();
  var banner = document.createElement('div');
  banner.id = 'switch-cooldown-banner';
  banner.className = 'switch-cooldown-banner';
  banner.innerHTML = '<span>Display refreshes in ~' + remaining + 's. Switch to ' + name + ' now anyway?</span>'
    + '<div class="scb-btns">'
    + '<button class="btn btn-sm btn-secondary scb-cancel">Cancel</button>'
    + '<button class="btn btn-sm scb-confirm">Switch Anyway</button>'
    + '</div>';
  banner.querySelector('.scb-cancel').addEventListener('click', function() { banner.remove(); });
  banner.querySelector('.scb-confirm').addEventListener('click', function() {
    banner.remove();
    _doSwitchTCG(tcg);
  });
  // Insert after whichever quick-switch container is visible
  var sbQs = document.getElementById('sb-quick-switch-btns');
  var mobQs = document.getElementById('quick-switch-btns');
  var qs = (sbQs && sbQs.offsetParent) ? sbQs : (mobQs || sbQs);
  if (qs) qs.parentNode.insertBefore(banner, qs.nextSibling);
  else document.body.appendChild(banner);
}

function switchTCG(tcg, activeBtn) {
  var ds = _lastStatus && (_lastStatus.display_start || _lastStatus.timestamp);
  var cooldownRemaining = ds ? Math.max(0, 180 - Math.floor(Date.now() / 1000 - ds)) : 0;
  if (cooldownRemaining > 0) {
    _showSwitchCooldownBanner(tcg, cooldownRemaining);
    return;
  }
  _doSwitchTCG(tcg);
}

// --- Settings ---
function loadAutoUpdateStatus() {
  if (_cache.autoUpdate) renderAutoUpdate(_cache.autoUpdate);
  fetch(API + '/api/auto_update/status').then(r => r.json()).then(function(data) {
    _cache.autoUpdate = data;
    renderAutoUpdate(data);
  }).catch(function() {
    if (!_cache.autoUpdate) {
      var el = document.getElementById('auto-update-list');
      if (el) el.innerHTML = '<div style="color:#ff6b6b;font-size:12px;">Failed to load</div>';
    }
  });
}

function renderAutoUpdate(data) {
  var el = document.getElementById('auto-update-list');
  if (!el) return;
  el.innerHTML = '';
  Object.entries(data).sort(function(a, b) {
    if (a[0] === 'custom') return -1;
    if (b[0] === 'custom') return 1;
    return a[1].name.localeCompare(b[1].name);
  }).forEach(function(entry) {
    var tcg = entry[0], info = entry[1];
    var lastStr = info.last_update ? new Date(info.last_update).toLocaleDateString() : 'Never';
    var row = document.createElement('div');
    row.className = 'form-row';
    var left = document.createElement('div');
    left.style.flex = '1';
    left.innerHTML = '<span class="row-label">' + esc(info.name) + '</span>'
      + '<div style="font-size:11px;color:var(--text-dim);margin-top:2px;">Last: ' + lastStr + '</div>';
    var sw = document.createElement('label');
    sw.className = 'switch';
    var inp = document.createElement('input');
    inp.type = 'checkbox';
    inp.id = 'au-' + tcg;
    inp.checked = !!info.enabled;
    inp.addEventListener('change', saveAutoUpdate);
    var slider = document.createElement('span');
    slider.className = 'switch-slider';
    sw.appendChild(inp);
    sw.appendChild(slider);
    row.appendChild(left);
    row.appendChild(sw);
    el.appendChild(row);
  });
  if (!el.children.length) el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">No sources available</div>';

  // Next scheduled update
  var nextEl = document.getElementById('auto-update-next');
  if (nextEl) {
    var enabled = Object.values(data).filter(function(d) { return d.enabled; });
    if (!enabled.length) {
      nextEl.textContent = 'Next scheduled: No sources enabled';
    } else {
      var earliest = null;
      enabled.forEach(function(d) {
        var next = d.last_update
          ? new Date(new Date(d.last_update).getTime() + 7 * 24 * 60 * 60 * 1000)
          : new Date();
        if (!earliest || next < earliest) earliest = next;
      });
      nextEl.textContent = earliest <= new Date()
        ? 'Next scheduled: Due now (runs at next hourly check)'
        : 'Next scheduled: ' + earliest.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
    }
  }
}

function runAllNow() {
  var btn = document.getElementById('btn-run-all');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/auto_update/run_all', {method: 'POST', headers: {'Content-Type': 'application/json'}})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        showToast('Running updates for ' + d.count + ' source' + (d.count !== 1 ? 's' : '') + '...', 3000);
        btn.textContent = 'Running...';
        setTimeout(function() { btn.disabled = false; btn.textContent = 'Run All Now'; }, 8000);
      } else {
        showToast(d.error || 'Failed to start', 3000);
        btn.disabled = false;
        btn.textContent = 'Run All Now';
      }
    }).catch(function() {
      showToast('Failed to start', 3000);
      btn.disabled = false;
      btn.textContent = 'Run All Now';
    });
}

function saveAutoUpdate() {
  var sources = [];
  document.querySelectorAll('[id^="au-"]').forEach(function(cb) {
    if (cb.checked) sources.push(cb.id.replace('au-', ''));
  });
  fetch(API + '/api/auto_update/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sources: sources})
  }).then(r => r.json()).then(function(d) {
    if (d.ok) showToast('Auto-update settings saved!', 2000);
  }).catch(function() { showToast('Failed to save'); });
}

function runUpdateNow(tcg, btn) {
  if (!confirm('Run update for ' + tcg.toUpperCase() + ' now? This will start a download.')) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/auto_update/run_now', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: tcg})
  }).then(r => r.json()).then(function(d) {
    btn.disabled = false;
    btn.textContent = 'Run Now';
    if (d.ok) {
      showToast(tcg.toUpperCase() + ' update started!', 2000);
      showTab('downloads');
    } else {
      showToast('Error: ' + (d.error || 'Unknown'), 3000);
    }
  }).catch(function() {
    btn.disabled = false;
    btn.textContent = 'Run Now';
  });
}

function loadMetronStatus() {
  fetch(API + '/api/metron/status').then(r => r.json()).then(function(d) {
    var statusEl = document.getElementById('metron-status');
    var formEl = document.getElementById('metron-form');
    if (!statusEl || !formEl) return;
    if (d.configured) {
      statusEl.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">&#10003; Connected as <strong>' + esc(d.username) + '</strong> &nbsp;<button class="btn btn-secondary btn-sm" onclick="testMetronCreds()" style="font-size:11px;">Test</button> <button class="btn btn-secondary btn-sm" onclick="clearMetronCreds()" style="font-size:11px;">Disconnect</button></div><div id="metron-test-result" style="margin-top:6px;font-size:13px;display:none;"></div>';
      formEl.style.display = 'none';
    } else {
      statusEl.innerHTML = '<div style="color:#888;font-size:13px;">Not connected</div>';
      formEl.style.display = 'block';
    }
  });
}

function saveMetronCreds() {
  var username = document.getElementById('metron-username').value.trim();
  var password = document.getElementById('metron-password').value.trim();
  if (!username || !password) { showToast('Username and password required', 3000); return; }
  fetch(API + '/api/metron/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: username, password: password})
  }).then(r => r.json()).then(function(d) {
    if (d.ok) {
      showToast('Metron credentials saved!', 2000);
      document.getElementById('metron-username').value = '';
      document.getElementById('metron-password').value = '';
      loadMetronStatus();
    } else {
      showToast('Error: ' + (d.error || 'Unknown'), 3000);
    }
  }).catch(function() { showToast('Failed to save credentials'); });
}

function clearMetronCreds() {
  if (!confirm('Disconnect Metron account? Comic downloads will stop working.')) return;
  fetch(API + '/api/metron/clear', {method: 'POST'}).then(r => r.json()).then(function(d) {
    if (d.ok) { showToast('Metron account disconnected', 2000); loadMetronStatus(); }
  });
}

function testMetronCreds() {
  var username = (document.getElementById('metron-username').value || '').trim();
  var password = (document.getElementById('metron-password').value || '').trim();
  var resultEl = document.getElementById('metron-test-result');
  if (resultEl) { resultEl.style.display = 'block'; resultEl.style.color = 'var(--text-dim)'; resultEl.textContent = 'Testing...'; }
  fetch(API + '/api/metron/test', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: username, password: password})
  }).then(r => r.json()).then(function(d) {
    if (!resultEl) return;
    if (d.ok) {
      resultEl.style.color = 'var(--accent2)';
      resultEl.textContent = 'Connected successfully!';
    } else {
      resultEl.style.color = 'var(--danger)';
      resultEl.textContent = d.error || 'Connection failed';
    }
  }).catch(function() {
    if (resultEl) { resultEl.style.color = 'var(--danger)'; resultEl.textContent = 'Connection error'; }
  });
}

function loadSettings() {
  fetch(API + '/api/config').then(r => r.json()).then(c => {
    document.getElementById('cfg-tcg').value = c.active_tcg;
    document.getElementById('cfg-header-mode').value = c.slab_header_mode || 'normal';
    var fitEl = document.getElementById('cfg-image-fit');
    if (fitEl) fitEl.value = c.image_fit || 'contain';
    var bgEl = document.getElementById('cfg-image-bg');
    if (bgEl) bgEl.value = c.image_bg || 'black';
    document.getElementById('cfg-rotation').value = c.rotation_angle;
    document.getElementById('cfg-day-interval').value = Math.round(c.day_interval / 60);
    document.getElementById('cfg-night-interval').value = Math.round(c.night_interval / 60);
    document.getElementById('cfg-day-start').value = c.day_start;
    document.getElementById('cfg-day-end').value = c.day_end;
    document.getElementById('cfg-saturation').value = c.color_saturation;
    document.getElementById('cfg-collection').checked = c.collection_only;
    var themeEl = document.getElementById('cfg-theme');
    if (themeEl) themeEl.value = localStorage.getItem('inkslab_theme') || 'default';
    var thumbEl = document.getElementById('cfg-thumbnails');
    if (thumbEl) thumbEl.checked = c.thumbnail_cache !== false;
  });
}

var _precachePoll = null;
function _updatePrecacheStatus(p) {
  var statusEl = document.getElementById('precache-status');
  if (!statusEl) return;
  if (p.running) {
    statusEl.style.display = 'block';
    statusEl.textContent = p.done + ' / ' + p.total + ' thumbnails cached';
  } else if (p.done > 0) {
    statusEl.style.display = 'block';
    statusEl.textContent = p.done + ' thumbnails cached';
  } else {
    statusEl.style.display = 'none';
  }
}

function initPrecacheStatus() {
  fetch(API + '/api/thumbnails/progress').then(r => r.json()).then(function(p) {
    _updatePrecacheStatus(p);
    if (p.running && !_precachePoll) {
      _precachePoll = setInterval(function() {
        fetch(API + '/api/thumbnails/progress').then(r => r.json()).then(function(p) {
          _updatePrecacheStatus(p);
          if (!p.running) { clearInterval(_precachePoll); _precachePoll = null; }
        }).catch(function() {});
      }, 5000);
    }
  }).catch(function() {});
}

function saveSettings() {
  const cfg = {
    active_tcg: document.getElementById('cfg-tcg').value,
    slab_header_mode: document.getElementById('cfg-header-mode').value,
    image_fit: document.getElementById('cfg-image-fit') ? document.getElementById('cfg-image-fit').value : 'contain',
    image_bg: document.getElementById('cfg-image-bg') ? document.getElementById('cfg-image-bg').value : 'black',
    rotation_angle: parseInt(document.getElementById('cfg-rotation').value) || 270,
    day_interval: (parseInt(document.getElementById('cfg-day-interval').value) || 10) * 60,
    night_interval: (parseInt(document.getElementById('cfg-night-interval').value) || 60) * 60,
    day_start: parseInt(document.getElementById('cfg-day-start').value) || 7,
    day_end: parseInt(document.getElementById('cfg-day-end').value) || 23,
    color_saturation: parseFloat(document.getElementById('cfg-saturation').value) || 2.5,
    thumbnail_cache: document.getElementById('cfg-thumbnails') ? document.getElementById('cfg-thumbnails').checked : true,
  };
  fetch(API + '/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg)})
    .then(function() { _cache.autoUpdate = null; showToast('Settings saved!'); startRapidPoll(); })
    .catch(function() { showToast('Failed to save settings'); });
}

function saveCollectionMode() {
  var checked = document.getElementById('cfg-collection').checked;
  updatePillStyle(checked);
  fetch(API + '/api/config', {method:'POST', body: JSON.stringify({collection_only: checked}),
    headers: {'Content-Type': 'application/json'}})
    .then(function() { showToast(checked ? 'Collection Only: ON' : 'Collection Only: OFF'); })
    .catch(function() { showToast('Failed to save'); updatePillStyle(!checked); document.getElementById('cfg-collection').checked = !checked; });
}

// --- Admin (hidden) ---
var _adminTaps = 0;
var _adminTimer = null;
function adminTap() {
  _adminTaps++;
  if (_adminTimer) clearTimeout(_adminTimer);
  _adminTimer = setTimeout(function() { _adminTaps = 0; }, 2000);
  if (_adminTaps >= 5) {
    _adminTaps = 0;
    var panel = document.getElementById('admin-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    if (panel.style.display === 'block') showToast('Admin mode');
  }
}

// --- WiFi ---
var _sysStatsTimer = null;
function loadSystemStats() {
  Promise.all([
    fetch(API + '/api/system').then(r => r.json()),
    fetch(API + '/api/wifi/status').then(r => r.json()).catch(() => ({}))
  ]).then(function(results) {
    var d = results[0];
    var w = results[1];
    var el = document.getElementById('system-stats');
    if (!el) return;
    var tempColor = d.cpu_temp >= 75 ? 'var(--danger)' : d.cpu_temp >= 60 ? '#F59E0B' : 'var(--accent2)';
    var ramPct = d.ram_total_mb ? Math.round(d.ram_used_mb / d.ram_total_mb * 100) : 0;
    var ramColor = ramPct >= 85 ? 'var(--danger)' : ramPct >= 70 ? '#F59E0B' : 'var(--accent2)';
    var html = '<div class="stat"><span class="stat-label">CPU Temp</span><span class="stat-value" style="color:' + tempColor + '">' + (d.cpu_temp != null ? d.cpu_temp + '°C' : '—') + '</span></div>';
    html += '<div class="stat"><span class="stat-label">RAM</span><span class="stat-value" style="color:' + ramColor + '">' + (d.ram_used_mb != null ? d.ram_used_mb + ' / ' + d.ram_total_mb + ' MB (' + ramPct + '%)' : '—') + '</span></div>';
    html += '<div class="stat"><span class="stat-label">Uptime</span><span class="stat-value" style="color:var(--accent2)">' + (d.uptime || '—') + '</span></div>';
    var wifiVal = w.ssid ? (w.ssid + (w.ip ? ' · ' + w.ip : '')) : (w.ip || '—');
    html += '<div class="stat"><span class="stat-label">WiFi</span><span class="stat-value" style="color:var(--accent2)">' + wifiVal + '</span></div>';
    el.innerHTML = html;
    if (_sysStatsTimer) clearTimeout(_sysStatsTimer);
    _sysStatsTimer = setTimeout(function() {
      if (document.getElementById('system-stats')) loadSystemStats();
    }, 30000);
  }).catch(function() {});
}

function loadPinStatus() {
  fetch(API + '/api/auth/status').then(r => r.json()).then(function(d) {
    var statusEl = document.getElementById('pin-status');
    var btn = document.getElementById('pin-set-btn');
    if (!statusEl || !btn) return;
    if (d.pin_configured) {
      statusEl.innerHTML = '<span style="color:var(--accent)">&#10003; PIN is set</span> &mdash; your dashboard is protected.';
      btn.textContent = 'Change / Remove PIN';
    } else {
      statusEl.innerHTML = '<span style="color:var(--text-dim)">No PIN set</span> &mdash; anyone on your network can access InkSlab.';
      btn.textContent = 'Set a PIN';
    }
    btn.style.display = 'block';
    document.getElementById('pin-current-label').style.display = d.pin_configured ? 'block' : 'none';
    document.getElementById('pin-current').closest('.form-group').style.display = d.pin_configured ? 'block' : 'none';
  }).catch(function() {});
}

function showPinForm() {
  document.getElementById('pin-form').style.display = 'block';
  document.getElementById('pin-error').textContent = '';
  document.getElementById('pin-current').value = '';
  document.getElementById('pin-new').value = '';
}

function savePinChange() {
  var current = document.getElementById('pin-current').value.trim();
  var newPin = document.getElementById('pin-new').value.trim();
  var errEl = document.getElementById('pin-error');
  errEl.textContent = '';
  fetch(API + '/api/auth/change_pin', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({current_pin: current, new_pin: newPin})})
    .then(r => r.json()).then(function(d) {
      if (d.ok) {
        document.getElementById('pin-form').style.display = 'none';
        loadPinStatus();
        showToast(newPin ? 'PIN updated' : 'PIN removed');
      } else {
        errEl.textContent = d.error || 'Failed';
      }
    }).catch(function() { errEl.textContent = 'Connection error'; });
}

function loadWifiInfo() {
  var el = document.getElementById('wifi-info');
  fetch(API + '/api/wifi/status').then(r => r.json()).then(function(d) {
    if (d.connected && d.ssid) {
      var safeSSID = (d.ssid||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      el.innerHTML = 'Connected to <strong>' + safeSSID + '</strong>' + (d.ip ? ' &mdash; IP: ' + d.ip : '');
    } else if (d.hotspot_active) {
      el.textContent = 'Setup mode — broadcasting ' + (d.hotspot_ssid || 'InkSlab-Setup');
    } else {
      el.innerHTML = 'Not connected &mdash; <button class="btn btn-secondary btn-sm" onclick="retryWifi(this)" style="margin-left:4px">Retry</button>';
    }
  }).catch(function() { el.textContent = 'Could not check WiFi status'; });
}

function retryWifi(btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Retrying...'; }
  fetch(API + '/api/wifi/retry', {method: 'POST'}).then(function() {
    var el = document.getElementById('wifi-info');
    el.textContent = 'Connecting...';
    var tries = 0;
    var poll = setInterval(function() {
      tries++;
      fetch(API + '/api/wifi/status').then(r => r.json()).then(function(d) {
        if (d.connected && d.ssid) {
          clearInterval(poll);
          loadWifiInfo();
          showToast('Connected to ' + d.ssid, 3000);
        } else if (tries >= 15) {
          clearInterval(poll);
          loadWifiInfo();
        }
      }).catch(function() {
        if (tries >= 15) { clearInterval(poll); loadWifiInfo(); }
      });
    }, 2000);
  }).catch(function() { showToast('Retry failed'); if (btn) { btn.disabled = false; btn.textContent = 'Retry'; } });
}

function factoryReset(btn) {
  var keepList = [];
  ['pokemon','mtg','lorcana','manga','comics'].forEach(function(t) {
    var cb = document.getElementById('keep-' + t);
    if (cb && cb.checked) keepList.push(t);
  });
  if (!confirm('PREPARE FOR NEW OWNER\\n\\nThis will:\\n- Forget WiFi credentials\\n- Delete ALL unchecked card libraries\\n- Reset all settings\\n- Show a welcome screen on the display\\n\\nAfter it finishes, wait ~30 seconds for the display to update, then unplug. The unit is ready to ship.\\n\\nAre you sure?')) return;
  if (!confirm('This cannot be undone. Continue?')) return;
  btn.disabled = true;
  btn.textContent = 'Resetting...';
  fetch(API + '/api/factory_reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({keep_cards: keepList})}).then(r => r.json()).then(function(d) {
    if (d.ok) {
      showToast('Done! Wait ~30s for the display to update, then unplug to ship.', 8000);
      document.getElementById('wifi-info').innerHTML = '<strong style="color:#ff6b6b">Ready to ship</strong> — Wait for the display to update, then unplug.';
      btn.textContent = 'Done — unplug when display updates';
    } else {
      showToast('Reset failed: ' + (d.error || 'unknown'));
      btn.disabled = false;
      btn.textContent = 'Prepare for New Owner';
    }
  }).catch(function() {
    showToast('Reset in progress — connection lost because WiFi was disconnected. Wait ~30s for display to update, then unplug.');
    btn.textContent = 'Done — unplug when display updates';
  });
}

function changeWifi() {
  if (!confirm('This will disconnect WiFi and start the setup hotspot.\\n\\nAfter this:\\n1. On your phone, go to Settings > WiFi\\n2. Connect to "InkSlab-Setup"\\n3. Open 10.42.0.1 in your web browser (Safari, Chrome, etc.)\\n\\nContinue?')) return;
  var el = document.getElementById('wifi-info');
  fetch(API + '/api/wifi/disconnect', {method:'POST'}).then(function() {
    el.innerHTML = '<strong>Setup mode active</strong><br>1. On your phone, go to WiFi settings and connect to <strong>InkSlab-Setup</strong><br>2. Open <strong>http://10.42.0.1</strong> in your web browser';
    showToast('Setup hotspot started!', 3000);
  }).catch(function() { showToast('Failed to start WiFi setup'); });
}

// --- Collection ---
var _deleteConfirmId = null;
function deleteSeriesStep(setId, name, tcg) {
  var btn = document.getElementById('delbtn-' + setId);
  if (!btn) return;
  if (_deleteConfirmId === setId) {
    // Second click - confirm delete
    var tcg = tcg || getEffectiveBrowseTcg();
    fetch(API + '/api/delete_series', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({tcg: tcg, set_id: setId})})
      .then(r => r.json()).then(function(d) {
        if (d.ok) {
          showToast('Deleted: ' + name, 2000);
          _deleteConfirmId = null;
          _cache.sets = {};
          loadSets();
        } else {
          showToast('Error: ' + (d.error || 'Unknown'), 3000);
        }
      }).catch(function() { showToast('Delete failed'); });
  } else {
    // First click - turn red
    if (_deleteConfirmId) {
      var prev = document.getElementById('delbtn-' + _deleteConfirmId);
      if (prev) { prev.style.background = 'var(--bg-input)'; prev.style.color = 'var(--text-dim)'; prev.textContent = 'Delete'; }
    }
    _deleteConfirmId = setId;
    btn.style.background = 'var(--danger)';
    btn.style.color = 'var(--text-hi)';
    btn.textContent = 'Confirm?';
    // Auto-reset after 4 seconds
    setTimeout(function() {
      if (_deleteConfirmId === setId) {
        _deleteConfirmId = null;
        btn.style.background = 'var(--bg-input)';
        btn.style.color = 'var(--text-dim)';
        btn.textContent = 'Delete';
      }
    }, 4000);
  }
}

function loadSets() {
  var el = document.getElementById('sets-list');
  if (!el) return;
  var tcg = getEffectiveBrowseTcg();
  if (_cache.sets[tcg]) {
    renderSets(el, _cache.sets[tcg], tcg);
  } else {
    try {
      var stored = localStorage.getItem('inkslab_sets_' + tcg);
      if (stored) renderSets(el, JSON.parse(stored), tcg);
      else el.innerHTML = '<div style="color:var(--text-dim);padding:16px;text-align:center"><span class="preview-spin" style="font-size:20px">&#8635;</span></div>';
    } catch(e) {
      el.innerHTML = '<div style="color:var(--text-dim);padding:16px;text-align:center"><span class="preview-spin" style="font-size:20px">&#8635;</span></div>';
    }
  }
  fetch(API + '/api/sets?tcg=' + encodeURIComponent(tcg)).then(r => r.json()).then(sets => {
    _cache.sets[tcg] = sets;
    try { localStorage.setItem('inkslab_sets_' + tcg, JSON.stringify(sets)); } catch(e) { console.warn('localStorage quota exceeded, sets not cached locally'); }
    if (tcg === getEffectiveBrowseTcg()) renderSets(el, sets, tcg);
  }).catch(function() {
    if (!_cache.sets[tcg]) el.innerHTML = '<div style="color:var(--text-dim);padding:16px;text-align:center">Failed to load sets</div>';
  });
}

function renderSets(el, sets, tcg) {
  if (!sets.length) { el.innerHTML = '<div style="color:var(--text-dim);padding:16px;text-align:center">No cards downloaded yet.</div>'; return; }
  sets = sets.slice().sort((a, b) => a.name.localeCompare(b.name));
  el.innerHTML = sets.map(s => `
    <div class="set-item">
      <div class="set-header" onclick="toggleSet('${esc(s.id)}')">
        <span>
          <span class="set-name">${esc(s.name)}</span>
          ${s.owned_count > 0 ? '<span class="badge">' + s.owned_count + '</span>' : ''}
        </span>
        <span style="display:flex;align-items:center;gap:8px;"><span class="set-meta">${esc(s.year)} &middot; ${s.card_count} cards</span><button id="delbtn-${esc(s.id)}" data-id="${esc(s.id)}" data-name="${esc(s.name)}" data-tcg="${esc(tcg||'')}" onclick="event.stopPropagation();deleteSeriesStep(this.dataset.id,this.dataset.name,this.dataset.tcg)" style="padding:2px 8px;border:none;border-radius:4px;background:var(--bg-input);color:var(--text-dim);font-size:11px;cursor:pointer;">Delete</button></span>
      </div>
      <div class="set-cards" id="set-${esc(s.id)}"></div>
    </div>
  `).join('');
}

function toggleSet(setId) {
  const el = document.getElementById('set-' + setId);
  if (el.classList.contains('open')) { el.classList.remove('open'); return; }
  el.classList.add('open');
  if (el.dataset.loaded) return;
  el.innerHTML = '<div style="padding:8px;color:var(--text-dim);font-size:12px">Loading...</div>';
  fetch(API + '/api/sets/' + setId + '/cards?tcg=' + encodeURIComponent(getEffectiveBrowseTcg())).then(r => r.json()).then(cards => {
    // Re-query live element in case renderSets rebuilt the DOM during the fetch
    var liveEl = document.getElementById('set-' + setId) || el;
    if (!liveEl.classList.contains('open')) return; // was closed while loading
    liveEl.dataset.loaded = '1';
    // Extract unique rarities for chips
    var rarities = [];
    var seen = {};
    cards.forEach(function(c) { if (c.rarity && !seen[c.rarity]) { seen[c.rarity] = 1; rarities.push(c.rarity); } });
    var _jsId = setId.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    let html = '<div style="padding:4px 0 6px;display:flex;gap:4px;flex-wrap:wrap">';
    html += '<button class="btn btn-secondary btn-sm" onclick="toggleSetAll(\'' + _jsId + '\',true)">Select All</button>';
    html += '<button class="btn btn-secondary btn-sm" onclick="toggleSetAll(\'' + _jsId + '\',false)">Deselect All</button>';
    html += '</div>';
    // Per-set rarity chips with counts and toggle state
    if (rarities.length > 1) {
      html += '<div class="rarity-chips">';
      rarities.forEach(function(r) {
        var total = 0, ownedCt = 0;
        cards.forEach(function(c) { if (c.rarity === r) { total++; if (c.owned) ownedCt++; } });
        var isActive = ownedCt > 0;
        var _jsR = r.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        html += '<span class="rarity-chip' + (isActive ? ' active' : '') + '" data-rarity="' + esc(r) + '" onclick="toggleSetRarityChip(this,\'' + _jsId + '\',\'' + _jsR + '\',' + (isActive ? 'false' : 'true') + ')">'
          + esc(r) + '<span class="chip-count">(' + ownedCt + '/' + total + ')</span></span>';
      });
      html += '</div>';
    }
    html += cards.map(c => `
      <div class="card-row" data-rarity="${esc(c.rarity)}">
        <label>
          <input type="checkbox" ${c.owned ? 'checked' : ''} onchange="toggleCard('${esc(c.id)}', this)">
          <span class="card-preview-btn">#${esc(c.number)} ${esc(c.name)}</span>
        </label>
        <span class="card-rarity">${esc(c.rarity)}</span>
      </div>
    `).join('');
    liveEl.innerHTML = html;
  });
}

function toggleCard(cardId, el) {
  var owned = el ? el.checked : null;
  var setItem = el ? el.closest('.set-item') : null;
  var badge = setItem ? setItem.querySelector('.badge') : null;
  var prevBadgeText = badge ? badge.textContent : null;
  // Update badge immediately (optimistic)
  if (setItem) {
    if (owned) {
      if (badge) { badge.textContent = parseInt(badge.textContent) + 1; }
      else { var sn = setItem.querySelector('.set-name'); if (sn) { badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = '1'; sn.after(badge); } }
    } else if (badge) {
      var n = parseInt(badge.textContent) - 1;
      if (n <= 0) badge.remove(); else badge.textContent = n;
    }
  }
  fetch(API + '/api/collection/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({card_id: cardId, owned: owned, tcg: getEffectiveBrowseTcg()})})
    .catch(function() {
      // Revert optimistic updates on failure
      if (el) el.checked = !owned;
      if (setItem) {
        var curBadge = setItem.querySelector('.badge');
        if (owned) {
          if (curBadge) { var m = parseInt(curBadge.textContent) - 1; if (m <= 0) curBadge.remove(); else curBadge.textContent = m; }
        } else {
          if (curBadge) { curBadge.textContent = parseInt(curBadge.textContent) + 1; }
          else if (prevBadgeText) { var sn2 = setItem.querySelector('.set-name'); if (sn2) { var b2 = document.createElement('span'); b2.className = 'badge'; b2.textContent = prevBadgeText; sn2.after(b2); } }
        }
      }
      showToast('Failed to update collection');
    });
}

function toggleSetAll(setId, owned) {
  fetch(API + '/api/collection/toggle_set', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({set_id: setId, owned: owned, tcg: getEffectiveBrowseTcg()})})
    .then(() => {
      const el = document.getElementById('set-' + setId);
      if (!el) return;
      // Update list view checkboxes
      el.querySelectorAll('input[type=checkbox]').forEach(cb => cb.checked = owned);
      // Update grid view thumbnails
      el.querySelectorAll('.grid-thumb').forEach(function(img) {
        var cardId = img.id.replace('gthumb-', '');
        var check = document.getElementById('gcheck-' + cardId);
        if (owned) { img.classList.add('owned'); if (check) check.classList.add('show'); }
        else { img.classList.remove('owned'); if (check) check.classList.remove('show'); }
      });
      // Update the set badge count
      const setItem = el.closest('.set-item');
      if (setItem) {
        const badge = setItem.querySelector('.badge');
        if (owned) {
          const count = el.querySelectorAll('input[type=checkbox]').length || el.querySelectorAll('.grid-thumb').length;
          if (badge) { badge.textContent = count; }
          else if (count > 0) {
            const sn = setItem.querySelector('.set-name');
            if (sn) { const b = document.createElement('span'); b.className = 'badge'; b.textContent = count; sn.after(b); }
          }
        } else if (badge) {
          badge.remove();
        }
      }
    }).catch(function() { showToast('Failed to update collection'); });
}

var _clearCollectionPending = false;
var _clearCollectionTimer = null;
function clearCollection() {
  var btn = document.querySelector('.btn[onclick="clearCollection()"]');
  if (!_clearCollectionPending) {
    _clearCollectionPending = true;
    if (btn) { btn.textContent = 'Confirm'; btn.style.background = 'var(--danger)'; btn.style.color = '#fff'; }
    _clearCollectionTimer = setTimeout(function() {
      _clearCollectionPending = false;
      if (btn) { btn.textContent = 'Clear All'; btn.style.background = ''; btn.style.color = ''; }
    }, 3000);
    return;
  }
  clearTimeout(_clearCollectionTimer);
  _clearCollectionPending = false;
  if (btn) { btn.textContent = 'Clear All'; btn.style.background = ''; btn.style.color = ''; }
  var tcg = getEffectiveBrowseTcg();
  fetch(API + '/api/collection/clear', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({tcg: tcg})}).then(() => {
    _cache.sets = {}; _cache.rarities = {};
    loadSets(); loadRarities();
  }).catch(function() { showToast('Failed to clear collection'); });
}

// --- Rarity filtering ---
var _rarityData = [];

function toggleRarityFilter() {
  var body = document.getElementById('rarity-filter-body');
  var icon = document.getElementById('rarity-toggle-icon');
  if (body.style.display === 'none') {
    body.style.display = 'block';
    icon.textContent = '▲ Hide';
    loadRarities();
  } else {
    body.style.display = 'none';
    icon.textContent = '▼ Show';
  }
}

function loadRarities() {
  var raritySection = document.getElementById('rarity-chips') && document.getElementById('rarity-chips').closest('.card');
  if (raritySection) raritySection.style.display = '';
  var tcg = getEffectiveBrowseTcg();
  if (_cache.rarities[tcg]) { _rarityData = _cache.rarities[tcg]; renderRarityChips(); }
  fetch(API + '/api/rarities?tcg=' + encodeURIComponent(tcg)).then(function(r) { return r.json(); }).then(function(rarities) {
    _cache.rarities[tcg] = rarities;
    _rarityData = rarities;
    renderRarityChips();
  }).catch(function() {});
}

function renderRarityChips() {
  var el = document.getElementById('rarity-chips');
  if (!_rarityData.length) { el.innerHTML = '<span style="color:var(--text-dim);font-size:12px">No cards downloaded yet</span>'; return; }
  el.innerHTML = _rarityData.map(function(r) {
    var sel = r.owned > 0;
    var safeR = r.name.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    return '<span class="rarity-toggle' + (sel ? ' selected' : '') + '" onclick="toggleRarityChip(this,\'' + safeR + '\',' + (sel ? 'false' : 'true') + ')">'
      + '<span class="rt-check">' + (sel ? '&#10003;' : '') + '</span>'
      + esc(r.name)
      + '<span class="rt-count">' + r.owned + '/' + r.count + '</span>'
      + '</span>';
  }).join('');
}

function toggleRarityChip(chipEl, rarity, owned) {
  var resultEl = document.getElementById('rarity-result');
  resultEl.textContent = (owned ? 'Selecting' : 'Deselecting') + ' all ' + rarity + '...';
  chipEl.style.opacity = '0.5';
  fetch(API + '/api/collection/toggle_rarity', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({rarity: rarity, owned: owned, tcg: getEffectiveBrowseTcg()})})
    .then(function(r) { return r.json(); }).then(function(d) {
      resultEl.textContent = (owned ? 'Selected ' : 'Deselected ') + (d.count || 0) + ' ' + rarity + ' cards';
      showToast((owned ? 'Selected ' : 'Deselected ') + (d.count || 0) + ' cards');
      loadRarities();
      // Clear set loaded state so they refresh checkboxes
      document.querySelectorAll('.set-cards').forEach(function(sc) { sc.removeAttribute('data-loaded'); });
      loadSets();
    }).catch(function() { resultEl.textContent = 'Error'; chipEl.style.opacity = '1'; });
}

function selectAllRarities(owned) {
  var resultEl = document.getElementById('rarity-result');
  resultEl.textContent = (owned ? 'Selecting' : 'Deselecting') + ' all...';
  fetch(API + '/api/collection/toggle_all', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({owned: owned, tcg: getEffectiveBrowseTcg()})})
    .then(function(r) { return r.json(); }).then(function(d) {
      resultEl.textContent = (owned ? 'Selected ' : 'Deselected ') + (d.count || 0) + ' cards';
      showToast((owned ? 'Selected ' : 'Deselected ') + (d.count || 0) + ' cards');
      loadRarities();
      document.querySelectorAll('.set-cards').forEach(function(sc) { sc.removeAttribute('data-loaded'); });
      loadSets();
    }).catch(function() { resultEl.textContent = 'Error'; });
}

function toggleSetRarityChip(chipEl, setId, rarity, owned) {
  chipEl.style.opacity = '0.5';
  fetch(API + '/api/collection/toggle_rarity', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({set_id: setId, rarity: rarity, owned: owned, tcg: getEffectiveBrowseTcg()})})
    .then(function(r) { return r.json(); }).then(function(d) {
      if (d.count !== undefined) {
        showToast((owned ? 'Selected ' : 'Deselected ') + d.count + ' ' + rarity + ' cards');
        var el = document.getElementById('set-' + setId);
        if (!el) { chipEl.style.opacity = '1'; return; }
        var total = 0, newOwned = 0;
        el.querySelectorAll('.card-row').forEach(function(row) {
          if (row.dataset.rarity === rarity) {
            var cb = row.querySelector('input[type=checkbox]');
            if (cb) { cb.checked = owned; }
            total++;
            if (owned) newOwned++;
          }
        });
        chipEl.classList.toggle('active', owned);
        chipEl.style.opacity = '1';
        var cs = chipEl.querySelector('.chip-count');
        if (cs) cs.textContent = '(' + newOwned + '/' + total + ')';
        var safeR = rarity.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        var safeSetId = setId.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        chipEl.setAttribute('onclick', "toggleSetRarityChip(this,'" + safeSetId + "','" + safeR + "'," + (!owned) + ")");
      }
    }).catch(function() { chipEl.style.opacity = '1'; });
}

// --- Card preview modal ---
function showPreview(setId, cardId, label, tcg) {
  if (_touchMoved) return;
  var t = tcg || (_lastStatus && _lastStatus.tcg) || 'pokemon';
  var _pi = document.getElementById('preview-img');
  _pi.style.opacity = '0';
  _pi.onload = function() { this.style.opacity = '1'; };
  _pi.src = '/api/card_image/' + t + '/' + setId + '/' + cardId;
  document.getElementById('preview-name').textContent = label;
  document.getElementById('preview-modal').classList.add('open');
}
function showCurrentPreview() {
  if (_touchMoved) return;
  if (!_lastStatus || !_lastStatus.set_id) return;
  showPreview(_lastStatus.set_id, _lastStatus.card_id, (_lastStatus.card_num || '') + ' ' + (_lastStatus.set_info || ''), _lastStatus.tcg);
}
function closePreview() {
  document.getElementById('preview-modal').classList.remove('open');
}

// --- Search ---
var _searchTimer = null;

function debounceSearch() {
  if (_searchTimer) clearTimeout(_searchTimer);
  var clearBtn = document.getElementById('search-clear');
  if (clearBtn) clearBtn.style.display = document.getElementById('search-input').value ? '' : 'none';
  _searchTimer = setTimeout(doSearch, 350);
}

function clearSearch() {
  var inp = document.getElementById('search-input');
  if (inp) { inp.value = ''; inp.focus(); }
  var clearBtn = document.getElementById('search-clear');
  if (clearBtn) clearBtn.style.display = 'none';
  var el = document.getElementById('search-results');
  if (el) el.innerHTML = '';
}

function loadFavorites() {
  fetch(API + '/api/collection/favorites').then(function(r) { return r.json(); }).then(function(favs) {
    var el = document.getElementById('search-filters');
    if (!favs.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
    el.style.display = '';
    el.innerHTML = favs.map(function(name) {
      var safeN = name.replace(/'/g, "\'");
      return '<span class="search-filter-chip">' + name + '<span class="sfc-x" onclick="removeFavorite(\'' + safeN + '\', event)">&times;</span></span>';
    }).join('');
  });
}

function removeFavorite(name, e) {
  var chip = e.target.parentElement;
  chip.style.opacity = '0.5';
  fetch(API + '/api/collection/favorites', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name: name, owned: false})})
    .then(function(r) { return r.json(); }).then(function(d) {
      showToast('Removed ' + (d.count || 0) + ' ' + name + ' cards');
      doSearch();
      loadRarities();
    }).catch(function() { chip.style.opacity = '1'; });
}

function doSearch() {
  var q = document.getElementById('search-input').value.trim();
  var el = document.getElementById('search-results');
  if (q.length < 2) { el.innerHTML = ''; return; }
  el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:8px">Searching...</div>';
  fetch(API + '/api/search?q=' + encodeURIComponent(q) + '&tcg=' + encodeURIComponent(getEffectiveBrowseTcg())).then(function(r) { return r.json(); }).then(function(data) {
    var results = data.results;
    if (!results.length) { el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:8px">No results found (searched ' + data.sets_searched + ' sets)</div>'; return; }
    var groups = {};
    results.forEach(function(c) {
      var key = c.name.toLowerCase();
      if (!groups[key]) groups[key] = {name: c.name, cards: []};
      groups[key].cards.push(c);
    });
    var header = '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px">' + data.total + ' results across ' + data.sets_searched + ' sets';
    if (data.total > results.length) header += ' (showing ' + results.length + ')';
    header += '</div>';
    var html = header;
    Object.values(groups).sort(function(a, b) { return b.cards.length - a.cards.length; }).forEach(function(g) {
      var allOwned = g.cards.every(function(c) { return c.owned; });
      var ownedCount = g.cards.filter(function(c) { return c.owned; }).length;
      html += '<div class="search-group" style="border-bottom:1px solid var(--border);padding:6px 0">';
      html += '<div class="search-group-header">';
      html += '<span class="search-result-name">' + esc(g.name) + ' <span class="search-owned-count" style="color:var(--text-dim);font-size:11px;font-weight:400">' + ownedCount + '/' + g.cards.length + ' owned</span></span>';
      html += '<button class="btn btn-secondary btn-sm search-group-btn" data-name="' + esc(g.name) + '" data-owned="' + (!allOwned) + '">' + (allOwned ? 'Remove All' : 'Add All') + '</button>';
      html += '</div>';
      html += '<div style="margin-top:4px">';
      g.cards.forEach(function(c) {
        html += '<div class="search-result"><label style="display:flex;align-items:center;gap:6px;flex:1;cursor:pointer">';
        html += '<input type="checkbox" ' + (c.owned ? 'checked' : '') + ' onchange="toggleCard(\'' + esc(c.id) + '\', this)" style="accent-color:var(--accent)">';
        html += '<span><span class="card-preview-btn">#' + esc(c.number) + '</span>';
        html += ' <span class="search-result-set">' + esc(c.set_name) + '</span></span>';
        html += '</label><span class="search-result-rarity">' + esc(c.rarity) + '</span></div>';
      });
      html += '</div></div>';
    });
    el.innerHTML = html;
  }).catch(function() { el.innerHTML = '<div style="color:#ff6b6b;font-size:12px;padding:8px">Search failed</div>'; });
}

function toggleSearchGroup(btn, name, owned) {
  btn.disabled = true;
  btn.textContent = owned ? 'Adding...' : 'Removing...';
  fetch(API + '/api/collection/favorites', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name: name, owned: owned, tcg: getEffectiveBrowseTcg()})})
    .then(function(r) { return r.json(); }).then(function(d) {
      showToast((owned ? 'Added ' : 'Removed ') + (d.count || 0) + ' ' + name + ' cards');
      btn.disabled = false;
      btn.textContent = owned ? 'Remove All' : 'Add All';
      btn.dataset.owned = (!owned).toString();
      var group = btn.closest('.search-group');
      if (group) {
        group.querySelectorAll('input[type=checkbox]').forEach(function(cb) { cb.checked = owned; });
        var total = group.querySelectorAll('input[type=checkbox]').length;
        var nowOwned = owned ? total : 0;
        var countEl = group.querySelector('.search-owned-count');
        if (countEl) countEl.textContent = nowOwned + '/' + total + ' owned';
      }
      _cache.sets = {};
      loadSets();
    }).catch(function() { btn.disabled = false; btn.textContent = owned ? 'Add All' : 'Remove All'; });
}

// --- Downloads ---
function _fmtGb(gb) {
  if (gb >= 10)  return gb.toFixed(0) + ' GB';
  return gb.toFixed(1) + ' GB';
}
function _fmtMb(mb) {
  if (mb >= 10) return Math.round(mb) + ' MB';
  return mb.toFixed(1) + ' MB';
}
function fmtSize(gb, mb) {
  if (gb >= 1 || mb >= 1000) return _fmtGb(gb >= 1 ? gb : mb / 1024);
  if (mb > 0) return _fmtMb(mb);
  return '0 MB';
}
function fmtSizeShort(gb, mb) {
  if (gb >= 100) return gb.toFixed(0) + 'G';
  if (gb >= 10)  return gb.toFixed(1) + 'G';
  if (gb >= 1)   return gb.toFixed(2) + 'G';
  if (mb >= 1000) return (mb / 1024).toFixed(2) + 'G';
  if (mb > 0) return mb + 'M';
  return '';
}
function fmtCount(n) { return (n || 0).toLocaleString(); }
function loadStorage() {
  fetch(API + '/api/storage').then(function(r) { return r.json(); }).then(function(info) {
    var el = document.getElementById('storage-info');
    if (info._computing) {
      el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:12px"><span class="preview-spin" style="display:inline-block;font-size:18px">&#8635;</span><div style="margin-top:6px">Calculating storage...</div></div>';
      setTimeout(loadStorage, 3000);
      return;
    }
    if (!info._disk) { el.innerHTML = '<div style="color:var(--text-dim)">Loading...</div>'; setTimeout(loadStorage, 3000); return; }
    var totalGb = info._disk.total_gb || 1;
    var freeGb = info._disk.free_gb || 0;
    // Dynamic: sum up all TCG sizes
    var tcgEntries = Object.entries(info).filter(function(e) { return !e[0].startsWith('_'); }).sort(function(a, b) {
      if (a[0] === 'custom') return -1;
      if (b[0] === 'custom') return 1;
      var na = _tcgRegistry[a[0]] ? _tcgRegistry[a[0]].name : a[0];
      var nb = _tcgRegistry[b[0]] ? _tcgRegistry[b[0]].name : b[0];
      return na.localeCompare(nb);
    });
    var tcgTotalGb = 0;
    tcgEntries.forEach(function(e) { tcgTotalGb += (e[1].size_gb || 0); });
    var usedGb = Math.round((totalGb - freeGb) * 100) / 100;
    var thumbGb = (info._thumbcache && info._thumbcache.cached > 0) ? Math.max(info._thumbcache.size_mb / 1024, 0.001) : 0;
    var otherGb = Math.max(0, Math.round((usedGb - tcgTotalGb - thumbGb) * 100) / 100);
    var otherPct = (otherGb / totalGb * 100);
    var freePct = (freeGb / totalGb * 100);
    var html = '<div class="storage-bar-wrap">';
    html += '<div class="storage-bar-label"><span>' + usedGb.toFixed(1) + ' GB used</span><span>' + freeGb.toFixed(1) + ' GB free / ' + totalGb.toFixed(0) + ' GB</span></div>';
    html += '<div class="storage-bar">';
    tcgEntries.forEach(function(e) {
      var tcg = e[0], d = e[1];
      var gb = d.size_gb || 0;
      if (gb <= 0) return;
      var pct = Math.max(gb / totalGb * 100, 1.5);
      var color = (_tcgRegistry[tcg] && _tcgRegistry[tcg].color) || '#888';
      html += '<div class="storage-seg" style="width:' + pct.toFixed(1) + '%;background:' + color + '">' + (pct > 8 ? fmtSizeShort(gb, d.size_mb || 0) : '') + '</div>';
    });
    if (thumbGb > 0) { var thumbPct = Math.max(thumbGb / totalGb * 100, 1.5); html += '<div class="storage-seg" style="width:' + thumbPct.toFixed(1) + '%;background:#8B5CF6">' + (thumbPct > 8 ? (info._thumbcache.size_mb + 'M') : '') + '</div>'; }
    if (otherPct > 0.5) html += '<div class="storage-seg seg-other" style="width:' + otherPct.toFixed(1) + '%">' + (otherPct > 8 ? otherGb.toFixed(1) + 'G' : '') + '</div>';
    html += '<div class="storage-seg seg-free" style="width:' + Math.max(freePct, 1).toFixed(1) + '%">' + (freePct > 12 ? freeGb.toFixed(1) + 'G' : '') + '</div>';
    html += '</div>';
    html += '<div class="storage-legend">';
    tcgEntries.forEach(function(e) {
      var tcg = e[0];
      var color = (_tcgRegistry[tcg] && _tcgRegistry[tcg].color) || '#888';
      var name = (_tcgRegistry[tcg] && _tcgRegistry[tcg].name) || tcg.toUpperCase();
      html += '<div class="storage-legend-item"><span class="storage-legend-dot" style="background:' + color + '"></span>' + name + '</div>';
    });
    if (thumbGb > 0) html += '<div class="storage-legend-item"><span class="storage-legend-dot" style="background:#8B5CF6"></span>Image Cache</div>';
    html += '<div class="storage-legend-item"><span class="storage-legend-dot" style="background:#E8786B"></span>System</div>';
    html += '<div class="storage-legend-item"><span class="storage-legend-dot" style="background:var(--bg-input);border:1px solid var(--border-hi)"></span>Free</div>';
    html += '</div></div>';
    tcgEntries.forEach(function(e) {
      var tcg = e[0], d = e[1];
      var name = (_tcgRegistry[tcg] && _tcgRegistry[tcg].name) || tcg.toUpperCase();
      html += '<div class="stat"><span class="stat-label">' + name + '</span><span class="stat-value">' + d.card_count + ' cards &middot; ' + d.set_count + ' sets &middot; ' + fmtSize(d.size_gb || 0, d.size_mb || 0) + '</span></div>';
    });
    if (info._thumbcache) {
      var tc = info._thumbcache;
      var cacheVal = tc.cached + ' / ' + tc.total + ' cached';
      if (tc.size_mb > 0) cacheVal += ' &middot; ' + _fmtMb(tc.size_mb);
      html += '<div class="stat"><span class="stat-label">Image Cache</span><span class="stat-value">' + cacheVal + '</span></div>';
    }
    el.innerHTML = html;
  });
}

function _dlInputChange(inp) {
  var btn = inp.parentNode.querySelector('.search-clear-btn');
  if (btn) btn.style.display = inp.value ? '' : 'none';
}
function _dlClearInput(inputId, resultsId) {
  var inp = document.getElementById(inputId);
  if (inp) { inp.value = ''; inp.dispatchEvent(new Event('input')); }
  var res = document.getElementById(resultsId);
  if (res) { res.style.display = 'none'; res.innerHTML = ''; }
}
function closeAllDlSearch() {
  ['dl-lorcana-search','dl-mtg-search','dl-pokemon-search','dl-manga-search','dl-comics-search'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  document.querySelectorAll('[data-search-btn]').forEach(function(b) {
    var c = b.getAttribute('data-color');
    b.style.background = c;
    b.style.color = 'var(--bg)';
    b.style.border = 'none';
  });
}

function toggleDlSearch(panelId, btn) {
  var panel = document.getElementById(panelId);
  if (!panel) return;
  var wasOpen = panel.style.display !== 'none';
  // Close all panels and reset all search buttons (accordion)
  ['dl-lorcana-search','dl-mtg-search','dl-pokemon-search','dl-manga-search','dl-comics-search'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  document.querySelectorAll('[data-search-btn]').forEach(function(b) {
    var c = b.getAttribute('data-color');
    b.style.background = c;
    b.style.color = 'var(--bg)';
    b.style.border = 'none';
  });
  // Open this one if it was closed
  if (!wasOpen) {
    panel.style.display = 'block';
    if (btn) {
      var color = btn.getAttribute('data-color');
      btn.style.background = 'transparent';
      btn.style.color = color;
      btn.style.border = '1px solid ' + color;
    }
  }
}

function setDownloadUI(running, tcg) {
  const btns = document.getElementById('dl-action-btns');
  const stopBtn = document.getElementById('btn-dl-stop');
  if (running) {
    if (btns) btns.querySelectorAll('.btn').forEach(b => b.disabled = true);
    stopBtn.style.display = 'block';
    stopBtn.textContent = 'Stop ' + (tcg || '').toUpperCase() + ' Download';
  } else {
    if (btns) btns.querySelectorAll('.btn').forEach(b => b.disabled = false);
    stopBtn.style.display = 'none';
  }
}

function startDownload(tcg, since) {
  const body = {tcg: tcg};
  if (since) body.since = parseInt(since);
  fetch(API + '/api/download/start', {method:'POST', body: JSON.stringify(body)})
    .then(r => r.json()).then(d => {
      if (d.ok) {
        document.getElementById('dl-status').textContent = 'Downloading ' + tcg.toUpperCase() + '...';
        var log = document.getElementById('dl-log');
        var btn = document.getElementById('btn-dl-log-toggle');
        if (log) { log.style.display = 'block'; if (btn) btn.textContent = 'Hide Log'; }
        setDownloadUI(true, tcg);
        pollDownload();
      } else {
        showToast(d.error || 'Failed to start download');
      }
    }).catch(function() { showToast('Failed to start download'); });
}

function stopDownload() {
  fetch(API + '/api/download/stop', {method:'POST'}).then(r => r.json()).then(d => {
    if (d.ok) {
      document.getElementById('dl-status').textContent = 'Download stopped.';
      setDownloadUI(false);
      loadStorage();
    }
  }).catch(function() { showToast('Failed to stop download'); });
}

let _dlPoll = null;
function pollDownload() {
  if (_dlPoll) clearInterval(_dlPoll);
  checkDownload();
  _dlPoll = setInterval(checkDownload, 2000);
}
function checkDownload() {
  fetch(API + '/api/download/status').then(r => r.json()).then(d => {
    const logEl = document.getElementById('dl-log');
    var lines = d.lines.length ? d.lines : ['No output yet.'];
    // Strip tqdm progress bar lines (contain \r or lots of █ / % characters mid-line)
    lines = lines.filter(function(l) { return l.trim() && !/^\s*[\d]+%\|/.test(l) && !/\r/.test(l); });
    logEl.innerHTML = lines.map(function(l) {
      var clean = l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      var style = 'color:#FCFDF0';
      if (/error|fail|exception/i.test(l)) style = 'color:#FF6B6B;font-weight:600';
      else if (/warning|warn/i.test(l)) style = 'color:#FACC15';
      else if (/done|complete|finish|success|saved|total/i.test(l)) style = 'color:var(--accent2);font-weight:600';
      else if (/downloading|fetching|processing|writing/i.test(l)) style = 'color:var(--accent)';
      else if (/^\[|\bINFO\b|\bDEBUG\b/.test(l)) style = 'color:#aaa';
      return '<span style="' + style + '">' + clean + '</span>';
    }).join('\n');
    logEl.scrollTop = logEl.scrollHeight;
    if (d.running) {
      document.getElementById('dl-status').textContent = 'Downloading ' + (d.tcg || '').toUpperCase() + '...';
      setDownloadUI(true, d.tcg);
    } else {
      document.getElementById('dl-status').textContent = 'Idle';
      setDownloadUI(false);
      if (_dlPoll) { clearInterval(_dlPoll); _dlPoll = null; loadStorage(); }
    }
  });
}

function deleteData(tcg, btn) {
  if (!confirm('Delete ALL ' + tcg.toUpperCase() + ' card images? This cannot be undone.')) return;
  var origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Deleting...';
  fetch(API + '/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({tcg: tcg})})
    .then(r => r.json()).then(d => {
      btn.disabled = false;
      btn.textContent = origText;
      if (d.ok) { showToast(tcg.toUpperCase() + ' data deleted'); loadStorage(); }
      else showToast(d.error || 'Delete failed');
    }).catch(function() {
      btn.disabled = false;
      btn.textContent = origText;
      showToast('Delete failed');
    });
}

// --- OTA Update ---
function checkUpdate() {
  var el = document.getElementById('update-info');
  el.textContent = 'Checking...';
  fetch(API + '/api/update/check', {method:'POST'}).then(r => r.json()).then(d => {
    if (!d.ok) { el.textContent = 'Error: ' + (d.error || 'unknown'); return; }
    if (d.up_to_date) {
      el.innerHTML = 'Up to date! <span style="color:var(--text-dim)">Version: ' + esc(d.local) + '</span>';
      document.getElementById('btn-update-now').style.display = 'none';
    } else {
      el.innerHTML = esc(String(d.behind)) + ' update' + (d.behind > 1 ? 's' : '') + ' available. <span style="color:var(--text-dim)">Current: ' + esc(d.local) + ' &rarr; Latest: ' + esc(d.remote) + '</span>';
      document.getElementById('btn-update-now').style.display = 'block';
    }
  }).catch(function() { el.textContent = 'Failed to check. Is the Pi online?'; });
}

function startUpdate() {
  if (!confirm('Update InkSlab? The display and web dashboard will restart.')) return;
  document.getElementById('update-progress').style.display = 'block';
  document.getElementById('update-stage').textContent = 'Starting update...';
  document.getElementById('update-bar').style.width = '10%';
  document.getElementById('btn-update-now').style.display = 'none';
  fetch(API + '/api/update/start', {method:'POST'}).then(r => r.json()).then(d => {
    if (d.ok) { pollUpdate(); }
    else { document.getElementById('update-stage').textContent = 'Error: ' + (d.error || 'unknown'); }
  }).catch(function() { document.getElementById('update-stage').textContent = 'Failed to start update'; });
}

var _updatePoll = null;
function pollUpdate() {
  if (_updatePoll) clearInterval(_updatePoll);
  _updatePoll = setInterval(checkUpdateStatus, 2000);
}
function checkUpdateStatus() {
  fetch(API + '/api/update/status').then(r => r.json()).then(d => {
    var bar = document.getElementById('update-bar');
    var stage = document.getElementById('update-stage');
    var stages = {fetching: 20, pulling: 40, restarting_display: 60, restarting_web: 80, complete: 100};
    bar.style.width = (stages[d.stage] || 10) + '%';
    stage.textContent = d.message || d.stage || 'Working...';
    if (d.stage === 'complete') {
      clearInterval(_updatePoll); _updatePoll = null;
      showToast('Update complete!');
      // Force cache-bypass reload so new JS/CSS is always loaded after an update
      setTimeout(function() { location.href = location.origin + '/?updated=' + Date.now(); }, 2000);
    } else if (d.error) {
      clearInterval(_updatePoll); _updatePoll = null;
      stage.textContent = d.message || 'Update failed';
      bar.style.background = 'var(--danger)';
    }
  }).catch(function() {
    document.getElementById('update-stage').textContent = 'Reconnecting...';
  });
}

// --- Custom Images ---
function loadCustomFolders(cb) {
  fetch(API + '/api/custom/folders').then(r => r.json()).then(folders => {
    var el = document.getElementById('custom-folders');
    if (!el) return;
    if (!folders.length) { el.innerHTML = '<div style="color:var(--text-dim);font-size:12px">No custom folders yet. Create one above.</div>'; if (cb) cb(); return; }
    el.innerHTML = folders.map(f => {
      return '<div class="set-item"><div class="set-header" onclick="toggleCustomFolder(\'' + esc(f.id) + '\')">'
        + '<span><span class="set-name">' + esc(f.name) + '</span></span>'
        + '<span class="set-meta">' + f.card_count + ' cards</span>'
        + '</div><div class="set-cards" id="cf-' + esc(f.id) + '"></div></div>';
    }).join('');
    if (cb) cb();
  }).catch(function() { showToast('Failed to load custom folders'); });
}

function refreshCustomFolder(folderId) {
  var el = document.getElementById('cf-' + folderId);
  if (!el) return;
  el.removeAttribute('data-loaded');
  el.classList.add('open');
  _loadCustomFolderContent(folderId, el);
}

function toggleCustomFolder(folderId) {
  var el = document.getElementById('cf-' + folderId);
  if (el.classList.contains('open')) { el.classList.remove('open'); return; }
  el.classList.add('open');
  if (el.dataset.loaded) return;
  _loadCustomFolderContent(folderId, el);
}

function _loadCustomFolderContent(folderId, el) {
  el.innerHTML = '<div style="padding:8px;color:var(--text-dim);font-size:12px">Loading...</div>';
  fetch(API + '/api/sets/' + folderId + '/cards?tcg=custom').then(r => r.json()).then(cards => {
    el.dataset.loaded = '1';
    var html = '<div style="padding:6px 0;display:flex;gap:4px;flex-wrap:wrap;align-items:center">';
    html += '<label class="btn btn-secondary btn-sm" style="cursor:pointer">Upload <input type="file" accept="image/png,image/jpeg" multiple style="display:none" onchange="uploadCustomCards(\'' + esc(folderId) + '\',this.files)"></label>';
    html += '<button class="btn btn-secondary btn-sm" onclick="renameCustomFolder(\'' + esc(folderId) + '\')">Rename</button>';
    html += '<button class="btn btn-danger btn-sm" onclick="deleteCustomFolder(\'' + esc(folderId) + '\')">Delete Set</button>';
    html += '</div>';
    if (cards.length) {
      cards.forEach(c => {
        html += '<div class="card-row"><label style="flex:1;cursor:pointer">';
        html += '<span class="card-preview-btn">#' + esc(c.number) + ' ' + esc(c.name) + '</span>';
        html += '</label>';
        html += '<span style="display:flex;gap:4px;align-items:center">';
        html += '<span class="card-rarity">' + esc(c.rarity || '') + '</span>';
        html += '<span style="cursor:pointer;color:var(--text-dim);font-size:11px" onclick="editCustomCard(\'' + esc(folderId) + '\',\'' + esc(c.id) + '\',\'' + esc(c.name||'') + '\',\'' + esc(c.number) + '\',\'' + esc(c.rarity||'') + '\')">edit</span>';
        html += '<span style="cursor:pointer;color:#ff6b6b;font-size:11px" onclick="deleteCustomCard(\'' + esc(folderId) + '\',\'' + esc(c.id) + '\')">x</span>';
        html += '</span></div>';
      });
    } else {
      html += '<div style="color:var(--text-dim);font-size:12px;padding:8px">No images yet. Upload some!</div>';
    }
    el.innerHTML = html;
  });
}

function createCustomFolder() {
  var name = document.getElementById('custom-folder-name').value.trim();
  if (!name) { showToast('Enter a folder name'); return; }
  fetch(API + '/api/custom/create_folder', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name: name})})
    .then(r => r.json()).then(d => {
      if (d.ok) { document.getElementById('custom-folder-name').value = ''; loadCustomFolders(); showToast('Created ' + name); }
      else showToast(d.error || 'Failed');
    }).catch(function() { showToast('Failed to create folder'); });
}

function uploadCustomCards(folderId, files) {
  if (!files.length) return;
  var done = 0;
  showToast('Uploading ' + files.length + ' file(s)...');
  Array.from(files).forEach(function(file) {
    var fd = new FormData();
    fd.append('folder', folderId);
    fd.append('file', file);
    fetch(API + '/api/custom/upload', {method:'POST', body: fd}).then(r => r.json()).then(function() {
      done++;
      if (done >= files.length) {
        showToast('Uploaded ' + done + ' file(s)');
        loadCustomFolders(function() { refreshCustomFolder(folderId); });
      }
    }).catch(function() { showToast('Upload failed'); });
  });
}

function renameCustomFolder(folderId) {
  var newName = prompt('New name for this set:');
  if (!newName) return;
  fetch(API + '/api/custom/rename_folder', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: folderId, name: newName})})
    .then(r => r.json()).then(d => { if (d.ok) { loadCustomFolders(); showToast('Renamed'); } else showToast(d.error || 'Rename failed'); })
    .catch(function() { showToast('Rename failed'); });
}

function deleteCustomFolder(folderId) {
  if (!confirm('Delete this entire custom set and all its images?')) return;
  fetch(API + '/api/custom/folder/' + folderId, {method:'DELETE'}).then(r => r.json()).then(d => {
    if (d.ok) { loadCustomFolders(); loadStorage(); showToast('Deleted'); }
    else showToast(d.error || 'Delete failed');
  }).catch(function() { showToast('Delete failed'); });
}

function deleteCustomCard(folderId, cardId) {
  if (!confirm('Delete this image?')) return;
  fetch(API + '/api/custom/card/' + folderId + '/' + cardId, {method:'DELETE'}).then(r => r.json()).then(d => {
    if (d.ok) { refreshCustomFolder(folderId); loadCustomFolders(); showToast('Deleted'); }
    else showToast(d.error || 'Delete failed');
  }).catch(function() { showToast('Delete failed'); });
}

function editCustomCard(folderId, cardId, name, number, rarity) {
  var newName = prompt('Card name:', name);
  if (newName === null) return;
  var newNum = prompt('Card number:', number);
  if (newNum === null) return;
  var newRarity = prompt('Rarity (optional):', rarity);
  if (newRarity === null) return;
  fetch(API + '/api/custom/card_metadata', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({folder: folderId, card_id: cardId, name: newName, number: newNum, rarity: newRarity})})
    .then(r => r.json()).then(d => {
      if (d.ok) { refreshCustomFolder(folderId); showToast('Updated'); }
      else showToast(d.error || 'Update failed');
    }).catch(function() { showToast('Update failed'); });
}

// --- Dynamic TCG UI ---
var _tcgRegistry = {};

var _delConfirmTcg = null;
var _delConfirmTimer = null;

function buildDynamicUI(registry) {
  _tcgRegistry = registry;
  window._tcgRegistry = registry;
  var sorted = Object.entries(registry).sort(function(a, b) {
    if (a[0] === 'custom') return -1;
    if (b[0] === 'custom') return 1;
    return a[1].name.localeCompare(b[1].name);
  });
  // Quick Switch buttons — populate both mobile (#quick-switch-btns) and sidebar (#sb-quick-switch-btns)
  var shortNames = {lorcana: 'Lorcana', mtg: 'Magic', pokemon: 'Pokemon', manga: 'Manga', comics: 'Comics', custom: 'Custom'};
  [document.getElementById('quick-switch-btns'), document.getElementById('sb-quick-switch-btns')].forEach(function(qsEl) {
    if (!qsEl) return;
    qsEl.innerHTML = '';
    sorted.forEach(function(e) {
      var color = e[1].color || '#36A5CA';
      var b = document.createElement('button');
      b.className = 'btn';
      b.dataset.tcg = e[0];
      b.dataset.color = color;
      b.style.cssText = 'background:transparent;color:' + color + ';border:1px solid ' + color + ';white-space:nowrap;';
      b.textContent = shortNames[e[0]] || e[1].name;
      b.addEventListener('mouseover', function() { if (b.dataset.tcg !== (_lastStatus.tcg||'')) { b.style.background = color; b.style.color = 'var(--bg)'; } });
      b.addEventListener('mouseout', function() { if (b.dataset.tcg !== (_lastStatus.tcg||'')) { b.style.background = 'transparent'; b.style.color = color; } });
      b.addEventListener('click', function() { switchTCG(e[0], b); });
      qsEl.appendChild(b);
    });
  });
  updateQuickSwitchActive(_lastStatus.tcg || '');
  // Browse TCG source picker in Collection tab (single pill selector + dropdown)
  var pillsEl = document.getElementById('tcg-browse-pills');
  if (pillsEl) {
    pillsEl.innerHTML = '';
    pillsEl.className = 'source-picker';
    var shortN = {lorcana:'Lorcana',mtg:'Magic',pokemon:'Pokemon',manga:'Manga',comics:'Comics',custom:'Custom'};
    var btn = document.createElement('button');
    btn.id = 'source-pill-btn';
    btn.className = 'source-pill-btn';
    btn.type = 'button';
    var lbl = document.createElement('span');
    lbl.className = 'source-pill-label';
    btn.appendChild(lbl);
    var chev = document.createElement('span');
    chev.className = 'source-pill-chevron';
    chev.textContent = '\u25BC';
    btn.appendChild(chev);
    var dd = document.createElement('div');
    dd.id = 'source-dd';
    dd.className = 'source-dd';
    dd.style.display = 'none';
    sorted.forEach(function(e) {
      var tcg = e[0], info = e[1];
      var color = info.color || '#36A5CA';
      var item = document.createElement('div');
      item.className = 'source-dd-item';
      item.dataset.tcg = tcg;
      var idot = document.createElement('span');
      idot.className = 'source-dot';
      idot.style.background = color;
      item.appendChild(idot);
      item.appendChild(document.createTextNode(shortN[tcg] || info.name));
      item.addEventListener('click', function() { closeSourceDropdown(); setBrowseTcg(tcg); });
      dd.appendChild(item);
    });
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (dd.style.display !== 'none') { closeSourceDropdown(); } else { dd.style.display = 'block'; btn.classList.add('open'); }
    });
    document.addEventListener('click', function(e) {
      if (!pillsEl.contains(e.target)) closeSourceDropdown();
    });
    pillsEl.appendChild(btn);
    pillsEl.appendChild(dd);
    updateBrowsePills(getEffectiveBrowseTcg());
  }
  // Settings TCG dropdown
  var sel = document.getElementById('cfg-tcg');
  sel.innerHTML = sorted.map(function(e) {
    return '<option value="' + e[0] + '">' + e[1].name + '</option>';
  }).join('');
  // Download picker (pill selector + action buttons) — built by dl_picker.js
  if (window.initDlPicker) initDlPicker(sorted);
  // Mobile Quick Switch bottom sheet — built by mobile_qs.js
  if (window.initMobileQS) { initMobileQS(sorted); if (window._mobileQSHook) _mobileQSHook(_lastStatus.tcg || ''); }
  // Delete Entire Library buttons — 2-col grid, two-step confirm
  var delEl = document.getElementById('delete-buttons');
  if (delEl) {
    delEl.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:8px;';
    delEl.innerHTML = '';
    sorted.forEach(function(e) {
      var tcg = e[0];
      var b = document.createElement('button');
      b.id = 'delLib-' + tcg;
      b.className = 'btn btn-sm btn-block';
      b.style.cssText = 'background:transparent;color:var(--danger);border:1px solid var(--danger);';
      b.textContent = 'Delete ' + e[1].name;
      b.addEventListener('mouseover', function() {
        if (_delConfirmTcg !== tcg) { b.style.background = 'var(--danger)'; b.style.color = 'var(--bg)'; }
      });
      b.addEventListener('mouseout', function() {
        if (_delConfirmTcg !== tcg) { b.style.background = 'transparent'; b.style.color = 'var(--danger)'; }
      });
      b.addEventListener('click', function() {
        if (_delConfirmTimer) clearTimeout(_delConfirmTimer);
        if (_delConfirmTcg && _delConfirmTcg !== tcg) {
          var old = document.getElementById('delLib-' + _delConfirmTcg);
          if (old) { old.textContent = 'Delete ' + registry[_delConfirmTcg].name; old.style.background = 'transparent'; old.style.color = '#EF4444'; }
          _delConfirmTcg = null;
        }
        if (_delConfirmTcg === tcg) {
          _delConfirmTcg = null;
          b.textContent = 'Deleting...';
          b.disabled = true;
          fetch(API + '/api/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({tcg: tcg})})
            .then(function(r) { return r.json(); }).then(function(d) {
              b.disabled = false;
              b.textContent = 'Delete ' + e[1].name;
              b.style.background = 'transparent'; b.style.color = 'var(--danger)';
              if (d.ok) { showToast(e[1].name + ' library deleted'); loadStorage(); }
              else showToast(d.error || 'Delete failed');
            }).catch(function() {
              b.disabled = false;
              b.textContent = 'Delete ' + e[1].name;
              b.style.background = 'transparent'; b.style.color = 'var(--danger)';
              showToast('Delete failed');
            });
        } else {
          _delConfirmTcg = tcg;
          b.style.background = 'var(--danger)'; b.style.color = 'var(--bg)';
          b.textContent = 'Confirm Delete?';
          _delConfirmTimer = setTimeout(function() {
            b.textContent = 'Delete ' + e[1].name;
            b.style.background = 'transparent'; b.style.color = 'var(--danger)';
            _delConfirmTcg = null;
          }, 4000);
        }
      });
      delEl.appendChild(b);
    });
  }
}

// --- Init ---
function initApp() {
  // Fetch registry and status in parallel so _lastStatus is ready before showing collection tab
  Promise.all([
    fetch(API + '/api/tcg_list').then(r => r.json()),
    fetch(API + '/api/status').then(r => r.json()),
  ]).then(function(results) {
    var registry = results[0], status = results[1];
    _lastStatus = status;
    buildDynamicUI(registry);
    // Wrap sets-list in a scroll container for max-height + fade hint
    var sl = document.getElementById('sets-list');
    if (sl && !sl.parentElement.classList.contains('sets-scroll-wrap')) {
      var wrap = document.createElement('div');
      wrap.className = 'sets-scroll-wrap';
      sl.parentNode.insertBefore(wrap, sl);
      wrap.appendChild(sl);
    }
    const saved = localStorage.getItem('inkslab_tab');
    if (saved && document.getElementById('tab-' + saved)) {
      showTab(saved);
    }
    document.body.classList.remove('auth-pending');
    refreshStatus();
    startMainPoll();
    startCountdown();
    fetch(API + '/api/ip').then(r => r.json()).then(d => {
      var sd = document.getElementById('status-dot');
      var st = document.getElementById('status-text');
      var sbSt = document.getElementById('sb-status-text');
      if (d.ip) {
        if (sd) sd.className = 'status-dot';
        if (st) st.textContent = d.ip;
        if (sbSt) sbSt.textContent = d.ip;
      } else {
        if (sd) sd.className = 'status-dot offline';
        if (st) st.textContent = 'Offline';
        if (sbSt) sbSt.textContent = 'Offline';
      }
    }).catch(function() {
      var sd = document.getElementById('status-dot');
      var st = document.getElementById('status-text');
      var sbSt = document.getElementById('sb-status-text');
      if (sd) sd.className = 'status-dot offline';
      if (st) st.textContent = 'Offline';
      if (sbSt) sbSt.textContent = 'Offline';
    });
    fetch(API + '/api/version').then(r => r.json()).then(d => {
      var el = document.getElementById('update-info');
      if (d.version && d.version !== 'unknown') el.textContent = 'Version: ' + d.version + ' — Click below to check for updates.';
      else el.textContent = 'Click below to check for updates.';
      var sbVer = document.getElementById('sb-version');
      if (sbVer && d.version && d.version !== 'unknown') sbVer.textContent = 'ver. ' + d.version;
    }).catch(() => { document.getElementById('update-info').textContent = 'Click below to check for updates.'; });
    loadSystemStats();
  }).catch(function() {
    document.body.classList.remove('auth-pending');
    refreshStatus();
    startMainPoll();
    startCountdown();
  });
}

(function() {
  checkAuth(initApp);
})();

// Reload if browser restores this page from bfcache (back-forward cache).
// bfcache freezes JS state, so buttons can silently lose their handlers
// after navigating away and back. Forcing a reload fixes this transparently.
window.addEventListener('pageshow', function(e) { if (e.persisted) location.reload(); });
