// modal_helpers.js — reusable themed modal helpers
// Replaces native confirm() and prompt() throughout the dashboard.

// ── Generic Confirm Modal ──────────────────────────────────────────────────
var _GCM = {
  _cb: null,
  show: function(title, bodyHTML, confirmLabel, onConfirm) {
    document.getElementById('gcm-title').textContent = title;
    document.getElementById('gcm-body').innerHTML = bodyHTML;
    document.getElementById('gcm-confirm-label').textContent = confirmLabel || 'Confirm';
    this._cb = onConfirm;
    document.getElementById('generic-confirm-modal').classList.add('open');
  },
  confirm: function() {
    document.getElementById('generic-confirm-modal').classList.remove('open');
    var cb = this._cb; this._cb = null;
    if (cb) cb();
  },
  cancel: function() {
    document.getElementById('generic-confirm-modal').classList.remove('open');
    this._cb = null;
  }
};

// Convenience alias used in app.js
function showConfirm(title, bodyHTML, confirmLabel, onConfirm) {
  _GCM.show(title, bodyHTML, confirmLabel, onConfirm);
}

// ── Generic Prompt Modal ───────────────────────────────────────────────────
var _GPM = {
  _cb: null,
  show: function(title, desc, placeholder, currentValue, onConfirm) {
    document.getElementById('gpm-title').textContent = title;
    var descEl = document.getElementById('gpm-desc');
    if (desc) { descEl.textContent = desc; descEl.style.display = 'block'; }
    else { descEl.style.display = 'none'; }
    var input = document.getElementById('gpm-input');
    input.placeholder = placeholder || '';
    input.value = currentValue || '';
    this._cb = onConfirm;
    document.getElementById('generic-prompt-modal').classList.add('open');
    setTimeout(function() {
      input.focus();
      input.select();
    }, 60);
  },
  confirm: function() {
    var val = document.getElementById('gpm-input').value.trim();
    if (!val) return;
    document.getElementById('generic-prompt-modal').classList.remove('open');
    var cb = this._cb; this._cb = null;
    if (cb) cb(val);
  },
  cancel: function() {
    document.getElementById('generic-prompt-modal').classList.remove('open');
    this._cb = null;
  }
};

function showPrompt(title, desc, placeholder, currentValue, onConfirm) {
  _GPM.show(title, desc, placeholder, currentValue, onConfirm);
}

// ── Card Metadata Modal (3-field edit) ────────────────────────────────────
var _CMM = {
  _cb: null,
  show: function(name, number, rarity, thumbUrl, onConfirm) {
    document.getElementById('cmm-name').value = name || '';
    document.getElementById('cmm-number').value = number || '';
    document.getElementById('cmm-rarity').value = rarity || '';
    var prev = document.getElementById('cmm-preview');
    var sub  = document.getElementById('cmm-subtitle');
    if (thumbUrl) {
      prev.src = thumbUrl;
      prev.style.display = 'block';
      sub.textContent = (name || '') + (number ? '  #' + number : '');
      sub.style.display = name ? 'block' : 'none';
    } else {
      prev.style.display = 'none';
      sub.style.display  = 'none';
    }
    this._cb = onConfirm;
    document.getElementById('card-meta-modal').classList.add('open');
    setTimeout(function() {
      document.getElementById('cmm-name').focus();
    }, 60);
  },
  confirm: function() {
    var name   = document.getElementById('cmm-name').value.trim();
    var number = document.getElementById('cmm-number').value.trim();
    var rarity = document.getElementById('cmm-rarity').value.trim();
    document.getElementById('card-meta-modal').classList.remove('open');
    var cb = this._cb; this._cb = null;
    if (cb) cb(name, number, rarity);
  },
  cancel: function() {
    document.getElementById('card-meta-modal').classList.remove('open');
    this._cb = null;
  }
};
