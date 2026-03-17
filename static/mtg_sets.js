function mtgSetSearch() {
  var q = document.getElementById('mtg-set-search-input').value.trim();
  var resultsEl = document.getElementById('mtg-set-search-results');
  if (!q) return;
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:#888;">Searching...</div>';
  fetch(API + '/api/mtg/sets?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var results = data.results || [];
      if (!results.length) {
        resultsEl.innerHTML = '<div style="padding:10px;color:#888;">No sets found.</div>';
        return;
      }
      var html = '';
      results.forEach(function(s) {
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #222;">'
          + '<div>'
          + '<div style="font-weight:600;"><a href="https://scryfall.com/sets/' + esc(s.code) + '" target="_blank" style="color:#6BCCBD;text-decoration:none;">' + esc(s.name) + '</a></div>'
          + '<div style="color:#888;font-size:12px;">' + esc(s.code.toUpperCase()) + ' &mdash; ' + esc(s.released) + ' &mdash; ' + s.card_count + ' cards</div>'
          + '</div>'
          + '<button onclick="mtgSetDownload(this)" data-set-code="' + esc(s.code) + '" data-set-name="' + esc(s.name) + '"'
          + ' style="padding:6px 14px;background:#6BCCBD;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;">Download All</button>'
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
      document.getElementById('mtg-set-search-results').style.display = 'none';
      document.getElementById('mtg-set-search-input').value = '';
      document.getElementById('dl-status').textContent = 'Downloading ' + name + '...';
      setDownloadUI(true, 'mtg');
      pollDownload();
    } else {
      showToast(d.error || 'Failed to start download');
      btn.disabled = false;
      btn.textContent = 'Download';
    }
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
