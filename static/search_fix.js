document.addEventListener('click', function(e) {
  var btn = e.target.closest('.search-group-btn');
  if (!btn) return;
  var name = btn.dataset.name;
  var owned = btn.dataset.owned === 'true';
  if (typeof window.toggleSearchGroup === 'function') {
    window.toggleSearchGroup(btn, name, owned);
  }
});

// Hover preview for queue cards (Previously / Up Next) on Display tab
document.addEventListener('mouseover', function(e) {
  var img = e.target.closest('.q-thumb');
  if (!img) return;
  var src = img.src;
  if (!src) return;
  if (typeof window.showThumbHover === 'function') {
    window.showThumbHover(e, src);
  }
});

document.addEventListener('mouseout', function(e) {
  var img = e.target.closest('.q-thumb');
  if (!img) return;
  if (typeof window.hideThumbHover === 'function') {
    window.hideThumbHover();
  }
});
