(function() {
  var _confirmTcg = null;
  var _confirmTimer = null;

  function resetBtn(tcg) {
    var btn = document.getElementById('delLib-' + tcg);
    if (!btn) return;
    var name = (window._tcgRegistry && window._tcgRegistry[tcg]) ? window._tcgRegistry[tcg].name : tcg;
    btn.textContent = 'Delete ' + name;
    btn.style.background = 'transparent';
    btn.style.color = '#EF4444';
    _confirmTcg = null;
  }

  window.deleteLibraryStep = function(tcg) {
    if (_confirmTimer) clearTimeout(_confirmTimer);

    if (_confirmTcg && _confirmTcg !== tcg) {
      resetBtn(_confirmTcg);
    }

    var btn = document.getElementById('delLib-' + tcg);
    if (!btn) return;

    if (_confirmTcg === tcg) {
      // Second click - do the delete
      btn.textContent = 'Deleting...';
      btn.disabled = true;
      _confirmTcg = null;
      fetch('/api/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tcg: tcg})
      }).then(function(r) { return r.json(); }).then(function(d) {
        btn.disabled = false;
        resetBtn(tcg);
        if (d.ok) {
          if (typeof showToast === 'function') showToast('Library deleted', 2000);
          if (typeof loadStorage === 'function') loadStorage();
        } else {
          if (typeof showToast === 'function') showToast(d.error || 'Delete failed', 3000);
        }
      }).catch(function() {
        btn.disabled = false;
        resetBtn(tcg);
      });
    } else {
      // First click - solid red to signal confirm needed
      _confirmTcg = tcg;
      btn.style.background = '#EF4444';
      btn.style.color = '#010001';
      btn.style.border = '1px solid #EF4444';
      btn.textContent = 'Confirm Delete?';
      _confirmTimer = setTimeout(function() { resetBtn(tcg); }, 4000);
    }
  };

  // Replace existing delete buttons with new two-step ones
  function upgradeBtns() {
    var el = document.getElementById('delete-buttons');
    if (!el || !window._tcgRegistry) return;
    el.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:8px;';
    el.innerHTML = '';
    Object.entries(window._tcgRegistry).forEach(function(e) {
      var tcg = e[0], info = e[1];
      var b = document.createElement('button');
      b.id = 'delLib-' + tcg;
      b.className = 'btn btn-sm btn-block';
      b.style.cssText = 'background:transparent;color:#EF4444;border:1px solid #EF4444;';
      b.textContent = 'Delete ' + info.name;
      b.addEventListener('mouseover', function() { if (_confirmTcg !== tcg) { b.style.background = '#EF4444'; b.style.color = '#010001'; } });
      b.addEventListener('mouseout', function() { if (_confirmTcg !== tcg) { b.style.background = 'transparent'; b.style.color = '#EF4444'; } });
      b.addEventListener('click', function() { deleteLibraryStep(tcg); });
      el.appendChild(b);
    });
  }

  // Wait for registry to be loaded then upgrade buttons
  var _upgradeTimer = setInterval(function() {
    if (window._tcgRegistry && document.getElementById('delete-buttons')) {
      upgradeBtns();
      clearInterval(_upgradeTimer);
    }
  }, 300);

})();
