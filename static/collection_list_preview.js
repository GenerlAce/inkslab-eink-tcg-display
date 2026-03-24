(function() {
  'use strict';

  // Fade-in keyframe used by the mobile accordion
  var _style = document.createElement('style');
  _style.textContent = '@keyframes clp-fade{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}';
  document.head.appendChild(_style);

  // --- Helpers ---
  function hesc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function getThumb(row) {
    var img = row.querySelector('.card-row-thumb');
    if (img && img.src) return img.src;
    return row.dataset.thumb || '';
  }

  function getRowInfo(row) {
    var nameEl = row.querySelector('.card-row-name') || row.querySelector('.card-preview-btn');
    var rarEl  = row.querySelector('.card-rarity');
    var setItem = row.closest('.set-item');
    return {
      name:    nameEl  ? nameEl.textContent.trim()  : '',
      vol:     rarEl   ? rarEl.textContent.trim()   : '',
      setName: setItem && setItem.querySelector('.set-name') ? setItem.querySelector('.set-name').textContent.trim() : ''
    };
  }

  // =========================================================
  // DESKTOP — floating hover panel
  // =========================================================
  var _panel = null, _hoverRow = null, _hoverTimer = null;

  function getPanel() {
    if (_panel) return _panel;
    _panel = document.createElement('div');
    _panel.id = 'clp-panel';
    _panel.style.cssText = [
      'position:fixed', 'z-index:9500', 'width:220px',
      'background:var(--bg-card)', 'border:1px solid var(--border-hi)',
      'border-radius:10px', 'padding:12px',
      'pointer-events:none', 'opacity:0',
      'transition:opacity 0.15s ease', 'display:none',
      'box-shadow:0 8px 32px rgba(0,0,0,0.55)'
    ].join(';');
    document.body.appendChild(_panel);
    return _panel;
  }

  function showPanel(row) {
    var thumb = getThumb(row);
    if (!thumb) return;
    var info = getRowInfo(row);
    var p = getPanel();
    p.innerHTML = '<img src="' + hesc(thumb) + '" style="width:100%;height:auto;border-radius:6px;display:block;margin-bottom:10px;">'
      + '<div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px;line-height:1.3;">' + hesc(info.name) + '</div>'
      + (info.setName ? '<div style="font-size:11px;color:var(--text-dim);margin-bottom:2px;">' + hesc(info.setName) + '</div>' : '')
      + (info.vol     ? '<div style="font-size:11px;color:var(--text-dim);">'                   + hesc(info.vol)     + '</div>' : '');

    // Position to the right of the row; fall back to left if no room
    var rect = p.getBoundingClientRect ? p.getBoundingClientRect() : {width:220};
    var pw = 220, ph = 320;
    var rRect = row.getBoundingClientRect();
    var left = rRect.right + 14;
    if (left + pw > window.innerWidth - 8) left = rRect.left - pw - 14;
    if (left < 8) left = 8;
    var top = rRect.top - 10;
    if (top + ph > window.innerHeight - 8) top = window.innerHeight - ph - 8;
    if (top < 8) top = 8;
    p.style.left = left + 'px';
    p.style.top  = top  + 'px';
    p.style.display = 'block';
    requestAnimationFrame(function() { p.style.opacity = '1'; });
  }

  function hidePanel() {
    if (!_panel) return;
    _panel.style.opacity = '0';
    setTimeout(function() { if (_panel) _panel.style.display = 'none'; }, 160);
  }

  // =========================================================
  // MOBILE — inline accordion
  // =========================================================
  var _openRow = null;

  function toggleAccordion(row) {
    // Remove any existing accordion
    var prev = document.querySelector('.clp-accordion');
    if (prev) prev.remove();
    if (_openRow === row) { _openRow = null; return; }

    var thumb = getThumb(row);
    if (!thumb) return;
    var info = getRowInfo(row);

    var acc = document.createElement('div');
    acc.className = 'clp-accordion';
    acc.style.cssText = 'padding:14px;text-align:center;background:var(--bg-input);border-bottom:1px solid var(--border);animation:clp-fade 0.15s ease both;';
    acc.innerHTML = '<img src="' + hesc(thumb) + '" style="width:180px;max-width:80%;height:auto;border-radius:6px;display:inline-block;margin-bottom:8px;">'
      + '<div style="font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px;">' + hesc(info.name) + '</div>'
      + (info.setName ? '<div style="font-size:11px;color:var(--text-dim);margin-bottom:2px;">' + hesc(info.setName) + '</div>' : '')
      + (info.vol     ? '<div style="font-size:11px;color:var(--text-dim);">'                   + hesc(info.vol)     + '</div>' : '');

    row.after(acc);
    _openRow = row;
  }

  // =========================================================
  // Event delegation on #sets-list
  // =========================================================
  function init() {
    var list = document.getElementById('sets-list');
    if (!list) { setTimeout(init, 300); return; }

    // Desktop: mouseover/mouseout for hover panel
    list.addEventListener('mouseover', function(e) {
      if (window.innerWidth < 900) return;
      var row  = e.target.closest('.card-row');
      var from = e.relatedTarget ? e.relatedTarget.closest('.card-row') : null;
      if (row === from) return;           // still within the same row
      clearTimeout(_hoverTimer);
      if (from) { _hoverRow = null; hidePanel(); }
      if (row) {
        _hoverRow = row;
        _hoverTimer = setTimeout(function() { if (_hoverRow === row) showPanel(row); }, 200);
      }
    });

    list.addEventListener('mouseout', function(e) {
      if (window.innerWidth < 900) return;
      var row = e.target.closest('.card-row');
      var to  = e.relatedTarget ? e.relatedTarget.closest('.card-row') : null;
      if (!row || row === to) return;     // still within the same row
      clearTimeout(_hoverTimer);
      _hoverRow = null;
      hidePanel();
    });

    // Mobile: tap the rarity/vol label (outside the checkbox label) to toggle accordion
    list.addEventListener('click', function(e) {
      if (window.innerWidth >= 900) return;
      var row = e.target.closest('.card-row');
      if (!row) return;
      // Only trigger on the rarity span (right side) — lets checkbox area work normally
      if (!e.target.closest('.card-rarity')) return;
      toggleAccordion(row);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 200);
  }
})();
