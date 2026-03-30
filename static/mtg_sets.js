function mtgSetSearch() {
  var q = document.getElementById('mtg-set-search-input').value.trim();
  var resultsEl = document.getElementById('mtg-set-search-results');
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:var(--text-dim);">Searching...</div>';
  fetch(API + '/api/mtg/sets?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var results = data.results || [];
      if (!results.length) {
        resultsEl.innerHTML = '<div style="padding:10px;color:var(--text-dim);">'
          + (data.error ? 'Search failed: ' + esc(data.error) : 'No sets found.') + '</div>';
        return;
      }
      var html = '';
      results.forEach(function(s) {
        var imgHtml = s.icon
          ? '<img src="' + esc(s.icon) + '" style="width:28px;height:28px;object-fit:contain;flex-shrink:0;filter:invert(1) sepia(1) saturate(2) hue-rotate(150deg) brightness(1.2);" onerror="this.style.display=\'none\'">'
          : '<div style="width:28px;flex-shrink:0;"></div>';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid var(--border);gap:8px;">'
          + '<div style="display:flex;align-items:center;gap:10px;min-width:0;">'
          + imgHtml
          + '<div style="min-width:0;">'
          + '<div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(s.name) + '</div>'
          + '<div style="color:var(--text-dim);font-size:12px;">' + esc(s.code.toUpperCase()) + ' &middot; ' + esc(s.released) + ' &middot; ' + s.card_count + ' cards</div>'
          + '</div></div>'
          + '<button onclick="mtgSetDownload(this)" data-set-code="' + esc(s.code) + '" data-set-name="' + esc(s.name) + '"'
          + ' style="padding:6px 14px;background:var(--accent2);color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;flex-shrink:0;">Download</button>'
          + '</div>';
      });
      resultsEl.innerHTML = html;
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Search failed. Check connection.</div>';
    });
}

function mtgSetDownload(btn) {
  var code = btn.getAttribute('data-set-code');
  var name = btn.getAttribute('data-set-name');
  if (!code) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'mtg', mtg_set: code})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      showToast('Downloading ' + name + '...');
      if (window.closeAllDlSearch) closeAllDlSearch();
      document.getElementById('mtg-set-search-results').style.display = 'none';
      document.getElementById('mtg-set-search-input').value = '';
      document.getElementById('dl-status').textContent = 'Downloading ' + name + '...';
      if (window.openDlLog) openDlLog();
      setDownloadUI(true, 'mtg');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download';
    }
  }).catch(function() {
    showToast('Failed to start download');
    btn.disabled = false;
    btn.textContent = 'Download';
  });
}

document.addEventListener('DOMContentLoaded', function() {
  var input = document.getElementById('mtg-set-search-input');
  if (input) {
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') mtgSetSearch();
    });
  }
});
