(function() {
  var style = document.createElement('style');
  style.textContent = [
    '.thumb-hover-preview{display:none;position:fixed;z-index:9999;pointer-events:none;border-radius:8px;border:2px solid #6BCCBD;box-shadow:0 4px 24px rgba(0,0,0,0.7);width:360px;max-width:calc(100vw - 24px);}',
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
  var hoverImg = document.createElement('img');
  hoverImg.id = 'thumb-hover-img';
  hoverImg.style.cssText = 'width:100%;border-radius:6px;display:block;';
  hoverDiv.appendChild(hoverImg);
  document.body.appendChild(hoverDiv);

  window.showThumbHover = function(event, src) {
    var el = document.getElementById('thumb-hover-preview');
    var img = document.getElementById('thumb-hover-img');
    if (!el || !img) return;
    img.src = src;
    el.style.display = 'block';
    var previewLeft = event.clientX + 12;
    if (previewLeft + 360 > window.innerWidth) previewLeft = window.innerWidth - 368;
    el.style.left = Math.max(8, previewLeft) + 'px';
    el.style.top = Math.max(8, event.clientY - 570) + 'px';
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
    getTcg(function(tcg) {
      var rows = container.querySelectorAll('.card-row');
      if (!rows.length) return;
      var gridDiv = document.createElement('div');
      gridDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;padding:6px 0;';
      rows.forEach(function(row) {
        var cb = row.querySelector('input[type=checkbox]');
        if (!cb) return;
        var onchange = cb.getAttribute('onchange') || '';
        var match = onchange.match(/toggleCard\('([^']+)'\)/);
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
      var attempts = 0;
      var check = setInterval(function() {
        attempts++;
        var el = document.getElementById('set-' + setId);
        if (!el || !el.classList.contains('open')) { clearInterval(check); return; }
        if (el.dataset.enhanced) { clearInterval(check); return; }
        if (el.dataset.loaded) {
          clearInterval(check);
          el.dataset.enhanced = '1';
          convertToGrid(el, setId);
        }
        if (attempts > 20) clearInterval(check);
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
      var match = onchange.match(/toggleCard\('([^']+)'\)/);
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
