(function() {
  var style = document.createElement('style');
  style.textContent = [
    '.thumb-hover-preview{display:none;position:fixed;z-index:9999;pointer-events:auto;border-radius:8px;border:2px solid #6BCCBD;box-shadow:0 4px 24px rgba(0,0,0,0.7);width:360px;max-width:calc(100vw - 24px);}',
    '.thumb-hover-close{position:absolute;top:6px;right:6px;background:rgba(0,0,0,0.6);color:#fff;border:none;border-radius:50%;width:28px;height:28px;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:10000;}',
    '.grid-thumb-wrap{position:relative;width:80px;cursor:pointer;text-align:center;}',
    '.grid-thumb{width:80px;height:110px;object-fit:cover;border-radius:6px;border:2px solid #1F333F;display:block;transition:border-color 0.15s;}',
    '.grid-thumb.owned{border-color:#6BCCBD;}',
    '.grid-check{display:none;position:absolute;top:3px;right:3px;background:#6BCCBD;color:#010001;border-radius:50%;width:18px;height:18px;align-items:center;justify-content:center;font-size:11px;font-weight:bold;}',
    '.grid-check.show{display:flex;}',
    '.grid-label{font-size:9px;color:#6BCCBD;text-align:center;margin-top:2px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;width:80px;}',
  ].join('');
  document.head.appendChild(style);

  var hoverDiv = document.createElement('div');
  hoverDiv.id = 'thumb-hover-preview';
  hoverDiv.className = 'thumb-hover-preview';
  hoverDiv.style.position = 'fixed';
  var hoverImg = document.createElement('img');
  hoverImg.id = 'thumb-hover-img';
  hoverImg.style.cssText = 'width:100%;border-radius:6px;display:block;';
  var closeBtn = document.createElement('button');
  closeBtn.className = 'thumb-hover-close';
  closeBtn.innerHTML = '&times;';
  closeBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    window.hideThumbHover();
  });
  hoverDiv.appendChild(hoverImg);
  hoverDiv.appendChild(closeBtn);
  hoverDiv.addEventListener('click', function() { window.hideThumbHover(); });
  hoverDiv.addEventListener('touchend', function() { window.hideThumbHover(); }, {passive: true});
  document.body.appendChild(hoverDiv);
  // Click anywhere outside to dismiss
  document.addEventListener('click', function(e) {
    var el = document.getElementById('thumb-hover-preview');
    if (el && el.style.display !== 'none' && !el.contains(e.target)) {
      window.hideThumbHover();
    }
  });
  // Touch on mobile - show on tap
  document.addEventListener('touchstart', function(e) {
    var el = document.getElementById('thumb-hover-preview');
    if (el && el.style.display !== 'none' && !el.contains(e.target)) {
      window.hideThumbHover();
    }
  });

  window.showThumbHover = function(event, src) {
    var el = document.getElementById('thumb-hover-preview');
    var img = document.getElementById('thumb-hover-img');
    if (!el || !img) return;
    img.src = src;
    el.style.display = 'block';
    var isMobile = window.innerWidth < 600;
    if (isMobile) {
      // Center on screen for mobile
      el.style.left = '50%';
      el.style.transform = 'translateX(-50%)';
      el.style.top = '50%';
      el.style.marginTop = '-180px';
    } else {
      el.style.transform = '';
      el.style.marginTop = '';
      // Position right of cursor, clamp to right edge
      var previewW = 360;
      var previewH = el.offsetHeight || 400;
      var previewLeft = event.clientX + 16;
      if (previewLeft + previewW > window.innerWidth - 8) {
        previewLeft = window.innerWidth - previewW - 8;
      }
      el.style.left = Math.max(8, previewLeft) + 'px';
      // Position above cursor, clamped to viewport
      var previewTop = event.clientY - previewH - 8;
      if (previewTop < 8) previewTop = event.clientY + 16;
      if (previewTop + previewH > window.innerHeight - 8) previewTop = window.innerHeight - previewH - 8;
      el.style.top = Math.max(8, previewTop) + 'px';
    }
  };

  window.hideThumbHover = function() {
    var el = document.getElementById('thumb-hover-preview');
    if (el) el.style.display = 'none';
  };

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
    fetch('/api/collection/toggle', {method:'POST', body: JSON.stringify({card_id: cardId, owned: nowOwned})});
  };

  function getTcg(callback) {
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
    if (lb) lb.style.background = mode === 'list' ? '#36A5CA' : '';
    if (gb) gb.style.background = mode === 'grid' ? '#36A5CA' : '';
  }

  function convertToGrid(container, setId) {
    if (container.querySelector('.grid-thumb-wrap')) { container.style.visibility = ''; return; }
    getTcg(function(tcg) {
      var rows = container.querySelectorAll('.card-row');
      if (!rows.length) return;
      var gridDiv = document.createElement('div');
      gridDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;padding:6px 0;';
      rows.forEach(function(row) {
        var cb = row.querySelector('input[type=checkbox]');
        if (!cb) return;
        var onchange = cb.getAttribute('onchange') || '';
        var match = onchange.match(/toggleCard\('([^']+)'/);
        if (!match) return;
        var cardId = match[1];
        var isOwned = cb.checked;
        var src = '/api/card_image/' + encodeURIComponent(tcg) + '/' + encodeURIComponent(setId) + '/' + encodeURIComponent(cardId);
        var rarityEl = row.querySelector('.card-rarity');
        var rarity = rarityEl ? rarityEl.textContent : '';
        var wrap = document.createElement('div');
        wrap.className = 'grid-thumb-wrap';
        wrap.id = 'gw-' + cardId;
        var img = document.createElement('img');
        img.className = 'grid-thumb' + (isOwned ? ' owned' : '');
        img.id = 'gthumb-' + cardId;
        img.src = src;
        img.dataset.src = src;
        img.onerror = function() { this.style.opacity = '0.2'; };
        img.addEventListener('click', function() { window.toggleCardThumb(cardId); });
        img.addEventListener('mouseenter', function(e) { window.showThumbHover(e, src); });
        img.addEventListener('mouseleave', window.hideThumbHover);
        // Top half tap = add to collection, bottom half tap = preview
        img.addEventListener('touchend', function(e) {
          e.preventDefault();
          var touch = e.changedTouches[0];
          var rect = img.getBoundingClientRect();
          var relY = touch.clientY - rect.top;
          if (relY < rect.height / 2) {
            window.toggleCardThumb(cardId);
          } else {
            var el = document.getElementById('thumb-hover-preview');
            if (el && el.style.display !== 'none') {
              window.hideThumbHover();
            } else {
              window.showThumbHover(touch, src);
            }
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
  function addHoverToBtn(btn) {
    if (btn.dataset.hoverAdded) return;
    btn.dataset.hoverAdded = '1';
    btn.addEventListener('mouseenter', function(e) {
      var row = btn.closest('.card-row');
      if (!row) return;
      var cb = row.querySelector('input[type=checkbox]');
      if (!cb) return;
      var onchange = cb.getAttribute('onchange') || '';
      var match = onchange.match(/toggleCard\('([^']+)'/);
      if (!match) return;
      var cardId = match[1];
      var setCards = btn.closest('.set-cards');
      if (!setCards) return;
      var setId = setCards.id.replace('set-', '');
      getTcg(function(tcg) {
        var src = '/api/card_image/' + encodeURIComponent(tcg) + '/' + encodeURIComponent(setId) + '/' + encodeURIComponent(cardId);
        window.showThumbHover(e, src);
      });
    });
    btn.addEventListener('mouseleave', window.hideThumbHover);
  }
  function init() {
    var setsList = document.getElementById('sets-list');
    if (setsList) {
      var toggleDiv = document.createElement('div');
      toggleDiv.className = 'card';
      toggleDiv.style.cssText = 'padding:16px;margin-bottom:12px;';
      toggleDiv.innerHTML = '<h3 style="margin:0 0 8px 0;">Collection View</h3><div style="display:flex;justify-content:space-between;align-items:center;"><span style="font-size:12px;color:#6BCCBD;">Choose display style</span><div style="display:flex;gap:6px;"><button id="btn-view-list" class="btn btn-secondary btn-sm" style="font-size:12px;">List</button><button id="btn-view-grid" class="btn btn-secondary btn-sm" style="font-size:12px;">Grid</button></div></div>';
      setsList.parentNode.insertBefore(toggleDiv, setsList);
      document.getElementById('btn-view-list').addEventListener('click', function() { window.setCollectionView('list'); });
      document.getElementById('btn-view-grid').addEventListener('click', function() { window.setCollectionView('grid'); });
    }
    // Add hover preview to list view card names
    var listObserver = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        mutation.addedNodes.forEach(function(node) {
          if (node.nodeType !== 1) return;
          var btns = node.querySelectorAll ? node.querySelectorAll('.card-preview-btn') : [];
          btns.forEach(addHoverToBtn);
          if (node.classList && node.classList.contains('card-preview-btn')) addHoverToBtn(node);
        });
      });
    });
    listObserver.observe(document.body, {childList: true, subtree: true});
    updateViewButtons();
    watchForSets();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 200);
  }
})();
