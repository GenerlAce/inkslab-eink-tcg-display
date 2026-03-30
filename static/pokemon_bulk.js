function pokemonSearch() {
  var q = document.getElementById('pokemon-search-input').value.trim();
  var resultsEl = document.getElementById('pokemon-search-results');
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:var(--text-dim);">Searching...</div>';
  fetch(API + '/api/pokemon/sets?q=' + encodeURIComponent(q))
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
        var imgHtml = s.symbol
          ? '<img src="' + esc(s.symbol) + '" style="width:36px;height:36px;object-fit:contain;flex-shrink:0;" onerror="this.style.display=\'none\'">'
          : '<div style="width:36px;flex-shrink:0;"></div>';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid var(--border);gap:8px;">'
          + '<div style="display:flex;align-items:center;gap:10px;min-width:0;">'
          + imgHtml
          + '<div style="min-width:0;">'
          + '<div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(s.name) + '</div>'
          + '<div style="color:var(--text-dim);font-size:12px;">' + esc(s.id.toUpperCase()) + ' &middot; ' + esc(s.released) + ' &middot; ' + s.total + ' cards</div>'
          + '</div></div>'
          + '<button onclick="pokemonSetDownload(this)" data-set-id="' + esc(s.id) + '" data-set-name="' + esc(s.name) + '"'
          + ' style="padding:6px 14px;background:#22d3ee;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;flex-shrink:0;">Download</button>'
          + '</div>';
      });
      resultsEl.innerHTML = html;
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Search failed. Check connection.</div>';
    });
}

function pokemonSetDownload(btn) {
  var setId = btn.getAttribute('data-set-id');
  var setName = btn.getAttribute('data-set-name');
  if (!setId) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'pokemon', pokemon_set: setId})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      showToast('Downloading ' + setName + '...');
      if (window.closeAllDlSearch) closeAllDlSearch();
      document.getElementById('pokemon-search-results').style.display = 'none';
      document.getElementById('pokemon-search-input').value = '';
      document.getElementById('dl-status').textContent = 'Downloading ' + setName + '...';
      if (window.openDlLog) openDlLog();
      setDownloadUI(true, 'pokemon');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download';
    }
  });
}

function pokemonBulkDownloadByName(btn) {
  var name = btn.getAttribute('data-pname');
  if (!name) return;
  btn.disabled = true;
  btn.textContent = 'Starting...';
  fetch(API + '/api/download/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tcg: 'pokemon', pokemon_name: name})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      showToast('Downloading all ' + name + ' cards...');
      if (window.closeAllDlSearch) closeAllDlSearch();
      document.getElementById('pokemon-search-results').style.display = 'none';
      document.getElementById('pokemon-search-input').value = '';
      document.getElementById('dl-status').textContent = 'Downloading ' + name + '...';
      if (window.openDlLog) openDlLog();
      setDownloadUI(true, 'pokemon');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download All';
    }
  });
}

function pokemonBulkClick(btn) {
  var name = btn.getAttribute('data-pname');
  if (!name) return;
  pokemonBulkDownloadByName(btn);
}

document.addEventListener('DOMContentLoaded', function() {
  var input = document.getElementById('pokemon-search-input');
  if (input) {
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') pokemonSearch();
    });
  }
});
