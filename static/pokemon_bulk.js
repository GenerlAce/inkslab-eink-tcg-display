function pokemonSearch() {
  var q = document.getElementById('pokemon-search-input').value.trim();
  var resultsEl = document.getElementById('pokemon-search-results');
  if (!q) return;
  resultsEl.style.display = 'block';
  resultsEl.innerHTML = '<div style="padding:10px;color:#888;">Searching...</div>';
  fetch(API + '/api/search?q=' + encodeURIComponent(q) + '&tcg=pokemon')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var results = data.results || [];
      if (!results.length) {
        resultsEl.innerHTML = '<div style="padding:10px;color:#888;">No results found.</div>';
        return;
      }
      // Group by pokemon name, sort by card count, take top 5
      var groups = {};
      results.forEach(function(c) {
        var key = c.name.toLowerCase();
        if (!groups[key]) groups[key] = {name: c.name, cards: []};
        groups[key].cards.push(c);
      });
      var sorted = Object.values(groups).sort(function(a, b) { return b.cards.length - a.cards.length; }).slice(0, 5);
      var html = '';
      sorted.forEach(function(g) {
        var searchUrl = 'https://www.pokemon.com/us/pokemon-tcg/pokemon-cards/?cardName=' + encodeURIComponent(g.name);
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;border-bottom:1px solid #222;">'
          + '<div>'
          + '<div style="font-weight:600;"><a href="' + searchUrl + '" target="_blank" style="color:#36A5CA;text-decoration:none;">' + esc(g.name) + '</a></div>'
          + '<div style="color:#888;font-size:12px;">' + g.cards.length + ' card(s) in collection</div>'
          + '</div>'
          + '<button onclick="pokemonBulkDownloadByName(this)" data-pname="' + esc(g.name) + '"'
          + ' style="padding:6px 14px;background:#36A5CA;color:#010001;border:none;border-radius:6px;cursor:pointer;font-weight:600;white-space:nowrap;">Download All</button>'
          + '</div>';
      });
      resultsEl.innerHTML = html;
    })
    .catch(function() {
      resultsEl.innerHTML = '<div style="padding:10px;color:#c00;">Search failed. Check connection.</div>';
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
