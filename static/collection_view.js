(function() {
  var style = document.createElement('style');
  style.textContent = [
    '.grid-thumb-wrap{position:relative;width:100%;cursor:pointer;text-align:center;min-width:0;}',
    '.grid-thumb{width:100%;height:auto;aspect-ratio:2/3;object-fit:cover;border-radius:6px;border:2px solid var(--border);display:block;transition:border-color 0.15s;}',
    '.grid-thumb.owned{border-color:var(--accent2);}',
    '.grid-check{display:none;position:absolute;top:3px;right:3px;background:var(--accent2);color:var(--bg);border-radius:50%;width:18px;height:18px;align-items:center;justify-content:center;font-size:11px;font-weight:bold;}',
    '.grid-check.show{display:flex;}',
    '.grid-label{font-size:9px;color:var(--text-dim);text-align:center;margin-top:2px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;width:100%;}',
  ].join('');
  document.head.appendChild(style);

  window.toggleCardThumb = function(cardId) {
    var img = document.getElementById('gthumb-' + cardId);
    var check = document.getElementById('gcheck-' + cardId);
    if (!img || !check) return;
    var nowOwned = !check.classList.contains('show');
    if (nowOwned) { img.classList.add('owned'); check.classList.add('show'); }
    else { img.classList.remove('owned'); check.classList.remove('show'); }
    // Update the set badge count immediately without waiting for a page reload
    var setItem = img.closest('.set-item');
    if (setItem) {
      var badge = setItem.querySelector('.badge');
      if (nowOwned) {
        if (badge) { badge.textContent = parseInt(badge.textContent) + 1; }
        else {
          var setName = setItem.querySelector('.set-name');
          if (setName) { badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = '1'; setName.after(badge); }
        }
      } else if (badge) {
        var n = parseInt(badge.textContent) - 1;
        if (n <= 0) badge.remove(); else badge.textContent = n;
      }
    }
    var tcg = window.getEffectiveBrowseTcg ? window.getEffectiveBrowseTcg() : ((window._lastStatus && window._lastStatus.tcg) || 'pokemon');
    fetch('/api/collection/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({card_id: cardId, owned: nowOwned, tcg: tcg})});
  };

  function getTcg(callback) {
    if (window.getEffectiveBrowseTcg) {
      callback(window.getEffectiveBrowseTcg());
      return;
    }
    if (window._lastStatus && window._lastStatus.tcg) {
      callback(window._lastStatus.tcg);
      return;
    }
    fetch('/api/status').then(function(r) { return r.json(); }).then(function(d) {
      if (window._lastStatus) window._lastStatus.tcg = d.tcg;
      callback(d.tcg || 'pokemon');
    }).catch(function() { callback('pokemon'); });
  }

  window.setCollectionView = function(mode) {
    localStorage.setItem('inkslab_collection_view', mode);
    updateViewButtons();
    document.querySelectorAll('.set-cards').forEach(function(sc) {
      sc.removeAttribute('data-loaded');
      sc.removeAttribute('data-enhanced');
      sc.classList.remove('open');
      sc.innerHTML = '';
    });
    if (typeof loadSets === 'function') loadSets();
  };

  function updateViewButtons() {
    var mode = localStorage.getItem('inkslab_collection_view') || 'list';
    var lb = document.getElementById('btn-view-list');
    var gb = document.getElementById('btn-view-grid');
    if (lb) lb.style.background = mode === 'list' ? 'var(--accent)' : '';
    if (gb) gb.style.background = mode === 'grid' ? 'var(--accent)' : '';
  }

  window.openPreviewModal = function(src, cardNum, rarity, setName, tcg, year) {
    openPreviewModal(src, cardNum, rarity, setName, tcg, year);
  };

  function openPreviewModal(src, cardNum, rarity, setName, tcg, year) {
    var previewImg = document.getElementById('preview-img');
    var previewModal = document.getElementById('preview-modal');
    if (!previewModal || !previewImg) return;
    previewImg.style.opacity = '0';
    previewImg.onload = function() { this.style.opacity = '1'; };
    previewImg.src = src;
    var previewName = document.getElementById('preview-name');
    if (previewName) previewName.textContent = '';
    var isMC = (tcg === 'manga' || tcg === 'comics');
    var numLabel = isMC ? (tcg === 'manga' ? 'Volume #' : 'Issue #') : 'Card #';
    var rarityLabel = isMC ? 'Year' : 'Rarity';
    var rarityVal = isMC ? (year || '\u2014') : (rarity || '\u2014');
    var pmNumLbl = document.getElementById('pm-num-label');
    var pmNum = document.getElementById('pm-num');
    var pmRarityLbl = document.getElementById('pm-rarity-label');
    var pmRarity = document.getElementById('pm-rarity');
    var pmSet = document.getElementById('pm-set');
    if (pmNumLbl) pmNumLbl.textContent = numLabel;
    if (pmNum) pmNum.textContent = cardNum || '\u2014';
    if (pmRarityLbl) pmRarityLbl.textContent = rarityLabel;
    if (pmRarity) pmRarity.textContent = rarityVal;
    if (pmSet) pmSet.textContent = setName || '\u2014';
    previewModal.classList.add('open');
  }

  function convertToGrid(container, setId) {
    if (container.querySelector('.grid-thumb-wrap')) { container.style.visibility = ''; return; }
    getTcg(function(tcg) {
      var rows = container.querySelectorAll('.card-row');
      if (!rows.length) return;
      var cols = window.innerWidth >= 600 ? 8 : 4;
      var gridDiv = document.createElement('div');
      gridDiv.style.cssText = 'display:grid;grid-template-columns:repeat(' + cols + ',1fr);gap:6px;padding:6px 0;width:100%;';
      var setItem = container.closest('.set-item');
      var setNameText = setItem ? (setItem.querySelector('.set-name') ? setItem.querySelector('.set-name').textContent.trim() : '') : '';
      rows.forEach(function(row) {
        var cb = row.querySelector('input[type=checkbox]');
        if (!cb) return;
        var onchange = cb.getAttribute('onchange') || '';
        var match = onchange.match(/toggleCard\('([^']+)'/);
        if (!match) return;
        var cardId = match[1];
        var isOwned = cb.checked;
        var src = '/api/card_image/' + encodeURIComponent(tcg) + '/' + encodeURIComponent(setId) + '/' + encodeURIComponent(cardId);
        var thumbSrc = '/api/card_thumbnail/' + encodeURIComponent(tcg) + '/' + encodeURIComponent(setId) + '/' + encodeURIComponent(cardId);
        var rarityEl = row.querySelector('.card-rarity');
        var rarity = rarityEl ? rarityEl.textContent : '';
        var previewBtnEl = row.querySelector('.card-preview-btn');
        var previewText = previewBtnEl ? previewBtnEl.textContent.trim() : '';
        var numMatch = previewText.match(/^#(\S+)/);
        var cardNum = numMatch ? numMatch[1] : '';
        var cardYear = row.dataset.year || '';
        var wrap = document.createElement('div');
        wrap.className = 'grid-thumb-wrap';
        wrap.id = 'gw-' + cardId;
        var img = document.createElement('img');
        img.className = 'grid-thumb' + (isOwned ? ' owned' : '');
        img.id = 'gthumb-' + cardId;
        img.loading = 'lazy';
        img.src = thumbSrc;
        img.dataset.src = src;
        img.onerror = (function(fullUrl) {
          var tried = false;
          return function() {
            if (!tried && this.src !== fullUrl) {
              tried = true;
              this.src = fullUrl; // thumbnail failed — fall back to full image
            } else {
              this.style.opacity = '0.2'; // full image also failed
            }
          };
        })(src);
        // _wasScrollTouch tracks if the last touch was a scroll so we can suppress the browser's
        // synthetic click event that fires after touchend even when the user was scrolling.
        var _wasScrollTouch = false;
        // Desktop: top half = toggle collection, bottom half = open preview modal
        img.addEventListener('click', function(e) {
          if (_wasScrollTouch) { _wasScrollTouch = false; return; }
          var rect = img.getBoundingClientRect();
          var relY = e.clientY - rect.top;
          if (relY < rect.height / 2) {
            window.toggleCardThumb(cardId);
          } else {
            openPreviewModal(src, cardNum, rarity, setNameText, tcg, cardYear);
          }
        });
        // Mobile: touchend handles top/bottom half tap; scrolls are ignored
        var _touchStartX = 0, _touchStartY = 0, _touchScrollY = 0;
        img.addEventListener('touchstart', function(e) {
          _touchStartX = e.touches[0].clientX;
          _touchStartY = e.touches[0].clientY;
          var sc = img.closest('.content') || document.documentElement;
          _touchScrollY = sc.scrollTop;
        }, {passive: true});
        img.addEventListener('touchend', function(e) {
          var touch = e.changedTouches[0];
          var dx = Math.abs(touch.clientX - _touchStartX);
          var dy = Math.abs(touch.clientY - _touchStartY);
          var sc = img.closest('.content') || document.documentElement;
          var scrolled = Math.abs(sc.scrollTop - _touchScrollY);
          if (dx > 8 || dy > 8 || scrolled > 5) {
            _wasScrollTouch = true; // suppress the upcoming synthetic click
            return;
          }
          e.preventDefault(); // genuine tap — block synthetic click
          var rect = img.getBoundingClientRect();
          var relY = touch.clientY - rect.top;
          if (relY < rect.height / 2) {
            window.toggleCardThumb(cardId); // top half: add/remove from collection
          } else {
            openPreviewModal(thumbSrc, cardNum, rarity, setNameText, tcg, cardYear); // bottom half: use thumbnail (already cached, fast on mobile)
          }
        }, {passive: false});
        var check = document.createElement('div');
        check.className = 'grid-check' + (isOwned ? ' show' : '');
        check.id = 'gcheck-' + cardId;
        check.innerHTML = '&#10003;';
        var lbl = document.createElement('div');
        lbl.className = 'grid-label';
        lbl.textContent = rarity;
        wrap.appendChild(img);
        wrap.appendChild(check);
        wrap.appendChild(lbl);
        gridDiv.appendChild(wrap);
      });
      var firstDiv = container.querySelector('div');
      container.innerHTML = '';
      if (firstDiv) container.appendChild(firstDiv);
      container.appendChild(gridDiv);
      container.style.visibility = '';
    });
  }

  function watchForSets() {
    var orig = window.toggleSet;
    if (typeof orig !== 'function') {
      setTimeout(watchForSets, 200);
      return;
    }
    window.toggleSet = function(setId) {
      orig(setId);
      var mode = localStorage.getItem('inkslab_collection_view') || 'list';
      if (mode !== 'grid') return;
      var el = document.getElementById('set-' + setId);
      if (!el || !el.classList.contains('open')) return; // closing
      if (el.dataset.enhanced) return; // already grid, imgs preserved
      // Hide immediately so list never flashes before grid is ready
      el.style.visibility = 'hidden';
      var attempts = 0;
      var check = setInterval(function() {
        attempts++;
        var el = document.getElementById('set-' + setId);
        if (!el || !el.classList.contains('open')) { if (el) el.style.visibility = ''; clearInterval(check); return; }
        if (el.dataset.enhanced) { clearInterval(check); return; }
        if (el.dataset.loaded) {
          clearInterval(check);
          el.dataset.enhanced = '1';
          convertToGrid(el, setId);
        }
        if (attempts > 20) { el.style.visibility = ''; clearInterval(check); }
      }, 200);
    };
  }

  function init() {
    var setsList = document.getElementById('sets-list');
    var ctrlEl = document.getElementById('collection-view-ctrl');
    if (window.innerWidth < 600) {
      // Mobile: always grid, no toggle
      localStorage.setItem('inkslab_collection_view', 'grid');
    } else if (ctrlEl) {
      // Desktop: populate the pre-placed top-row section
      ctrlEl.innerHTML = '<button id="btn-view-list" class="btn btn-secondary btn-sm" style="flex:1">List</button><button id="btn-view-grid" class="btn btn-secondary btn-sm" style="flex:1">Grid</button>';
      var wrap = document.getElementById('collection-view-ctrl-wrap');
      if (wrap) wrap.style.display = '';
      document.getElementById('btn-view-list').addEventListener('click', function() { window.setCollectionView('list'); });
      document.getElementById('btn-view-grid').addEventListener('click', function() { window.setCollectionView('grid'); });
    } else if (setsList) {
      // Fallback: insert card before sets-list
      var toggleDiv = document.createElement('div');
      toggleDiv.className = 'card';
      toggleDiv.style.cssText = 'padding:16px;margin-bottom:12px;';
      toggleDiv.innerHTML = '<h3 style="margin:0 0 8px 0;">Collection View</h3><div style="display:flex;justify-content:space-between;align-items:center;"><span style="font-size:12px;color:var(--text-dim);">Choose display style</span><div style="display:flex;gap:6px;"><button id="btn-view-list" class="btn btn-secondary btn-sm" style="font-size:12px;">List</button><button id="btn-view-grid" class="btn btn-secondary btn-sm" style="font-size:12px;">Grid</button></div></div>';
      setsList.parentNode.insertBefore(toggleDiv, setsList);
      document.getElementById('btn-view-list').addEventListener('click', function() { window.setCollectionView('list'); });
      document.getElementById('btn-view-grid').addEventListener('click', function() { window.setCollectionView('grid'); });
    }
    updateViewButtons();
    watchForSets();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 200);
  }
})();
