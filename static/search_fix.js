document.addEventListener('click', function(e) {
  var btn = e.target.closest('.search-group-btn');
  if (!btn) return;
  var name = btn.dataset.name;
  var owned = btn.dataset.owned === 'true';
  if (typeof window.toggleSearchGroup === 'function') {
    window.toggleSearchGroup(btn, name, owned);
  }
});
