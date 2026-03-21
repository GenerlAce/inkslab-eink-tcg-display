#!/usr/bin/python3
"""
InkSlab Web Dashboard
https://github.com/costamesatechsolutions/inkslab-eink-tcg-display

A lightweight Flask web UI for managing InkSlab from your phone or browser.
Access via the IP address shown on startup after enabling the systemd service.

By Costa Mesa Tech Solutions (a brand of Pine Heights Ventures LLC)
"""

import os
import re
import json
import shutil
import signal
import subprocess
import tempfile
import time
import threading
import hashlib
import secrets
import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_file, redirect, session
import wifi_manager
try:
    from PIL import Image as _PIL_Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

THUMB_CACHE_DIR = '/home/pi/inkslab-collections/.thumbcache'
THUMB_SIZE = (300, 450)  # max width x height (2:3 aspect)
_thumb_lock = threading.Lock()  # one PIL generation at a time — prevents OOM on Pi

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

# --- SESSION & SECRET KEY ---
_SECRET_KEY_FILE = '/home/pi/.inkslab_secret_key'

def _load_or_create_secret_key():
    if os.path.exists(_SECRET_KEY_FILE):
        try:
            with open(_SECRET_KEY_FILE, 'rb') as f:
                key = f.read()
            if len(key) >= 24:
                return key
        except Exception:
            pass
    key = os.urandom(32)
    try:
        with open(_SECRET_KEY_FILE, 'wb') as f:
            f.write(key)
        os.chmod(_SECRET_KEY_FILE, 0o600)
    except Exception:
        pass
    return key

app.secret_key = _load_or_create_secret_key()
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

VERSION = "1.0.0"

# --- PATHS ---
CONFIG_FILE = "/home/pi/inkslab_config.json"
COLLECTION_FILE = "/home/pi/inkslab_collection.json"
LAST_UPDATE_FILE = "/home/pi/inkslab_last_update.json"
STATUS_FILE = "/tmp/inkslab_status.json"
NEXT_TRIGGER = "/tmp/inkslab_next"
COLLECTION_TRIGGER = "/tmp/inkslab_collection_changed"
REDRAW_TRIGGER = "/tmp/inkslab_redraw"
DOWNLOAD_LOG = "/tmp/inkslab_download.log"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

TCG_REGISTRY = {
    "lorcana": {"name": "Disney Lorcana", "path": "/home/pi/inkslab-collections/lorcana", "color": "#C084FC", "download_script": "download_cards_lorcana.py"},
    "mtg":     {"name": "Magic: The Gathering", "path": "/home/pi/inkslab-collections/mtg", "color": "#6BCCBD", "download_script": "download_cards_mtg.py"},
    "pokemon": {"name": "Pokemon", "path": "/home/pi/inkslab-collections/pokemon", "color": "#36A5CA", "download_script": "download_cards_pokemon.py"},
    "manga":   {"name": "Manga", "path": "/home/pi/inkslab-collections/manga", "color": "#F472B6", "download_script": "download_covers_manga.py"},
    "comics":  {"name": "Comics", "path": "/home/pi/inkslab-collections/comics", "color": "#F97316", "download_script": "download_covers_comics.py"},
    "custom":  {"name": "Custom", "path": "/home/pi/inkslab-collections/custom", "color": "#F59E0B", "download_script": None},
}
TCG_LIBRARIES = {k: v["path"] for k, v in TCG_REGISTRY.items()}

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')

DEFAULTS = {
    "active_tcg": "pokemon",
    "rotation_angle": 270,
    "day_interval": 600,
    "night_interval": 3600,
    "day_start": 7,
    "day_end": 23,
    "color_saturation": 2.5,
    "collection_only": False,
    "auto_update_sources": [],
    "auto_update_day": 0,
    "slab_header_mode": "normal",
    "image_fit": "contain",
    "image_bg": "black",
    "thumbnail_cache": False,
}

# Track running download process
_download_proc = None
_download_tcg = None
_download_log_fh = None
_download_lock = threading.Lock()
_run_all_running = False

# --- WIFI SETUP MODE ---
_wifi_setup_mode = False
_wifi_connect_result = {"status": "idle"}
_wifi_connect_lock = threading.Lock()

# --- FILE SAFETY ---
_config_lock = threading.Lock()
_collection_lock = threading.Lock()
_custom_lock = threading.Lock()
MIN_FREE_SPACE_MB = 500  # Refuse writes if less than this much free space


def _atomic_write_json(path, data, indent=None):
    """Write JSON atomically: write to temp file, then os.rename().

    This prevents corruption from power loss or crash mid-write.
    os.rename() is atomic on the same filesystem (always true for /home/pi).
    """
    dir_name = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _check_disk_space(path="/home/pi"):
    """Return free space in MB. Returns 0 if check fails."""
    try:
        st = shutil.disk_usage(path)
        return st.free // (1024 * 1024)
    except Exception:
        return 0


def _has_disk_space(path="/home/pi"):
    """Return True if there's enough free space to safely write."""
    return _check_disk_space(path) >= MIN_FREE_SPACE_MB

# --- AUTH HELPERS ---

def _hash_pin(pin, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt.encode('utf-8'), 260000)
    return dk.hex(), salt

def _verify_pin(pin, stored_hash, salt):
    dk = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt.encode('utf-8'), 260000)
    return secrets.compare_digest(dk.hex(), stored_hash)

def _get_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def protected(f):
    """Require valid auth session + CSRF token for state-changing endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        cfg = load_config()
        if cfg.get('pin_hash') and not session.get('authenticated'):
            return jsonify({'error': 'Authentication required'}), 401
        tok = request.headers.get('X-CSRF-Token', '')
        if not tok or not secrets.compare_digest(tok, session.get('csrf_token', '')):
            return jsonify({'error': 'Invalid CSRF token'}), 403
        return f(*args, **kwargs)
    return decorated


# --- TTL CACHE (avoids re-walking 15,000+ files on every request) ---
_cache = {}
_cache_lock = threading.Lock()


def _cache_get(key, ttl=30):
    """Return cached value if fresh, else None."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry[1]) < ttl:
            return entry[0]
    return None


def _cache_set(key, value):
    """Store a value in cache with current timestamp."""
    with _cache_lock:
        _cache[key] = (value, time.time())


def _cache_invalidate(*keys):
    """Remove specific keys from cache."""
    with _cache_lock:
        for key in keys:
            _cache.pop(key, None)


def _close_download_log():
    """Close the download log file handle if open."""
    global _download_log_fh
    if _download_log_fh:
        try:
            _download_log_fh.close()
        except Exception:
            pass
        _download_log_fh = None


# --- INPUT VALIDATION ---
# All subprocess calls use list form (not shell=True) so shell injection is
# already blocked at the OS level. These validators prevent argument injection
# (e.g. "--flag" passed as a set code becoming an extra CLI flag).

_RE_SET_CODE   = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,31}$')
_RE_YEAR       = re.compile(r'^(19|20)\d{2}$')
_RE_SLUG       = re.compile(r'^[a-zA-Z0-9\-]{1,64}$')  # MangaDex UUIDs, Metron IDs

def _valid_set_code(s):
    return bool(s and isinstance(s, str) and _RE_SET_CODE.match(s))

def _valid_year(s):
    return bool(s and _RE_YEAR.match(str(s)))

def _valid_slug(s):
    return bool(s and isinstance(s, str) and _RE_SLUG.match(s))

def _clean_title(s, maxlen=200):
    """Strip non-printable chars and cap length. Safe for use as a subprocess arg."""
    if not s or not isinstance(s, str):
        return ''
    return re.sub(r'[^\x20-\x7E]', '', s)[:maxlen].strip()

def _valid_pokemon_name(s):
    return bool(s and isinstance(s, str) and re.match(r"^[a-zA-Z0-9 '\-]{1,100}$", s))


# --- METRON CREDENTIAL ENCRYPTION ---
# Uses device serial number as key material so credentials are tied to this Pi.
# Requires python3-cryptography (usually pre-installed on Pi OS).
# Falls back to plaintext with chmod 600 if cryptography is unavailable.

def _get_device_key():
    """Derive a 32-byte key from the Pi serial number."""
    serial = ''
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('Serial'):
                    serial = line.split(':', 1)[1].strip()
                    break
    except Exception:
        pass
    if not serial:
        serial = 'inkslab-device'
    return hashlib.pbkdf2_hmac('sha256', serial.encode(), b'inkslab-metron-v1', 100000)

def _encrypt_creds(username, password):
    """Encrypt credentials. Returns 'enc:<token>' or None if unavailable."""
    try:
        from cryptography.fernet import Fernet
        import base64
        key = base64.urlsafe_b64encode(_get_device_key())
        f = Fernet(key)
        plaintext = json.dumps({'u': username, 'p': password}).encode()
        return 'enc:' + f.encrypt(plaintext).decode()
    except ImportError:
        return None

def _decrypt_creds(data):
    """Decrypt credentials. Returns (username, password) or (None, None)."""
    if not data or not data.startswith('enc:'):
        return None, None
    try:
        from cryptography.fernet import Fernet
        import base64
        key = base64.urlsafe_b64encode(_get_device_key())
        f = Fernet(key)
        plaintext = f.decrypt(data[4:].encode())
        obj = json.loads(plaintext)
        return obj['u'], obj['p']
    except Exception:
        return None, None

def _read_metron_creds():
    """Read Metron credentials from file. Returns (username, password) or (None, None)."""
    creds_file = '/home/pi/.metron_credentials'
    if not os.path.exists(creds_file):
        return None, None
    try:
        creds = {}
        with open(creds_file) as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    creds[k.strip()] = v.strip()
        if creds.get('METRON_ENC'):
            return _decrypt_creds(creds['METRON_ENC'])
        return creds.get('METRON_USERNAME'), creds.get('METRON_PASSWORD')
    except Exception:
        return None, None


# --- HELPERS ---

def load_config():
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f))
        except Exception:
            pass
    return config


def save_config(config):
    try:
        _atomic_write_json(CONFIG_FILE, config, indent=2)
    except Exception as e:
        app.logger.error(f"Failed to save config: {e}")


_collection_cache = None
_collection_cache_mtime = 0.0
_collection_cache_lock = threading.Lock()


def load_collection():
    global _collection_cache, _collection_cache_mtime
    with _collection_cache_lock:
        try:
            mtime = os.path.getmtime(COLLECTION_FILE) if os.path.exists(COLLECTION_FILE) else 0.0
            if _collection_cache is not None and mtime == _collection_cache_mtime:
                return dict(_collection_cache)
            if os.path.exists(COLLECTION_FILE):
                with open(COLLECTION_FILE, 'r') as f:
                    data = json.load(f)
                _collection_cache = data
                _collection_cache_mtime = mtime
                return dict(data)
        except Exception:
            pass
        return {}


def save_collection(data):
    global _collection_cache, _collection_cache_mtime
    try:
        _atomic_write_json(COLLECTION_FILE, data)
        _collection_cache = dict(data)
        _collection_cache_mtime = os.path.getmtime(COLLECTION_FILE)
    except Exception as e:
        app.logger.error(f"Failed to save collection: {e}")
    # Don't signal daemon on individual card toggles - deck rebuilds on next natural cycle


def _is_card_image(filename):
    """Check if a file is a supported card image."""
    return filename.lower().endswith(IMAGE_EXTENSIONS) and not filename.startswith('_')


def rarity_sort_key(rarity):
    """Sort key for rarities — rarest first."""
    order = {
        "special": 1, "mythic rare": 2, "bonus": 3,
        "hyper rare": 1, "special illustration rare": 2, "rare secret": 3,
        "rare rainbow": 4, "illustration rare": 5, "shiny ultra rare": 6,
        "rare ultra": 7, "ultra rare": 7, "double rare": 8, "ace spec rare": 8,
        "rare holo vstar": 9, "rare holo vmax": 9, "rare holo v": 10,
        "rare holo gx": 10, "rare holo ex": 10, "shiny rare": 11,
        "rare holo": 12, "rare prism star": 12, "rare": 15,
        "uncommon": 20, "common": 30, "promo": 25,
        # Lorcana rarities
        "enchanted": 1, "legendary": 5, "super rare": 8,
    }
    return order.get(rarity.lower().strip(), 15)


def get_local_ip():
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        parts = result.stdout.strip().split()
        return parts[0] if parts else None
    except Exception:
        return None


# --- AUTH ROUTES ---

@app.route('/api/auth/status')
def api_auth_status():
    cfg = load_config()
    pin_configured = bool(cfg.get('pin_hash'))
    setup_done = bool(cfg.get('pin_setup_done'))
    authenticated = bool(session.get('authenticated'))
    return jsonify({
        'pin_configured': pin_configured,
        'setup_done': setup_done,
        'authenticated': authenticated or not pin_configured,
    })


@app.route('/api/auth/setup', methods=['POST'])
def api_auth_setup():
    """First-time PIN setup or skip. No auth/CSRF required (bootstrap)."""
    cfg = load_config()
    if cfg.get('pin_hash'):
        return jsonify({'ok': False, 'error': 'PIN already configured'}), 400
    data = request.get_json(force=True) or {}
    pin = data.get('pin', '').strip()
    if pin:
        if not re.match(r'^\d{4,8}$', pin):
            return jsonify({'ok': False, 'error': 'PIN must be 4-8 digits'})
        h, salt = _hash_pin(pin)
        cfg['pin_hash'] = h
        cfg['pin_salt'] = salt
        save_config(cfg)
    cfg['pin_setup_done'] = True
    save_config(cfg)
    session['authenticated'] = True
    session.permanent = True
    tok = _get_csrf_token()
    return jsonify({'ok': True, 'skipped': not pin, 'csrf_token': tok})


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """PIN login. No CSRF required (creates the session)."""
    data = request.get_json(force=True) or {}
    pin = data.get('pin', '').strip()
    cfg = load_config()
    if not cfg.get('pin_hash'):
        session['authenticated'] = True
        session.permanent = True
        tok = _get_csrf_token()
        return jsonify({'ok': True, 'csrf_token': tok})
    if not _verify_pin(pin, cfg['pin_hash'], cfg['pin_salt']):
        return jsonify({'ok': False, 'error': 'Incorrect PIN'})
    session['authenticated'] = True
    session.permanent = True
    tok = _get_csrf_token()
    return jsonify({'ok': True, 'csrf_token': tok})


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/auth/change_pin', methods=['POST'])
def api_auth_change_pin():
    """Change or remove PIN. Requires auth + CSRF."""
    cfg = load_config()
    if cfg.get('pin_hash') and not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    tok = request.headers.get('X-CSRF-Token', '')
    if not tok or not secrets.compare_digest(tok, session.get('csrf_token', '')):
        return jsonify({'error': 'Invalid CSRF token'}), 403
    data = request.get_json(force=True) or {}
    current_pin = data.get('current_pin', '').strip()
    new_pin = data.get('new_pin', '').strip()
    cfg = load_config()
    if cfg.get('pin_hash'):
        if not _verify_pin(current_pin, cfg['pin_hash'], cfg['pin_salt']):
            return jsonify({'ok': False, 'error': 'Current PIN incorrect'})
    if not new_pin:
        cfg.pop('pin_hash', None)
        cfg.pop('pin_salt', None)
    else:
        if not re.match(r'^\d{4,8}$', new_pin):
            return jsonify({'ok': False, 'error': 'PIN must be 4-8 digits'})
        h, salt = _hash_pin(new_pin)
        cfg['pin_hash'] = h
        cfg['pin_salt'] = salt
    save_config(cfg)
    return jsonify({'ok': True})


# --- API ROUTES ---

_warmed_keys = set()

def _warm_one_thumb(tcg, set_id, card_id):
    """Queue background thumbnail generation for one card. No-op if already cached or queued."""
    key = (tcg, os.path.basename(set_id), os.path.basename(card_id))
    if key in _warmed_keys:
        return
    thumb_path = os.path.join(THUMB_CACHE_DIR, key[0], key[1], key[2] + '.jpg')
    if os.path.exists(thumb_path):
        _warmed_keys.add(key)
        return
    library = TCG_LIBRARIES.get(tcg)
    if not library or not _PIL_OK:
        return
    card_path = None
    for ext in IMAGE_EXTENSIONS:
        p = os.path.join(library, key[1], key[2] + ext)
        if os.path.exists(p):
            card_path = p
            break
    if not card_path:
        return
    _warmed_keys.add(key)
    def _gen(cp=card_path, tp=thumb_path):
        with _thumb_lock:
            try:
                os.makedirs(os.path.dirname(tp), exist_ok=True)
                img = _PIL_Image.open(cp)
                img.thumbnail(THUMB_SIZE, _PIL_Image.LANCZOS)
                img = img.convert('RGB')
                img.save(tp, 'JPEG', quality=72, optimize=True)
                img.close()
                del img
            except Exception as e:
                logging.warning('Warm thumb failed for %s: %s', cp, e)
    threading.Thread(target=_gen, daemon=True).start()


def _warm_current_thumb(status):
    """Warm thumbnails for the current card + all queue cards."""
    tcg = status.get('tcg')
    if not tcg:
        return
    cards = []
    if status.get('set_id') and status.get('card_id'):
        cards.append((status['set_id'], status['card_id']))
    for c in status.get('next_cards', []) + status.get('prev_cards', []):
        if c.get('set_id') and c.get('card_id'):
            cards.append((c['set_id'], c['card_id']))
    for set_id, card_id in cards:
        _warm_one_thumb(tcg, set_id, card_id)


@app.route('/api/status')
def api_status():
    status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        except Exception:
            pass
    # Auto-clear stale flags (e.g. if daemon crashed mid-update)
    if status.get('pending') and time.time() - status.get('timestamp', 0) > 60:
        status.pop('pending', None)
    if status.get('display_updating') and time.time() - status.get('timestamp', 0) > 60:
        status.pop('display_updating', None)
    status['collection_only'] = load_config().get('collection_only', False)
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            status['cpu_temp'] = round(int(f.read().strip()) / 1000)
    except Exception:
        pass
    # Check if thumbnail is already cached for the current display card
    tcg = status.get('tcg')
    set_id = status.get('set_id')
    card_id = status.get('card_id')
    if tcg and set_id and card_id:
        thumb_path = os.path.join(THUMB_CACHE_DIR, tcg, os.path.basename(set_id), os.path.basename(card_id) + '.jpg')
        status['thumb_ready'] = os.path.exists(thumb_path)
    _warm_current_thumb(status)
    return jsonify(status)


@app.route('/api/config', methods=['GET'])
def api_get_config():
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
@protected
def api_set_config():
    updates = request.get_json(force=True)
    with _config_lock:
        config = load_config()
        # Only track keys that actually changed value
        changed = {k for k in updates if k in DEFAULTS and config.get(k) != updates[k]}
        for key in DEFAULTS:
            if key in updates:
                config[key] = updates[key]
        save_config(config)

    # Only active_tcg forces an immediate card advance
    if 'active_tcg' in changed:
        # Write interim status so the web UI reflects the change instantly
        try:
            status = {}
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    status = json.load(f)
            status['tcg'] = updates['active_tcg']
            status['pending'] = 'Switching to ' + updates['active_tcg'].upper() + '...'
            status['timestamp'] = int(time.time())
            status.pop('display_updating', None)
            _atomic_write_json(STATUS_FILE, status)
        except Exception:
            pass
        try:
            with open(NEXT_TRIGGER, 'w') as f:
                f.write('1')
        except OSError:
            pass
    elif changed & {'color_saturation', 'slab_header_mode', 'rotation_angle', 'image_fit', 'image_bg'}:
        # Re-render the current card with new display settings, no advance
        try:
            with open(REDRAW_TRIGGER, 'w') as f:
                f.write('1')
        except OSError:
            pass
    # Start or stop background thumbnail caching when the toggle changes
    if 'thumbnail_cache' in changed:
        if config.get('thumbnail_cache'):
            _start_precache_thread()
        else:
            with _precache_lock:
                _precache_state['stop'] = True
    # collection_only and interval/timing changes take effect on next natural card advance
    return jsonify(config)


@app.route('/api/next', methods=['POST'])
@protected
def api_next():
    try:
        with open(NEXT_TRIGGER, 'w') as f:
            f.write('1')
        # Write interim status so web UI shows "loading" immediately
        try:
            status = {}
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    status = json.load(f)
            status['pending'] = 'Loading next card...'
            status['timestamp'] = int(time.time())
            status.pop('display_updating', None)
            _atomic_write_json(STATUS_FILE, status)
        except Exception:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


PREV_TRIGGER = "/tmp/inkslab_prev"
PAUSE_FILE = "/tmp/inkslab_pause"


@app.route('/api/prev', methods=['POST'])
@protected
def api_prev():
    try:
        with open(PREV_TRIGGER, 'w') as f:
            f.write('1')
        try:
            status = {}
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    status = json.load(f)
            status['pending'] = 'Loading previous card...'
            status['timestamp'] = int(time.time())
            status.pop('display_updating', None)
            _atomic_write_json(STATUS_FILE, status)
        except Exception:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/api/pause', methods=['POST'])
@protected
def api_pause():
    """Toggle pause state. Returns new paused state."""
    if os.path.exists(PAUSE_FILE):
        try:
            os.remove(PAUSE_FILE)
        except OSError:
            pass
        paused = False
    else:
        try:
            with open(PAUSE_FILE, 'w') as f:
                f.write('1')
        except OSError:
            pass
        paused = True
    # Update status file so web UI reflects immediately
    try:
        status = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        status['paused'] = paused
        if not paused and status.get('interval'):
            status['next_change'] = int(time.time()) + status['interval']
        elif paused:
            status['next_change'] = 0
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except Exception:
        pass
    return jsonify({"ok": True, "paused": paused})


@app.route('/api/ip')
def api_ip():
    return jsonify({"ip": get_local_ip()})


@app.route('/api/system')
def api_system():
    info = {}
    # CPU temp
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            info['cpu_temp'] = round(int(f.read().strip()) / 1000)
    except Exception:
        pass
    # RAM from /proc/meminfo
    try:
        meminfo = {}
        with open('/proc/meminfo') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
        total_kb = meminfo.get('MemTotal', 0)
        avail_kb = meminfo.get('MemAvailable', 0)
        used_kb = total_kb - avail_kb
        info['ram_total_mb'] = round(total_kb / 1024)
        info['ram_used_mb'] = round(used_kb / 1024)
        info['ram_free_mb'] = round(avail_kb / 1024)
    except Exception:
        pass
    # Uptime
    try:
        with open('/proc/uptime') as f:
            secs = float(f.read().split()[0])
        days = int(secs // 86400)
        hours = int((secs % 86400) // 3600)
        mins = int((secs % 3600) // 60)
        if days > 0:
            info['uptime'] = f'{days}d {hours}h {mins}m'
        elif hours > 0:
            info['uptime'] = f'{hours}h {mins}m'
        else:
            info['uptime'] = f'{mins}m'
    except Exception:
        pass
    return jsonify(info)


@app.route('/api/card_image')
def api_current_card_image():
    """Serve the current card image from the display status."""
    allowed_dirs = list(TCG_LIBRARIES.values())
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
            card_path = status.get("card_path")
            if card_path and os.path.exists(card_path):
                # Validate path is within a known card directory
                real = os.path.realpath(card_path)
                if not any(real == os.path.realpath(d) or real.startswith(os.path.realpath(d) + os.sep) for d in allowed_dirs):
                    return '', 403
                mime = 'image/png' if card_path.lower().endswith('.png') else 'image/jpeg'
                resp = send_file(card_path, mimetype=mime)
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return resp
        except Exception:
            pass
    return '', 404


@app.route('/api/card_image/<tcg>/<set_id>/<card_id>')
def api_card_image(tcg, set_id, card_id):
    """Serve a specific card image on demand."""
    library = TCG_LIBRARIES.get(tcg)
    if not library:
        return '', 404
    # Sanitize to prevent path traversal
    safe_set = os.path.basename(set_id)
    safe_card = os.path.basename(card_id)
    for ext in IMAGE_EXTENSIONS:
        card_path = os.path.join(library, safe_set, safe_card + ext)
        if os.path.exists(card_path):
            mime = 'image/png' if ext == '.png' else 'image/jpeg'
            resp = send_file(card_path, mimetype=mime)
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            return resp
    return '', 404


@app.route('/api/card_thumbnail/<tcg>/<set_id>/<card_id>')
def api_card_thumbnail(tcg, set_id, card_id):
    """Serve a small cached JPEG thumbnail for grid views."""
    library = TCG_LIBRARIES.get(tcg)
    if not library:
        return '', 404
    safe_set = os.path.basename(set_id)
    safe_card = os.path.basename(card_id)
    card_path = None
    for ext in IMAGE_EXTENSIONS:
        p = os.path.join(library, safe_set, safe_card + ext)
        if os.path.exists(p):
            card_path = p
            break
    if not card_path:
        logging.warning('Thumbnail 404: %s/%s/%s', tcg, safe_set, safe_card)
        return '', 404

    thumb_path = os.path.join(THUMB_CACHE_DIR, tcg, safe_set, safe_card + '.jpg')

    # Always serve existing thumbnail if on disk (regardless of toggle)
    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
        resp = send_file(thumb_path, mimetype='image/jpeg')
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return resp
    elif os.path.exists(thumb_path):
        # 0-byte file from a previous failed generation — delete and regenerate
        try:
            os.remove(thumb_path)
        except Exception:
            pass

    # No cached thumbnail — generate on demand (toggle only controls background pre-cache)
    if _PIL_OK:
        with _thumb_lock:  # one PIL op at a time — prevents OOM on Pi Zero
            try:
                os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                img = _PIL_Image.open(card_path)
                img.thumbnail(THUMB_SIZE, _PIL_Image.LANCZOS)
                img = img.convert('RGB')
                img.save(thumb_path, 'JPEG', quality=72, optimize=True)
                img.close()
                del img
                if os.path.getsize(thumb_path) > 0:
                    resp = send_file(thumb_path, mimetype='image/jpeg')
                    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
                    return resp
                os.remove(thumb_path)
            except Exception as e:
                logging.warning('Thumbnail gen failed for %s: %s', card_path, e)

    # Fallback: full image — no-cache so browser retries next time
    ext_lower = card_path.lower()
    if ext_lower.endswith('.png'):
        mime = 'image/png'
    elif ext_lower.endswith('.webp'):
        mime = 'image/webp'
    else:
        mime = 'image/jpeg'
    resp = send_file(card_path, mimetype=mime)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


_precache_state = {'running': False, 'done': 0, 'total': 0, 'stop': False}
_precache_lock = threading.Lock()


def _start_precache_thread():
    """Start background thumbnail generation if not already running."""
    with _precache_lock:
        if _precache_state['running']:
            return
        _precache_state.update({'running': True, 'done': 0, 'total': 0, 'stop': False})

    def _run():
        try:
            jobs = []
            for tcg, lib in TCG_LIBRARIES.items():
                if not os.path.exists(lib):
                    continue
                for set_id in os.listdir(lib):
                    set_path = os.path.join(lib, set_id)
                    if not os.path.isdir(set_path):
                        continue
                    for fname in os.listdir(set_path):
                        if _is_card_image(fname):
                            card_id = os.path.splitext(fname)[0]
                            jobs.append((tcg, set_id, card_id, os.path.join(set_path, fname)))
            with _precache_lock:
                _precache_state['total'] = len(jobs)
            for i, (tcg, set_id, card_id, card_path) in enumerate(jobs):
                with _precache_lock:
                    if _precache_state.get('stop'):
                        break
                thumb_path = os.path.join(THUMB_CACHE_DIR, tcg, set_id, card_id + '.jpg')
                generated = False
                if not os.path.exists(thumb_path) and _PIL_OK:
                    try:
                        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                        img = _PIL_Image.open(card_path)
                        img.thumbnail(THUMB_SIZE, _PIL_Image.LANCZOS)
                        img = img.convert('RGB')
                        img.save(thumb_path, 'JPEG', quality=72, optimize=True)
                        img.close()
                        del img
                        generated = True
                    except Exception:
                        pass
                with _precache_lock:
                    _precache_state['done'] = i + 1
                if generated:
                    time.sleep(3.0)  # slow & safe — fine to run while display is cycling
        finally:
            with _precache_lock:
                _precache_state['running'] = False
            _cache_invalidate('storage')

    threading.Thread(target=_run, daemon=True).start()


@app.route('/api/thumbnails/progress')
def api_thumbnails_progress():
    with _precache_lock:
        return jsonify(dict(_precache_state))


@app.route('/api/tcg_list')
def api_tcg_list():
    """Return the TCG registry for dynamic UI generation."""
    return app.response_class(json.dumps(TCG_REGISTRY), mimetype='application/json')


@app.route('/api/sets')
def api_sets():
    config = load_config()
    tcg = request.args.get('tcg', config['active_tcg'])
    library = TCG_LIBRARIES.get(tcg)
    if not library or not os.path.exists(library):
        return jsonify([])

    cache_key = 'sets_' + tcg
    sets_cache = _cache_get(cache_key, ttl=300)

    master = {}
    index_path = os.path.join(library, "master_index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r') as f:
                master = json.load(f)
        except Exception:
            pass

    collection = load_collection()
    owned_ids = set(collection.get(tcg, []))

    if sets_cache:
        # Fast path: recompute owned counts from cached card IDs
        result = []
        for s in sets_cache:
            owned_count = sum(1 for cid in s["_cids"] if cid in owned_ids)
            result.append({
                "id": s["id"], "name": s["name"], "year": s["year"],
                "card_count": s["card_count"], "owned_count": owned_count,
            })
        result.sort(key=lambda x: x["year"], reverse=True)
        return jsonify(result)

    # Slow path: read _data.json per set (faster than listing 300+ .png files per dir)
    sets_data = []
    result = []
    for d in sorted(os.listdir(library)):
        set_path = os.path.join(library, d)
        if not os.path.isdir(set_path):
            continue
        data_file = os.path.join(set_path, "_data.json")
        card_ids = []
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r') as f:
                    card_ids = list(json.load(f).keys())
            except Exception:
                pass
        if not card_ids:
            card_ids = [os.path.splitext(f)[0] for f in os.listdir(set_path)
                        if _is_card_image(f)]
        owned_count = sum(1 for cid in card_ids if cid in owned_ids)
        info = master.get(d, {})
        sets_data.append({
            "id": d, "name": info.get("name", d), "year": info.get("year", ""),
            "card_count": len(card_ids), "_cids": card_ids,
        })
        result.append({
            "id": d, "name": info.get("name", d), "year": info.get("year", ""),
            "card_count": len(card_ids), "owned_count": owned_count,
        })

    _cache_set(cache_key, sets_data)
    result.sort(key=lambda x: x["year"], reverse=True)
    return jsonify(result)


@app.route('/api/sets/<set_id>/cards')
def api_set_cards(set_id):
    config = load_config()
    tcg = request.args.get('tcg', config['active_tcg'])
    library = TCG_LIBRARIES.get(tcg)
    if not library:
        return jsonify([])

    set_path = os.path.join(library, os.path.basename(set_id))
    if not os.path.isdir(set_path):
        return jsonify([])

    metadata = {}
    data_file = os.path.join(set_path, "_data.json")
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r') as f:
                metadata = json.load(f)
        except Exception:
            pass

    collection = load_collection()
    owned_ids = set(collection.get(tcg, []))

    cards = []
    for f in sorted(os.listdir(set_path)):
        if not _is_card_image(f):
            continue
        card_id = os.path.splitext(f)[0]
        info = metadata.get(card_id, {})
        cards.append({
            "id": card_id,
            "name": info.get("name", card_id),
            "number": info.get("number", "?"),
            "rarity": info.get("rarity", ""),
            "owned": card_id in owned_ids,
            "set_id": set_id,
        })

    cards.sort(key=lambda x: (float(x["number"]) if x["number"].replace('.', '', 1).isdigit() else float('inf'), x["number"]))
    return jsonify(cards)


@app.route('/api/collection/toggle', methods=['POST'])
@protected
def api_collection_toggle():
    data = request.get_json(force=True)
    card_id = data.get("card_id")
    if not card_id:
        return jsonify({"error": "card_id required"}), 400
    if not isinstance(card_id, str) or len(card_id) > 128 or not card_id.replace('-', '').replace('_', '').replace('.', '').isalnum():
        return jsonify({"error": "invalid card_id"}), 400

    config = load_config()
    tcg = data.get("tcg", config["active_tcg"])

    with _collection_lock:
        collection = load_collection()
        if tcg not in collection:
            collection[tcg] = []

        if card_id in collection[tcg]:
            collection[tcg].remove(card_id)
            owned = False
        else:
            collection[tcg].append(card_id)
            owned = True

        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    if config.get("collection_only"):
        try: open(COLLECTION_TRIGGER, 'w').close()
        except Exception: pass
    return jsonify({"card_id": card_id, "owned": owned})


@app.route('/api/collection/toggle_set', methods=['POST'])
@protected
def api_collection_toggle_set():
    data = request.get_json(force=True)
    set_id = data.get("set_id")
    owned = data.get("owned", True)
    if not set_id:
        return jsonify({"error": "set_id required"}), 400

    config = load_config()
    tcg = data.get("tcg", config["active_tcg"])
    library = TCG_LIBRARIES.get(tcg)
    if not library:
        return jsonify({"error": "invalid tcg"}), 400

    safe_set = os.path.basename(set_id)
    set_path = os.path.join(library, safe_set)
    if not os.path.isdir(set_path):
        return jsonify({"error": "set not found"}), 404

    card_ids = [os.path.splitext(f)[0] for f in os.listdir(set_path)
                if _is_card_image(f)]

    with _collection_lock:
        collection = load_collection()
        if tcg not in collection:
            collection[tcg] = []

        if owned:
            existing = set(collection[tcg])
            for cid in card_ids:
                if cid not in existing:
                    collection[tcg].append(cid)
        else:
            remove_set = set(card_ids)
            collection[tcg] = [cid for cid in collection[tcg] if cid not in remove_set]

        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    if config.get("collection_only"):
        try: open(COLLECTION_TRIGGER, 'w').close()
        except Exception: pass
    return jsonify({"set_id": set_id, "owned": owned, "count": len(card_ids)})


@app.route('/api/collection/clear', methods=['POST'])
@protected
def api_collection_clear():
    data = request.get_json(force=True) if request.data else {}
    config = load_config()
    tcg = data.get("tcg", config["active_tcg"])
    with _collection_lock:
        collection = load_collection()
        collection[tcg] = []
        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    return jsonify({"ok": True})


@app.route('/api/rarities')
def api_rarities():
    """Return rarity objects with card counts for the active TCG, sorted rarest first."""
    config = load_config()
    tcg = request.args.get('tcg', config['active_tcg'])
    cache_key = 'rarities_' + tcg
    cached = _cache_get(cache_key, ttl=300)
    if cached:
        return jsonify(cached)

    library = TCG_LIBRARIES.get(tcg)
    rarity_counts = {}
    collection = load_collection()
    owned_ids = set(collection.get(tcg, []))
    rarity_owned = {}

    if library and os.path.isdir(library):
        for d in os.listdir(library):
            data_file = os.path.join(library, d, "_data.json")
            if not os.path.exists(data_file):
                continue
            try:
                with open(data_file, 'r') as f:
                    data = json.load(f)
                for card_id, card in data.items():
                    r = card.get("rarity", "")
                    if r:
                        rarity_counts[r] = rarity_counts.get(r, 0) + 1
                        if card_id in owned_ids:
                            rarity_owned[r] = rarity_owned.get(r, 0) + 1
            except Exception:
                pass

    result = [{"name": r, "count": rarity_counts[r], "owned": rarity_owned.get(r, 0)}
              for r in sorted(rarity_counts.keys(), key=rarity_sort_key)]

    _cache_set(cache_key, result)
    return jsonify(result)


@app.route('/api/collection/toggle_all', methods=['POST'])
@protected
def api_collection_toggle_all():
    """Select or deselect ALL cards for the active TCG in one request."""
    body = request.get_json(force=True)
    owned = body.get("owned", True)
    config = load_config()
    tcg = body.get("tcg", config["active_tcg"])
    library = TCG_LIBRARIES.get(tcg)
    if not library or not os.path.isdir(library):
        return jsonify({"error": "invalid tcg"}), 400

    # Walk library outside the lock — this can be slow on SD card
    all_ids = set()
    if owned:
        for d in os.listdir(library):
            set_path = os.path.join(library, d)
            if not os.path.isdir(set_path):
                continue
            for f in os.listdir(set_path):
                if _is_card_image(f):
                    all_ids.add(os.path.splitext(f)[0])

    with _collection_lock:
        collection = load_collection()
        if tcg not in collection:
            collection[tcg] = []
        if not owned:
            count = len(collection[tcg])
            collection[tcg] = []
        else:
            collection[tcg] = list(all_ids)
            count = len(all_ids)
        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    if config.get("collection_only"):
        try: open(COLLECTION_TRIGGER, 'w').close()
        except Exception: pass
    return jsonify({"owned": owned, "count": count})


@app.route('/api/collection/toggle_batch', methods=['POST'])
@protected
def api_collection_toggle_batch():
    """Add or remove a specific list of card_ids in one request."""
    body = request.get_json(force=True)
    card_ids = body.get("card_ids", [])
    owned = body.get("owned", True)
    config = load_config()
    tcg = body.get("tcg", config["active_tcg"])

    with _collection_lock:
        collection = load_collection()
        if tcg not in collection:
            collection[tcg] = []

        if owned:
            existing = set(collection[tcg])
            for cid in card_ids:
                if cid not in existing:
                    collection[tcg].append(cid)
                    existing.add(cid)
        else:
            remove = set(card_ids)
            collection[tcg] = [c for c in collection[tcg] if c not in remove]

        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    if config.get("collection_only"):
        try: open(COLLECTION_TRIGGER, 'w').close()
        except Exception: pass
    return jsonify({"owned": owned, "count": len(card_ids)})


@app.route('/api/collection/toggle_rarity', methods=['POST'])
@protected
def api_collection_toggle_rarity():
    """Select or deselect all cards of a given rarity. Optionally scoped to a single set."""
    body = request.get_json(force=True)
    rarity = body.get("rarity")
    owned = body.get("owned", True)
    set_id = body.get("set_id")  # optional — None means all sets

    if not rarity:
        return jsonify({"error": "rarity required"}), 400

    config = load_config()
    tcg = body.get("tcg", config["active_tcg"])
    library = TCG_LIBRARIES.get(tcg)
    if not library or not os.path.isdir(library):
        return jsonify({"error": "invalid tcg or no data"}), 400

    # Find all card IDs matching the rarity
    matching_ids = []
    if set_id:
        dirs_to_scan = [os.path.basename(set_id)]
    else:
        dirs_to_scan = [d for d in os.listdir(library)
                        if os.path.isdir(os.path.join(library, d))]
    for d in dirs_to_scan:
        data_file = os.path.join(library, d, "_data.json")
        if not os.path.exists(data_file):
            continue
        try:
            with open(data_file, 'r') as f:
                cards_data = json.load(f)
            for card_id, card_info in cards_data.items():
                if card_info.get("rarity") == rarity:
                    matching_ids.append(card_id)
        except Exception:
            pass

    # Update collection
    with _collection_lock:
        collection = load_collection()
        if tcg not in collection:
            collection[tcg] = []

        if owned:
            existing = set(collection[tcg])
            for cid in matching_ids:
                if cid not in existing:
                    collection[tcg].append(cid)
        else:
            remove_set = set(matching_ids)
            collection[tcg] = [cid for cid in collection[tcg] if cid not in remove_set]

        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    if config.get("collection_only"):
        try: open(COLLECTION_TRIGGER, 'w').close()
        except Exception: pass
    return jsonify({"rarity": rarity, "owned": owned, "count": len(matching_ids)})


@app.route('/api/search')
def api_search():
    """Search card names across all sets. Returns up to 100 matches."""
    q = request.args.get('q', '').strip().lower()
    if len(q) < 2:
        return jsonify([])

    config = load_config()
    tcg = request.args.get('tcg', config['active_tcg'])
    library = TCG_LIBRARIES.get(tcg)
    if not library or not os.path.isdir(library):
        return jsonify([])

    cache_key = f'search_{tcg}_{q}'
    cached = _cache_get(cache_key, ttl=30)
    if cached is not None:
        return jsonify(cached)

    master = {}
    index_path = os.path.join(library, "master_index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r') as f:
                master = json.load(f)
        except Exception:
            pass

    collection = load_collection()
    owned_ids = set(collection.get(tcg, []))

    results = []
    sets_searched = 0
    for d in os.listdir(library):
        data_file = os.path.join(library, d, "_data.json")
        if not os.path.exists(data_file):
            continue
        sets_searched += 1
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            set_info = master.get(d, {})
            for card_id, card in data.items():
                name = card.get("name", "")
                if q in name.lower():
                    results.append({
                        "id": card_id,
                        "name": name,
                        "number": card.get("number", "?"),
                        "rarity": card.get("rarity", ""),
                        "set_id": d,
                        "set_name": set_info.get("name", d),
                        "owned": card_id in owned_ids,
                    })
        except Exception:
            pass

    results.sort(key=lambda x: (x["name"].lower(), x["set_id"]))
    total = len(results)
    payload = {"results": results[:200], "total": total, "sets_searched": sets_searched}
    _cache_set(cache_key, payload)
    return jsonify(payload)


@app.route('/api/collection/favorites')
def api_favorites_get():
    """Return the favorites list for the active TCG."""
    config = load_config()
    tcg = config["active_tcg"]
    collection = load_collection()
    favs = collection.get("_favorites", {}).get(tcg, [])
    return jsonify(favs)


@app.route('/api/collection/favorites', methods=['POST'])
@protected
def api_favorites_set():
    """Add or remove a favorite name. Also batch-adds/removes all matching card IDs."""
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    owned = body.get("owned", True)
    if not name:
        return jsonify({"error": "name required"}), 400

    config = load_config()
    tcg = body.get("tcg", config["active_tcg"])

    # Find matching card IDs (read-only, outside lock)
    library = TCG_LIBRARIES.get(tcg)
    matching_ids = []
    if library and os.path.isdir(library):
        for d in os.listdir(library):
            data_file = os.path.join(library, d, "_data.json")
            if not os.path.exists(data_file):
                continue
            try:
                with open(data_file, 'r') as f:
                    data = json.load(f)
                for card_id, card in data.items():
                    if card.get("name", "").lower() == name.lower():
                        matching_ids.append(card_id)
            except Exception:
                pass

    with _collection_lock:
        collection = load_collection()

        # Manage favorites list
        if "_favorites" not in collection:
            collection["_favorites"] = {}
        if tcg not in collection["_favorites"]:
            collection["_favorites"][tcg] = []

        favs = collection["_favorites"][tcg]

        if owned:
            if not any(f.lower() == name.lower() for f in favs):
                favs.append(name)
        else:
            collection["_favorites"][tcg] = [f for f in favs if f.lower() != name.lower()]

        if tcg not in collection:
            collection[tcg] = []

        if owned:
            existing = set(collection[tcg])
            for cid in matching_ids:
                if cid not in existing:
                    collection[tcg].append(cid)
                    existing.add(cid)
        else:
            remove = set(matching_ids)
            collection[tcg] = [c for c in collection[tcg] if c not in remove]

        save_collection(collection)
    _cache_invalidate('rarities_' + tcg)
    return jsonify({"name": name, "owned": owned, "count": len(matching_ids)})


@app.route('/api/download/start', methods=['POST'])
@protected
def api_download_start():
    global _download_proc, _download_tcg, _download_log_fh

    with _download_lock:
        if _download_proc and _download_proc.poll() is None:
            return jsonify({"ok": False, "error": "Download already running"})

        # Close any leftover file handle from a previous download
        _close_download_log()

        if not _has_disk_space():
            return jsonify({"ok": False, "error": "Not enough storage space. Delete some cards first."})

        data = request.get_json(force=True) if request.data else {}
        tcg = data.get("tcg", "pokemon")
        since = data.get("since")

        reg = TCG_REGISTRY.get(tcg)
        if not reg or not reg.get("download_script"):
            return jsonify({"ok": False, "error": "Unknown TCG or no download script"})

        cmd = ["python3", os.path.join(SCRIPT_DIR, "scripts", reg["download_script"])]
        if tcg == "mtg" and since:
            if not _valid_year(since):
                return jsonify({"ok": False, "error": "Invalid year"})
            cmd.extend(["--since", str(int(since))])
        if tcg == "mtg" and data.get("mtg_set"):
            mtg_set = data.get("mtg_set")
            if not _valid_set_code(mtg_set):
                return jsonify({"ok": False, "error": "Invalid set code"})
            cmd.extend(["--set", mtg_set])
        if tcg == "lorcana" and data.get("set_code"):
            set_code = data.get("set_code")
            if not _valid_set_code(set_code):
                return jsonify({"ok": False, "error": "Invalid set code"})
            cmd.extend(["--set", set_code])

        if tcg == "pokemon" and data.get("pokemon_name"):
            pname = data.get("pokemon_name")
            if not _valid_pokemon_name(pname):
                return jsonify({"ok": False, "error": "Invalid Pokemon name"})
            cmd = ["python3", os.path.join(SCRIPT_DIR, "scripts", "download_pokemon_bulk.py"),
                   "--name", pname]
        if tcg == "manga":
            manga_id = data.get("manga_id")
            manga_title = _clean_title(data.get("manga_title", ""))
            if manga_id and manga_title:
                if not _valid_slug(manga_id):
                    return jsonify({"ok": False, "error": "Invalid manga ID"})
                cmd = ["python3", os.path.join(SCRIPT_DIR, "scripts", "download_manga_series.py"),
                       "--id", manga_id, "--title", manga_title]

        if tcg == "comics":
            comic_id = data.get("comic_id")
            comic_title = _clean_title(data.get("comic_title", ""))
            if comic_id and comic_title:
                if not re.match(r'^\d{1,10}$', str(comic_id)):
                    return jsonify({"ok": False, "error": "Invalid comic ID"})
                cmd = ["python3", os.path.join(SCRIPT_DIR, "scripts", "download_comic_series.py"),
                       "--id", str(int(comic_id)), "--title", comic_title]

        _download_log_fh = open(DOWNLOAD_LOG, 'w')
        _download_log_fh.write('Download started on ' + time.strftime('%B %-d, %Y at %-I:%M') + time.strftime('%p').lower() + '\n\n')
        _download_log_fh.flush()
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        try:
            _download_proc = subprocess.Popen(
                cmd, stdout=_download_log_fh, stderr=subprocess.STDOUT,
                cwd=SCRIPT_DIR, env=env
            )
        except Exception as e:
            _close_download_log()
            return jsonify({"ok": False, "error": "Failed to start download."})
        _download_tcg = tcg

        return jsonify({"ok": True, "tcg": tcg, "pid": _download_proc.pid})


@app.route('/api/download/stop', methods=['POST'])
@protected
def api_download_stop():
    global _download_proc, _download_tcg

    with _download_lock:
        if _download_proc and _download_proc.poll() is None:
            try:
                _download_proc.send_signal(signal.SIGTERM)
                _download_proc.wait(timeout=5)
            except Exception:
                try:
                    _download_proc.kill()
                except Exception:
                    pass
            _download_proc = None
            _download_tcg = None
            _close_download_log()
            return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "No download running"})

@app.route('/api/delete_series', methods=['POST'])
@protected
def api_delete_series():
    """Delete a specific series folder from the active TCG library."""
    data = request.get_json(force=True) if request.data else {}
    tcg = data.get('tcg')
    set_id = data.get('set_id')
    if not tcg or not set_id:
        return jsonify({'ok': False, 'error': 'Missing tcg or set_id'})
    library = TCG_LIBRARIES.get(tcg)
    if not library:
        return jsonify({'ok': False, 'error': 'Unknown TCG'})
    safe_set = os.path.basename(set_id)
    series_path = os.path.join(library, safe_set)
    real = os.path.realpath(series_path)
    real_lib = os.path.realpath(library)
    if not (real == real_lib or real.startswith(real_lib + os.sep)):
        return jsonify({'ok': False, 'error': 'Invalid path'})
    if not os.path.isdir(series_path):
        return jsonify({'ok': False, 'error': 'Series not found'})
    try:
        # Read card IDs before deletion so we can clean the collection
        card_ids_in_set = set()
        data_file = os.path.join(series_path, '_data.json')
        if os.path.exists(data_file):
            try:
                with open(data_file) as f:
                    card_ids_in_set = set(json.load(f).keys())
            except Exception:
                pass

        shutil.rmtree(series_path)

        # Remove deleted card IDs from collection file
        if card_ids_in_set:
            with _collection_lock:
                coll = load_collection()
                if tcg in coll:
                    coll[tcg] = [c for c in coll.get(tcg, []) if c not in card_ids_in_set]
                    save_collection(coll)

        # Remove from master_index.json if present
        index_path = os.path.join(library, 'master_index.json')
        if os.path.exists(index_path):
            try:
                with open(index_path) as f:
                    idx = json.load(f)
                idx.pop(safe_set, None)
                to_remove = [k for k in idx if os.path.basename(k) == safe_set or k == safe_set]
                for k in to_remove:
                    idx.pop(k, None)
                _atomic_write_json(index_path, idx, ensure_ascii=False, indent=2)
            except Exception:
                pass
        _cache_invalidate('sets_' + tcg, 'rarities_' + tcg)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/manga/search')
def api_manga_search():
    """Search MangaDex for manga titles."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
    try:
        import requests as req
        params = {
            "title": query,
            "limit": 10,
            "contentRating[]": ["safe", "suggestive", "erotica"],
            "order[relevance]": "desc",
        }
        r = req.get("https://api.mangadex.org/manga", params=params, timeout=10,
                    headers={"User-Agent": "InkSlab/1.0"})
        r.raise_for_status()
        data = r.json()
        results = []
        for manga in data.get("data", []):
            attrs = manga.get("attributes", {})
            titles = attrs.get("title", {})
            title = (titles.get("en") or titles.get("ja-ro") or
                     titles.get("ja") or next(iter(titles.values()), "Unknown"))
            results.append({
                "id": manga["id"],
                "title": title,
                "year": str(attrs.get("year", "")) if attrs.get("year") else "",
                "status": attrs.get("status", "").title(),
                "demographic": (attrs.get("publicationDemographic") or "").title(),
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

@app.route('/api/metron/status')
def api_metron_status():
    """Check if Metron credentials are configured."""
    username, password = _read_metron_creds()
    configured = bool(username and password)
    return jsonify({'configured': configured, 'username': username if configured else ''})

@app.route('/api/metron/save', methods=['POST'])
@protected
def api_metron_save():
    """Save Metron credentials to file. Never stored in config or logs."""
    data = request.get_json(force=True) if request.data else {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'ok': False, 'error': 'Username and password required'})
    try:
        creds_file = '/home/pi/.metron_credentials'
        encrypted = _encrypt_creds(username, password)
        with open(creds_file, 'w') as f:
            if encrypted:
                f.write(f'METRON_ENC={encrypted}\n')
            else:
                f.write(f'METRON_USERNAME={username}\n')
                f.write(f'METRON_PASSWORD={password}\n')
        os.chmod(creds_file, 0o600)
        return jsonify({'ok': True, 'username': username})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/metron/clear', methods=['POST'])
@protected
def api_metron_clear():
    """Remove Metron credentials."""
    creds_file = '/home/pi/.metron_credentials'
    try:
        if os.path.exists(creds_file):
            os.remove(creds_file)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/metron/test', methods=['POST'])
@protected
def api_metron_test():
    """Test Metron credentials by making a lightweight API call."""
    data = request.get_json(force=True) if request.data else {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    # Fall back to stored creds if none provided
    if not username or not password:
        username, password = _read_metron_creds()
    if not username or not password:
        return jsonify({'ok': False, 'error': 'No credentials to test'})
    try:
        import requests as req
        headers = {'User-Agent': 'InkSlab/1.0', 'Accept': 'application/json'}
        r = req.get('https://metron.cloud/api/', timeout=10, headers=headers, auth=(username, password))
        if r.status_code == 200:
            return jsonify({'ok': True})
        elif r.status_code == 401:
            return jsonify({'ok': False, 'error': 'Invalid username or password'})
        else:
            return jsonify({'ok': False, 'error': f'Metron returned {r.status_code}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/mtg/sets')
def api_mtg_sets():
    """Fetch available MTG sets from Scryfall for the set-search UI."""
    q = request.args.get('q', '').strip().lower()
    try:
        import requests as req
        INCLUDE_SET_TYPES = {
            "core", "expansion", "masters", "draft_innovation",
            "commander", "starter", "duel_deck", "planechase",
        }
        r = req.get("https://api.scryfall.com/sets", timeout=15,
                    headers={"User-Agent": "InkSlab/1.0"})
        r.raise_for_status()
        all_sets = r.json().get("data", [])
        import time
        today = time.strftime("%Y-%m-%d")
        results = []
        for s in all_sets:
            if s.get("set_type", "") not in INCLUDE_SET_TYPES:
                continue
            if s.get("released_at", "9999") > today:
                continue
            name = s.get("name", "")
            code = s.get("code", "")
            if q and q not in name.lower() and q not in code.lower():
                continue
            results.append({
                "code": code,
                "name": name,
                "released": s.get("released_at", ""),
                "card_count": s.get("card_count", 0),
            })
        results.sort(key=lambda x: x["released"], reverse=True)
        return jsonify({"results": results[:50]})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

@app.route('/api/lorcana/sets')
def api_lorcana_sets():
    """Fetch Lorcana sets from the Lorcast API."""
    try:
        import requests as req
        r = req.get("https://api.lorcast.com/v0/sets", timeout=15,
                    headers={"User-Agent": "InkSlab/1.0"})
        r.raise_for_status()
        data = r.json()
        sets = data if isinstance(data, list) else data.get("results", data.get("data", []))
        results = []
        for s in sets:
            results.append({
                "code": s.get("code", s.get("id", "")),
                "name": s.get("name", ""),
                "released": s.get("released_at", s.get("released", "")),
                "card_count": s.get("card_count", s.get("total_cards", 0)),
            })
        results.sort(key=lambda x: x["released"], reverse=True)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

@app.route('/api/comics/search')
def api_comics_search():
    """Search Metron for comic series."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
    try:
        import requests as req
        username, password = _read_metron_creds()
        if not username or not password:
            return jsonify({"results": [], "error": "Metron credentials not configured"})
        auth = (username, password)
        headers = {'User-Agent': 'InkSlab/1.0 (https://github.com/costamesatechsolutions/inkslab-eink-tcg-display)', 'Accept': 'application/json'}
        r = req.get('https://metron.cloud/api/series/', params={'name': query, 'page_size': 10}, timeout=10, headers=headers, auth=auth)
        r.raise_for_status()
        data = r.json()
        results = []
        for series in data.get('results', []):
            results.append({
                'id': series['id'],
                'title': series.get('series', series.get('name', 'Unknown')),
                'year': str(series.get('year_began', '')) if series.get('year_began') else '',
                'publisher': '',
                'issue_count': series.get('issue_count', '?'),
                'status': '',
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

@app.route('/api/download/status')
def api_download_status():
    global _download_proc, _download_tcg

    running = False
    tcg = _download_tcg
    with _download_lock:
        if _download_proc and _download_proc.poll() is None:
            running = True
        elif _download_proc:
            # Process finished — append completion timestamp, close log, clean up
            try:
                with open(DOWNLOAD_LOG, 'a') as _f:
                    _f.write('\nDownload completed on ' + time.strftime('%B %-d, %Y at %-I:%M') + time.strftime('%p').lower() + '\n')
            except Exception:
                pass
            _close_download_log()
            _download_proc = None
            _download_tcg = None
            tcg = None
            _cache_invalidate('storage')
            _trigger_storage_recompute()
        else:
            tcg = None

    lines = []
    if os.path.exists(DOWNLOAD_LOG):
        try:
            with open(DOWNLOAD_LOG, 'rb') as f:
                f.seek(0, 2)
                size = f.tell()
                chunk = min(size, 8192)
                f.seek(size - chunk)
                tail = f.read().decode('utf-8', errors='replace')
                lines = [l.rstrip() for l in tail.splitlines()[-30:]]
        except Exception:
            pass

    return jsonify({"running": running, "tcg": tcg, "lines": lines})


_storage_computing = False
_storage_lock = threading.Lock()


def _trigger_storage_recompute():
    """Start a background storage recompute if one isn't already running."""
    global _storage_computing
    with _storage_lock:
        if _storage_computing:
            return
        _storage_computing = True
    def _run():
        global _storage_computing
        try:
            result = _compute_storage()
            _cache_set('storage', result)
        finally:
            with _storage_lock:
                _storage_computing = False
    threading.Thread(target=_run, daemon=True).start()


def _compute_storage():
    """Compute storage info. Uses native du for size (much faster than Python stat)."""
    info = {}
    for tcg, path in TCG_LIBRARIES.items():
        if os.path.exists(path):
            # Use du -sb for fast size calculation (native C, avoids 50k+ Python stat calls)
            total_size = 0
            try:
                result = subprocess.run(['du', '-sb', path],
                                        capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and result.stdout.strip():
                    total_size = int(result.stdout.split()[0])
            except Exception:
                pass

            # Count cards and sets with listdir (no stat on each file)
            card_count = 0
            set_count = 0
            try:
                for d in os.listdir(path):
                    set_path = os.path.join(path, d)
                    if os.path.isdir(set_path):
                        set_count += 1
                        for f in os.listdir(set_path):
                            if _is_card_image(f):
                                card_count += 1
            except Exception:
                pass

            info[tcg] = {
                "path": path,
                "size_mb": round(total_size / (1024 * 1024)),
                "size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "card_count": card_count,
                "set_count": set_count,
            }
        else:
            info[tcg] = {"path": path, "size_mb": 0, "size_gb": 0.0,
                         "card_count": 0, "set_count": 0}
    # Image thumbnail cache size + count
    thumb_size = 0
    thumb_count = 0
    if os.path.exists(THUMB_CACHE_DIR):
        try:
            result = subprocess.run(['du', '-sb', THUMB_CACHE_DIR],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                thumb_size = int(result.stdout.split()[0])
        except Exception:
            pass
        try:
            for root, dirs, files in os.walk(THUMB_CACHE_DIR):
                thumb_count += sum(1 for f in files if f.endswith('.jpg'))
        except Exception:
            pass
    total_cards = sum(v.get('card_count', 0) for v in info.values())
    info['_thumbcache'] = {
        'size_mb': round(thumb_size / (1024 * 1024), 2),
        'cached': thumb_count,
        'total': total_cards,
    }

    try:
        usage = shutil.disk_usage('/home/pi')
        info['_disk'] = {
            'free_gb': round(usage.free / (1024 * 1024 * 1024), 2),
            'total_gb': round(usage.total / (1024 * 1024 * 1024), 2),
        }
    except Exception:
        pass
    return info


@app.route('/api/storage')
def api_storage():
    cached = _cache_get('storage', ttl=300)
    if cached:
        return jsonify(cached)
    stale = _cache_get('storage', ttl=float('inf'))
    _trigger_storage_recompute()
    if stale:
        return jsonify(stale)
    return jsonify({"_computing": True})


@app.route('/api/delete', methods=['POST'])
@protected
def api_delete():
    data = request.get_json(force=True)
    tcg = data.get("tcg")
    if not tcg or tcg not in TCG_LIBRARIES:
        return jsonify({"ok": False, "error": "Invalid TCG"}), 400

    path = TCG_LIBRARIES[tcg]
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            _cache_invalidate('storage', 'rarities_' + tcg, 'sets_' + tcg)
            return jsonify({"ok": True, "tcg": tcg})
        except Exception as e:
            app.logger.error(f"Delete failed for {tcg}: {e}")
            return jsonify({"ok": False, "error": "Delete failed. Try again or reboot."})
    return jsonify({"ok": True, "tcg": tcg})


# --- OTA UPDATE ---
UPDATE_STATUS_FILE = "/tmp/inkslab_update_status.json"

# Fix "dubious ownership" — web service runs as root but repo is owned by pi
subprocess.run(['git', 'config', '--global', 'safe.directory', SCRIPT_DIR],
               capture_output=True, timeout=5)


def _git_default_branch():
    """Detect the remote default branch (main or master)."""
    try:
        r = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'],
                           cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip().split('/')[-1]
    except Exception:
        pass
    # Fallback: check which branch exists
    for branch in ('main', 'master'):
        r = subprocess.run(['git', 'rev-parse', '--verify', f'origin/{branch}'],
                           cwd=SCRIPT_DIR, capture_output=True, timeout=5)
        if r.returncode == 0:
            return branch
    return 'main'


@app.route('/api/version')
def api_version():
    """Return the current version (hardcoded + git hash if available)."""
    git_hash = ""
    try:
        local = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=SCRIPT_DIR,
                               capture_output=True, text=True, timeout=5)
        if local.returncode == 0:
            git_hash = local.stdout.strip()[:8]
    except Exception:
        pass
    version = f"{VERSION}-{git_hash}" if git_hash else VERSION
    return jsonify({"version": version})


@app.route('/api/update/check', methods=['POST'])
@protected
def api_update_check():
    """Check if updates are available by comparing local vs remote HEAD."""
    try:
        # Fetch first so branch detection can see remote refs
        fetch = subprocess.run(['git', 'fetch', 'origin'], cwd=SCRIPT_DIR,
                               capture_output=True, text=True, timeout=30)
        if fetch.returncode != 0:
            return jsonify({"ok": False, "error": "Could not reach update server. Check your internet connection."})
        branch = _git_default_branch()
        local = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=SCRIPT_DIR,
                               capture_output=True, text=True, timeout=5)
        remote = subprocess.run(['git', 'rev-parse', f'origin/{branch}'], cwd=SCRIPT_DIR,
                                capture_output=True, text=True, timeout=5)
        local_hash = local.stdout.strip()[:8] if local.returncode == 0 else ""
        remote_hash = remote.stdout.strip()[:8] if remote.returncode == 0 else ""
        behind = subprocess.run(['git', 'rev-list', '--count', f'HEAD..origin/{branch}'],
                                cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=5)
        commits_behind = int(behind.stdout.strip()) if behind.returncode == 0 else 0
        # Build display version: "1.0.0-abc123" or just "1.0.0"
        local_version = f"{VERSION}-{local_hash}" if local_hash else VERSION
        return jsonify({"ok": True, "local": local_version, "remote": remote_hash,
                        "behind": commits_behind, "up_to_date": commits_behind == 0})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/api/update/start', methods=['POST'])
@protected
def api_update_start():
    """Launch OTA update script detached from this process."""
    lock_file = "/tmp/inkslab_update.lock"
    if os.path.exists(lock_file):
        try:
            with open(lock_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # Check if process is alive
            return jsonify({"ok": False, "error": "Update already in progress"})
        except (ValueError, OSError):
            pass  # Stale lock, allow proceeding
    script = os.path.join(SCRIPT_DIR, "scripts", "ota_update.sh")
    if not os.path.exists(script):
        return jsonify({"ok": False, "error": "Update script not found"})
    try:
        # Clear old status
        if os.path.exists(UPDATE_STATUS_FILE):
            os.remove(UPDATE_STATUS_FILE)
        subprocess.Popen(['bash', script], cwd=SCRIPT_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/api/update/status')
def api_update_status():
    """Read OTA update progress."""
    if os.path.exists(UPDATE_STATUS_FILE):
        try:
            with open(UPDATE_STATUS_FILE, 'r') as f:
                status = json.load(f)
            # Auto-clear stale status
            if time.time() - status.get('timestamp', 0) > 120:
                return jsonify({"stage": "idle"})
            return jsonify(status)
        except Exception:
            pass
    return jsonify({"stage": "idle"})


# --- WIFI SETUP ---

def _perform_wifi_connection(ssid, password):
    """Background thread: tear down hotspot, connect, handle failure."""
    global _wifi_setup_mode, _wifi_connect_result

    try:
        # Step 1: Tear down hotspot and wait for wlan0 to switch from AP to station mode
        wifi_manager.stop_hotspot()
        time.sleep(5)  # Pi Zero needs time for interface mode switch

        # Step 2: Attempt connection
        success, message = wifi_manager.connect_to_network(ssid, password)

        if success:
            with _wifi_connect_lock:
                _wifi_connect_result = {
                    "status": "success", "ip": message,
                    "ssid": ssid, "error": None,
                }
            _wifi_setup_mode = False
            # Signal inkslab.py to refresh splash screen
            try:
                with open("/tmp/inkslab_wifi_connected", "w") as f:
                    f.write(message)
            except OSError:
                pass
        else:
            # Connection failed — restore hotspot and signal e-ink display
            with _wifi_connect_lock:
                _wifi_connect_result = {
                    "status": "failed", "error": message, "ssid": ssid,
                }
            try:
                with open("/tmp/inkslab_wifi_failed", "w") as f:
                    f.write(message or "Connection failed")
            except OSError:
                pass
            wifi_manager.start_hotspot()
            _wifi_setup_mode = True
    except Exception as e:
        with _wifi_connect_lock:
            _wifi_connect_result = {
                "status": "failed", "error": str(e), "ssid": ssid,
            }
        try:
            with open("/tmp/inkslab_wifi_failed", "w") as f:
                f.write(str(e))
        except OSError:
            pass
        try:
            wifi_manager.start_hotspot()
            _wifi_setup_mode = True
        except Exception:
            pass


@app.route('/api/wifi/status')
def api_wifi_status():
    """Return current WiFi state and setup mode flag."""
    status = wifi_manager.get_wifi_status()
    status["setup_mode"] = _wifi_setup_mode
    with _wifi_connect_lock:
        status["connect_status"] = dict(_wifi_connect_result)
    return jsonify(status)


@app.route('/api/wifi/scan')
def api_wifi_scan():
    """Scan for available networks."""
    networks = wifi_manager.scan_networks()
    return jsonify(networks)


@app.route('/api/wifi/connect', methods=['POST'])
def api_wifi_connect():
    """Begin connection to a WiFi network (non-blocking)."""
    global _wifi_connect_result
    data = request.get_json(force=True)
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "").strip()

    if not ssid:
        return jsonify({"ok": False, "error": "SSID required"}), 400

    with _wifi_connect_lock:
        if _wifi_connect_result.get("status") == "connecting":
            return jsonify({"ok": False, "error": "Connection already in progress"}), 409
        _wifi_connect_result = {"status": "connecting", "ssid": ssid, "error": None}

    t = threading.Thread(target=_perform_wifi_connection, args=(ssid, password), daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Connecting..."})


@app.route('/api/wifi/retry', methods=['POST'])
def api_wifi_retry():
    """Attempt to reconnect to the last known WiFi network (no auth required — needed during setup)."""
    global _wifi_connect_result
    with _wifi_connect_lock:
        if _wifi_connect_result.get('status') == 'connecting':
            return jsonify({'ok': False, 'error': 'Connection already in progress'}), 409
        _wifi_connect_result = {'status': 'connecting', 'ssid': None, 'error': None}

    def _do_retry():
        global _wifi_setup_mode, _wifi_connect_result
        try:
            wifi_manager.stop_hotspot()
            time.sleep(3)
            r1 = subprocess.run(
                ['nmcli', '-t', '-e', 'yes', '-f', 'TYPE,NAME', 'con', 'show'],
                capture_output=True, text=True, timeout=10
            )
            profiles = [line.split(':')[1] for line in r1.stdout.strip().splitlines()
                        if line.startswith('802-11-wireless:') and 'Hotspot' not in line and 'InkSlab' not in line]
            if not profiles:
                raise Exception('No saved WiFi profiles found')
            profile = profiles[0]
            r2 = subprocess.run(['nmcli', 'con', 'up', 'id', profile],
                                 capture_output=True, text=True, timeout=30)
            if r2.returncode == 0:
                ip = wifi_manager.get_local_ip() or ''
                with _wifi_connect_lock:
                    _wifi_connect_result = {'status': 'success', 'ssid': profile, 'ip': ip, 'error': None}
                _wifi_setup_mode = False
            else:
                raise Exception(r2.stderr.strip() or 'Connection failed')
        except Exception as e:
            with _wifi_connect_lock:
                _wifi_connect_result = {'status': 'failed', 'ssid': None, 'error': str(e)}
            try:
                wifi_manager.start_hotspot()
                _wifi_setup_mode = True
            except Exception:
                pass

    t = threading.Thread(target=_do_retry, daemon=True)
    t.start()
    return jsonify({'ok': True, 'message': 'Retrying...'})


@app.route('/api/wifi/disconnect', methods=['POST'])
@protected
def api_wifi_disconnect():
    """Disconnect WiFi, forget the saved profile, and re-enter setup mode."""
    global _wifi_setup_mode, _wifi_connect_result
    try:
        wifi_manager.stop_hotspot()
        # Disconnect AND delete (forget) the WiFi profile
        ssid = wifi_manager.get_active_ssid()
        if ssid:
            subprocess.run(["nmcli", "con", "down", "id", ssid],
                           capture_output=True, timeout=10)
            subprocess.run(["nmcli", "con", "delete", "id", ssid],
                           capture_output=True, timeout=10)
        with _wifi_connect_lock:
            _wifi_connect_result = {"status": "idle"}
        _wifi_setup_mode = True
        wifi_manager.start_hotspot()
        # Signal display daemon to show setup screen
        try:
            with open("/tmp/inkslab_wifi_setup", "w") as f:
                f.write("1")
        except OSError:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/factory_reset', methods=['POST'])
@protected
def api_factory_reset():
    """Prepare unit for shipping: forget WiFi, delete card data, reset config."""
    global _wifi_setup_mode, _wifi_connect_result
    errors = []

    # 1. Forget all saved WiFi profiles (except hotspot)
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-e", "yes", "-f", "TYPE,NAME", "con", "show"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().splitlines():
            parts = wifi_manager._split_nmcli_escaped(line)
            if len(parts) >= 2 and "wireless" in parts[0] and parts[1] != "InkSlab-Setup":
                subprocess.run(["nmcli", "con", "down", "id", parts[1]],
                               capture_output=True, timeout=10)
                subprocess.run(["nmcli", "con", "delete", "id", parts[1]],
                               capture_output=True, timeout=10)
    except Exception as e:
        errors.append(f"WiFi cleanup: {e}")

    # 2. Delete card data (except kept libraries)
    req_data = request.get_json(force=True) if request.data else {}
    keep_cards = req_data.get("keep_cards", [])
    for tcg_key, tcg_info in TCG_REGISTRY.items():
        if tcg_key in keep_cards:
            continue
        card_path = tcg_info["path"]
        if os.path.isdir(card_path):
            try:
                shutil.rmtree(card_path)
            except Exception as e:
                errors.append(f"Delete {tcg_key}: {e}")
    # 2b. Delete Metron credentials
    for creds_f in ["/home/pi/.metron_credentials", LAST_UPDATE_FILE]:
        if os.path.exists(creds_f):
            try:
                os.remove(creds_f)
            except Exception as e:
                errors.append(f"Delete {creds_f}: {e}")
    # 3. Reset config and collection to defaults
    for f in [CONFIG_FILE, COLLECTION_FILE]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            errors.append(f"Reset {f}: {e}")

    # 4. Enter setup mode
    with _wifi_connect_lock:
        _wifi_connect_result = {"status": "idle"}
    _wifi_setup_mode = True
    try:
        wifi_manager.start_hotspot()
    except Exception as e:
        errors.append(f"Hotspot: {e}")

    # 5. Clean up temp files, logs, and user traces
    _close_download_log()
    for tmp_file in [STATUS_FILE, DOWNLOAD_LOG, NEXT_TRIGGER, COLLECTION_TRIGGER, REDRAW_TRIGGER,
                     "/tmp/inkslab_prev", "/tmp/inkslab_pause",
                     "/tmp/inkslab_wifi_connected", "/tmp/inkslab_update_status.json",
                     "/tmp/inkslab_update.lock"]:
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except OSError:
            pass
    # Purge journal logs (contain SSIDs, IPs)
    try:
        subprocess.run(["journalctl", "--rotate"], capture_output=True, timeout=10)
        subprocess.run(["journalctl", "--vacuum-time=1s"], capture_output=True, timeout=10)
    except Exception:
        pass
    # Clear bash history
    for hist in ["/home/pi/.bash_history", "/root/.bash_history"]:
        try:
            if os.path.exists(hist):
                with open(hist, 'w') as _:
                    pass
        except OSError:
            pass

    # 6. Signal display daemon to show unbox/shipping screen
    # The "Plug me in!" screen stays on the e-ink after power off — perfect for shipping.
    # When the customer plugs it in, it boots without WiFi and shows the setup screen automatically.
    try:
        with open("/tmp/inkslab_unbox", "w") as f:
            f.write("1")
    except OSError:
        pass

    # 7. Invalidate all caches
    _cache_invalidate("storage", "card_counts")

    if errors:
        return jsonify({"ok": True, "warnings": errors})
    return jsonify({"ok": True})



# Captive portal detection endpoints — redirect to setup page
@app.route('/hotspot-detect.html')
@app.route('/generate_204')
@app.route('/ncsi.txt')
@app.route('/connecttest.txt')
@app.route('/redirect')
@app.route('/canonical.html')
def captive_portal_detect():
    if _wifi_setup_mode:
        return redirect("http://10.42.0.1/", code=302)
    return "Success", 200


# --- CUSTOM IMAGE MANAGEMENT ---

CUSTOM_PATH = TCG_LIBRARIES["custom"]

@app.route('/api/custom/folders')
def api_custom_folders():
    """List custom image folders with card counts."""
    if not os.path.exists(CUSTOM_PATH):
        return jsonify([])
    folders = []
    master = {}
    idx_path = os.path.join(CUSTOM_PATH, "master_index.json")
    if os.path.exists(idx_path):
        try:
            with open(idx_path, 'r') as f:
                master = json.load(f)
        except Exception:
            pass
    for d in sorted(os.listdir(CUSTOM_PATH)):
        dp = os.path.join(CUSTOM_PATH, d)
        if not os.path.isdir(dp):
            continue
        count = sum(1 for f in os.listdir(dp) if _is_card_image(f))
        info = master.get(d, {})
        folders.append({"id": d, "name": info.get("name", d.replace('_', ' ').replace('-', ' ').title()),
                        "card_count": count})
    return jsonify(folders)


@app.route('/api/custom/create_folder', methods=['POST'])
@protected
def api_custom_create_folder():
    """Create a new custom image folder."""
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    # Sanitize folder name
    safe = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in name).strip()
    safe = safe.replace(' ', '_').lower()
    if not safe:
        return jsonify({"error": "invalid name"}), 400
    folder = os.path.join(CUSTOM_PATH, safe)
    os.makedirs(folder, exist_ok=True)
    # Update master_index
    with _custom_lock:
        idx_path = os.path.join(CUSTOM_PATH, "master_index.json")
        master = {}
        if os.path.exists(idx_path):
            try:
                with open(idx_path, 'r') as f:
                    master = json.load(f)
            except Exception:
                pass
        master[safe] = {"name": name, "year": ""}
        _atomic_write_json(idx_path, master)
    _cache_invalidate('sets_custom', 'storage')
    return jsonify({"ok": True, "id": safe, "name": name})


@app.route('/api/custom/rename_folder', methods=['POST'])
@protected
def api_custom_rename_folder():
    """Rename a custom set's display name."""
    data = request.get_json(force=True)
    folder_id = os.path.basename(data.get("id", ""))
    new_name = data.get("name", "").strip()
    if not folder_id or not new_name:
        return jsonify({"error": "id and name required"}), 400
    with _custom_lock:
        idx_path = os.path.join(CUSTOM_PATH, "master_index.json")
        master = {}
        if os.path.exists(idx_path):
            try:
                with open(idx_path, 'r') as f:
                    master = json.load(f)
            except Exception:
                pass
        if folder_id not in master:
            master[folder_id] = {"name": new_name, "year": ""}
        else:
            master[folder_id]["name"] = new_name
        _atomic_write_json(idx_path, master)
    _cache_invalidate('sets_custom')
    return jsonify({"ok": True})


@app.route('/api/custom/folder/<name>', methods=['DELETE'])
@protected
def api_custom_delete_folder(name):
    """Delete an entire custom folder."""
    safe = os.path.basename(name)
    folder = os.path.join(CUSTOM_PATH, safe)
    with _custom_lock:
        # Update index FIRST so daemon won't try to read deleted folder
        idx_path = os.path.join(CUSTOM_PATH, "master_index.json")
        if os.path.exists(idx_path):
            try:
                with open(idx_path, 'r') as f:
                    master = json.load(f)
                master.pop(safe, None)
                _atomic_write_json(idx_path, master)
            except Exception:
                pass
        if os.path.isdir(folder):
            shutil.rmtree(folder)
    _cache_invalidate('sets_custom', 'storage')
    return jsonify({"ok": True})


@app.route('/api/custom/card/<folder>/<card_id>', methods=['DELETE'])
@protected
def api_custom_delete_card(folder, card_id):
    """Delete a single card from a custom folder."""
    safe_folder = os.path.basename(folder)
    safe_card = os.path.basename(card_id)
    folder_path = os.path.join(CUSTOM_PATH, safe_folder)
    with _custom_lock:
        # Update metadata first
        data_file = os.path.join(folder_path, "_data.json")
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r') as f:
                    data = json.load(f)
                data.pop(safe_card, None)
                _atomic_write_json(data_file, data)
            except Exception:
                pass
        # Then remove image files
        for ext in IMAGE_EXTENSIONS:
            p = os.path.join(folder_path, safe_card + ext)
            if os.path.exists(p):
                os.remove(p)
    _cache_invalidate('sets_custom', 'storage')
    return jsonify({"ok": True})


@app.route('/api/custom/upload', methods=['POST'])
@protected
def api_custom_upload():
    """Upload an image to a custom folder."""
    folder_id = request.form.get("folder", "")
    if not folder_id:
        return jsonify({"error": "folder required"}), 400
    safe_folder = os.path.basename(folder_id)
    folder_path = os.path.join(CUSTOM_PATH, safe_folder)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "folder not found"}), 404
    if not _has_disk_space():
        return jsonify({"error": "Not enough storage space. Delete some cards first."}), 507
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "file required"}), 400
    # Validate extension
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return jsonify({"error": "Only PNG/JPG images allowed"}), 400
    # Sanitize filename
    base = os.path.splitext(f.filename)[0]
    safe_base = "".join(c if c.isalnum() or c in ('-', '_', ' ') else '' for c in base).strip()
    if not safe_base:
        safe_base = f"card_{int(time.time())}"
    safe_name = safe_base.replace(' ', '_') + ext
    filepath = os.path.join(folder_path, safe_name)
    # Avoid overwrite
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(folder_path, f"{safe_base}_{counter}{ext}")
        counter += 1
    # Save to temp file first, then rename (atomic)
    tmp_path = filepath + '.tmp'
    try:
        f.save(tmp_path)
        os.rename(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return jsonify({"error": "Upload failed. Try again."}), 500
    card_id = os.path.splitext(os.path.basename(filepath))[0]
    # Auto-add metadata (locked + atomic)
    with _custom_lock:
        data_file = os.path.join(folder_path, "_data.json")
        data = {}
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r') as df:
                    data = json.load(df)
            except Exception:
                pass
        data[card_id] = {
            "name": safe_base.replace('_', ' ').replace('-', ' ').title(),
            "number": str(len(data) + 1),
            "rarity": "",
        }
        _atomic_write_json(data_file, data)
    _cache_invalidate('sets_custom', 'storage')
    return jsonify({"ok": True, "card_id": card_id})


@app.route('/api/custom/card_metadata', methods=['POST'])
@protected
def api_custom_card_metadata():
    """Edit a card's metadata (name, number, rarity)."""
    data = request.get_json(force=True)
    folder_id = data.get("folder", "")
    card_id = data.get("card_id", "")
    if not folder_id or not card_id:
        return jsonify({"error": "folder and card_id required"}), 400
    safe_folder = os.path.basename(folder_id)
    folder_path = os.path.join(CUSTOM_PATH, safe_folder)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "folder not found"}), 404
    data_file = os.path.join(folder_path, "_data.json")
    cards = {}
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r') as f:
                cards = json.load(f)
        except Exception:
            pass
    with _custom_lock:
        if card_id not in cards:
            cards[card_id] = {}
        if "name" in data:
            cards[card_id]["name"] = data["name"]
        if "number" in data:
            cards[card_id]["number"] = data["number"]
        if "rarity" in data:
            cards[card_id]["rarity"] = data["rarity"]
        _atomic_write_json(data_file, cards)
    return jsonify({"ok": True})


@app.route('/api/custom/set_metadata', methods=['POST'])
@protected
def api_custom_set_metadata():
    """Edit a set's display name and year."""
    data = request.get_json(force=True)
    folder_id = data.get("id", "")
    if not folder_id:
        return jsonify({"error": "id required"}), 400
    idx_path = os.path.join(CUSTOM_PATH, "master_index.json")
    master = {}
    if os.path.exists(idx_path):
        try:
            with open(idx_path, 'r') as f:
                master = json.load(f)
        except Exception:
            pass
    with _custom_lock:
        if folder_id not in master:
            master[folder_id] = {"name": folder_id, "year": ""}
        if "name" in data:
            master[folder_id]["name"] = data["name"]
        if "year" in data:
            master[folder_id]["year"] = data["year"]
        _atomic_write_json(idx_path, master)
    _cache_invalidate('sets_custom')
    return jsonify({"ok": True})


# --- DASHBOARD HTML ---

WIFI_SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
  <meta name="apple-mobile-web-app-title" content="InkSlab">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>InkSlab WiFi Setup</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #132E3E; color: #D8E6E4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-height: 100vh; display: flex; flex-direction: column; }
.header { background: #0d2230; padding: 16px; text-align: center; border-bottom: 1px solid #1F333F; }
.header h1 { font-size: 20px; color: #FCFDF0; font-weight: 700; }
.header p { font-size: 12px; color: #6BCCBD; margin-top: 4px; }
.content { flex: 1; padding: 16px; max-width: 480px; margin: 0 auto; width: 100%; }
.card { background: #1a3a4a; border-radius: 10px; padding: 16px; margin-bottom: 16px; border: 1px solid #1F333F; }
.welcome { text-align: center; padding: 20px 0; }
.welcome h2 { color: #FCFDF0; font-size: 22px; margin-bottom: 8px; }
.welcome p { color: #6BCCBD; font-size: 14px; }
.section-title { font-size: 14px; font-weight: 600; color: #6BCCBD; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
.btn { display: inline-block; padding: 10px 16px; border-radius: 6px; border: none; font-size: 14px; font-weight: 600; cursor: pointer; text-align: center; transition: opacity 0.2s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #36A5CA; color: #010001; width: 100%; }
.btn-secondary { background: #1F333F; color: #D8E6E4; border: 1px solid #36A5CA44; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.network-list { max-height: 45vh; overflow-y: auto; border-radius: 8px; }
.network-item { display: flex; align-items: center; justify-content: space-between; padding: 12px; background: #132E3E; border-bottom: 1px solid #1F333F; cursor: pointer; transition: background 0.15s; }
.network-item:hover, .network-item:active { background: #1F333F; }
.network-item:first-child { border-radius: 8px 8px 0 0; }
.network-item:last-child { border-radius: 0 0 8px 8px; border-bottom: none; }
.network-ssid { font-size: 15px; color: #FCFDF0; font-weight: 500; flex: 1; }
.network-meta { display: flex; align-items: center; gap: 8px; }
.signal-bars { display: flex; gap: 2px; align-items: flex-end; height: 16px; }
.signal-bar { width: 4px; background: #6BCCBD; border-radius: 1px; }
.signal-bar.off { background: #1F333F; }
.lock { font-size: 12px; color: #6BCCBD; }
.connect-form { display: none; margin-top: 12px; }
.connect-form.open { display: block; }
.connect-form h3 { font-size: 15px; color: #FCFDF0; margin-bottom: 10px; }
.input-wrap { position: relative; margin-bottom: 12px; }
.input-wrap input { width: 100%; padding: 12px 44px 12px 12px; background: #132E3E; color: #FCFDF0; border: 1px solid #36A5CA44; border-radius: 6px; font-size: 15px; outline: none; }
.input-wrap input:focus { border-color: #36A5CA; }
.toggle-pw { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #6BCCBD; font-size: 12px; cursor: pointer; padding: 4px 8px; }
.status-area { text-align: center; padding: 16px 0; }
.spinner { display: inline-block; width: 28px; height: 28px; border: 3px solid #1F333F; border-top-color: #36A5CA; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }
.success-screen { text-align: center; padding: 32px 16px; }
.success-screen .check { font-size: 56px; color: #6BCCBD; margin-bottom: 12px; }
.success-screen h2 { color: #6BCCBD; margin-bottom: 10px; }
.success-screen .ip { font-size: 20px; font-weight: 700; color: #FCFDF0; margin: 16px 0; }
.success-screen p { color: #6BCCBD; font-size: 13px; }
.error-msg { color: #ff6b6b; font-size: 13px; text-align: center; padding: 8px; }
.footer { background: #0d2230; padding: 14px 16px; text-align: center; font-size: 10px; color: #1F333F55; border-top: 1px solid #1F333F; margin-top: auto; }
</style>
</head>
<body>
<div class="header">
  <h1>InkSlab</h1>
  <p>WiFi Setup</p>
</div>

<div class="content" id="setup-content">
  <div class="welcome">
    <h2>Welcome!</h2>
    <p>Let's connect your InkSlab to WiFi.</p>
  </div>

  <div class="card">
    <div class="section-title">
      <span>Available Networks</span>
      <button class="btn btn-secondary btn-sm" onclick="scanNetworks()">Scan</button>
    </div>
    <div class="network-list" id="network-list">
      <div style="text-align:center;padding:24px;color:#6BCCBD">Scanning...</div>
    </div>
  </div>

  <div class="card connect-form" id="connect-form">
    <h3>Connect to <span id="selected-ssid"></span></h3>
    <div id="password-section">
      <div class="input-wrap">
        <input type="password" id="wifi-password" placeholder="Enter WiFi password" autocomplete="off" autocapitalize="off">
        <button class="toggle-pw" onclick="togglePw()">show</button>
      </div>
    </div>
    <button class="btn btn-primary" id="btn-connect" onclick="doConnect()">Connect</button>
    <div style="text-align:center;margin-top:8px">
      <button class="btn btn-secondary btn-sm" onclick="cancelConnect()">Cancel</button>
    </div>
    <div id="status-area" class="status-area"></div>
  </div>
</div>

<div class="footer">Costa Mesa Tech Solutions</div>

<script>
var selectedSSID = '';
var selectedSecurity = '';
var _statusPoll = null;

function scanNetworks() {
  var el = document.getElementById('network-list');
  el.innerHTML = '<div style="text-align:center;padding:24px;color:#6BCCBD"><div class="spinner"></div><br>Scanning...</div>';
  fetch('/api/wifi/scan').then(function(r) { return r.json(); }).then(function(networks) {
    if (!networks.length) {
      el.innerHTML = '<div style="text-align:center;padding:24px;color:#6BCCBD">No networks found. Tap Scan to try again.</div>';
      return;
    }
    el.innerHTML = networks.map(function(n) {
      var bars = signalBars(n.signal);
      var lock = n.security ? '<span class="lock">&#128274;</span>' : '';
      var safe = n.ssid.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
      return '<div class="network-item" onclick="selectNetwork(&#39;' + safe + '&#39;,&#39;' + (n.security || '').replace(/'/g, "&#39;") + '&#39;)">'
        + '<span class="network-ssid">' + safe + '</span>'
        + '<span class="network-meta">' + bars + lock + '</span>'
        + '</div>';
    }).join('');
  }).catch(function() {
    el.innerHTML = '<div style="text-align:center;padding:24px;color:#ff6b6b">Scan failed. Tap Scan to retry.</div>';
  });
}

function signalBars(signal) {
  var bars = '';
  var heights = [4, 7, 10, 13, 16];
  for (var i = 0; i < 5; i++) {
    var on = signal >= (i + 1) * 20;
    bars += '<span class="signal-bar' + (on ? '' : ' off') + '" style="height:' + heights[i] + 'px"></span>';
  }
  return '<span class="signal-bars">' + bars + '</span>';
}

function selectNetwork(ssid, security) {
  selectedSSID = ssid;
  selectedSecurity = security;
  document.getElementById('selected-ssid').textContent = ssid;
  document.getElementById('connect-form').classList.add('open');
  document.getElementById('status-area').innerHTML = '';
  document.getElementById('btn-connect').disabled = false;
  var pwSection = document.getElementById('password-section');
  if (security) {
    pwSection.style.display = 'block';
    document.getElementById('wifi-password').value = '';
    document.getElementById('wifi-password').focus();
  } else {
    pwSection.style.display = 'none';
  }
}

function cancelConnect() {
  document.getElementById('connect-form').classList.remove('open');
  selectedSSID = '';
  if (_statusPoll) { clearInterval(_statusPoll); _statusPoll = null; }
}

function togglePw() {
  var inp = document.getElementById('wifi-password');
  var btn = inp.nextElementSibling;
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
  else { inp.type = 'password'; btn.textContent = 'show'; }
}

function doConnect() {
  var password = document.getElementById('wifi-password').value;
  document.getElementById('btn-connect').disabled = true;
  document.getElementById('status-area').innerHTML = '<div class="spinner"></div><div style="color:#36A5CA">Connecting to ' + selectedSSID + '...</div>';
  fetch('/api/wifi/connect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ssid: selectedSSID, password: password})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (!d.ok) {
      document.getElementById('status-area').innerHTML = '<div class="error-msg">' + esc(d.error || 'Failed') + '</div>';
      document.getElementById('btn-connect').disabled = false;
      return;
    }
    // Start polling for result
    _statusPoll = setInterval(checkConnectStatus, 2000);
  }).catch(function() {
    document.getElementById('status-area').innerHTML = '<div class="error-msg">Request failed</div>';
    document.getElementById('btn-connect').disabled = false;
  });
}

function checkConnectStatus() {
  fetch('/api/wifi/status').then(function(r) { return r.json(); }).then(function(d) {
    var cs = d.connect_status;
    if (cs.status === 'success') {
      clearInterval(_statusPoll); _statusPoll = null;
      showSuccess(cs.ip, cs.ssid);
    } else if (cs.status === 'failed') {
      clearInterval(_statusPoll); _statusPoll = null;
      document.getElementById('status-area').innerHTML = '<div class="error-msg">' + esc(cs.error || 'Connection failed. Check your password.') + '</div>';
      document.getElementById('btn-connect').disabled = false;
    }
  }).catch(function() {
    // Connection might be in progress (hotspot tearing down) — normal, keep polling
  });
}

function showSuccess(ip, ssid) {
  document.getElementById('setup-content').innerHTML =
    '<div class="success-screen">'
    + '<div class="check">&#10004;</div>'
    + '<h2>Connected!</h2>'
    + '<p style="color:#D8E6E4;font-size:15px;margin-bottom:16px">Your InkSlab is now on <strong>' + ssid.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') + '</strong></p>'
    + '<div class="ip">http://' + ip.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>'
    + '<p>Open this address in your web browser (Safari, Chrome, etc.) to access the dashboard.</p>'
    + '<p style="margin-top:20px;color:#36A5CA;font-size:12px">The e-ink display will also show this address.</p>'
    + '</div>';
}

// Auto-scan on load
scanNetworks();
</script>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<meta name="apple-mobile-web-app-title" content="InkSlab">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>InkSlab</title>
<link rel="stylesheet" href="/static/style.css?v=4">
<script>window.CSRF_TOKEN = '__CSRF_TOKEN__';</script>
<script>(function(){var T={'default':{'--bg-card':'#16303E','--bg-panel':'#132E3E','--bg-input':'#1F333F','--border':'#1F333F','--text':'#D8E6E4','--text-dim':'#6BCCBD','--text-hi':'#FCFDF0','--accent':'#36A5CA','--accent2':'#6BCCBD','--border-hi':'#36A5CA44'},'lorcana':{'--bg-card':'#1A0B2E','--bg-panel':'#130823','--bg-input':'#211040','--border':'#2D1554','--text':'#E8D0F8','--text-dim':'#C084FC','--text-hi':'#F5EEFF','--accent':'#C084FC','--accent2':'#A855F7','--border-hi':'#C084FC44'},'pokemon':{'--bg-card':'#0D1E2E','--bg-panel':'#091629','--bg-input':'#122035','--border':'#1A3550','--text':'#C8E8F8','--text-dim':'#36A5CA','--text-hi':'#E8F4FA','--accent':'#36A5CA','--accent2':'#5bbfe0','--border-hi':'#36A5CA44'},'mtg':{'--bg-card':'#0E1E1C','--bg-panel':'#091816','--bg-input':'#132220','--border':'#1C3330','--text':'#C8E8E4','--text-dim':'#6BCCBD','--text-hi':'#E8F8F5','--accent':'#6BCCBD','--accent2':'#4db8a8','--border-hi':'#6BCCBD44'},'manga':{'--bg-card':'#2A0F20','--bg-panel':'#200B18','--bg-input':'#33102A','--border':'#401535','--text':'#F8D0E8','--text-dim':'#F472B6','--text-hi':'#FFF0F8','--accent':'#F472B6','--accent2':'#EC4899','--border-hi':'#F472B644'},'comics':{'--bg-card':'#2A1000','--bg-panel':'#200C00','--bg-input':'#301500','--border':'#3D1800','--text':'#F8DCC0','--text-dim':'#F97316','--text-hi':'#FFF4EC','--accent':'#F97316','--accent2':'#EA580C','--border-hi':'#F9731644'},'custom':{'--bg-card':'#241600','--bg-panel':'#1B1000','--bg-input':'#2E1C00','--border':'#392200','--text':'#F8E8C0','--text-dim':'#F59E0B','--text-hi':'#FFF8E8','--accent':'#F59E0B','--accent2':'#D97706','--border-hi':'#F59E0B44'}};var t=localStorage.getItem('inkslab_theme')||'default';var k=t==='auto'?(localStorage.getItem('inkslab_last_tcg')||'default'):t;var p=T[k]||T['default'];var r=document.documentElement;Object.keys(p).forEach(function(k){r.style.setProperty(k,p[k]);});}());</script>
</head>
<body class="auth-pending">

<!-- AUTH OVERLAY -->
<div id="auth-overlay" style="display:none;position:fixed;inset:0;background:var(--bg);z-index:1000;display:none;align-items:center;justify-content:center;flex-direction:column;">
  <div style="width:100%;max-width:320px;padding:32px 24px;">
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:22px;font-weight:700;color:var(--accent);letter-spacing:1px;margin-bottom:6px;">InkSlab</div>
    </div>

    <!-- SETUP SECTION (first boot) -->
    <div id="auth-setup-section" style="display:none;">
      <h3 style="margin:0 0 8px;color:var(--text-hi);font-size:16px;">Set a PIN</h3>
      <p style="color:var(--text-dim);font-size:12px;margin:0 0 16px;">Optional: protect your dashboard with a 4-8 digit PIN. You can change or remove it in Settings later.</p>
      <input id="setup-pin-input" type="password" inputmode="numeric" pattern="[0-9]*" placeholder="4-8 digits (optional)" maxlength="8"
        style="width:100%;box-sizing:border-box;margin-bottom:10px;padding:12px;border-radius:8px;border:1px solid var(--border-hi);background:var(--bg-input);color:var(--text-hi);font-size:16px;text-align:center;letter-spacing:4px;"
        onkeydown="if(event.key==='Enter')submitSetup(false)">
      <div id="setup-error" style="color:var(--danger);font-size:12px;min-height:16px;margin-bottom:8px;text-align:center;"></div>
      <button class="btn btn-primary btn-block" style="margin-bottom:10px;" onclick="submitSetup(false)">Set PIN &amp; Continue</button>
      <button class="btn btn-block" style="background:transparent;color:var(--text-dim);border:1px solid var(--border);" onclick="submitSetup(true)">Skip (no PIN)</button>
    </div>

    <!-- LOGIN SECTION -->
    <div id="auth-login-section" style="display:none;">
      <h3 style="margin:0 0 8px;color:var(--text-hi);font-size:16px;">Enter PIN</h3>
      <p style="color:var(--text-dim);font-size:12px;margin:0 0 16px;">Enter your InkSlab PIN to continue.</p>
      <input id="login-pin-input" type="password" inputmode="numeric" pattern="[0-9]*" placeholder="PIN" maxlength="8"
        style="width:100%;box-sizing:border-box;margin-bottom:10px;padding:12px;border-radius:8px;border:1px solid var(--border-hi);background:var(--bg-input);color:var(--text-hi);font-size:16px;text-align:center;letter-spacing:4px;"
        onkeydown="if(event.key==='Enter')submitLogin()">
      <div id="login-error" style="color:var(--danger);font-size:12px;min-height:16px;margin-bottom:8px;text-align:center;"></div>
      <button class="btn btn-primary btn-block" onclick="submitLogin()">Unlock</button>
    </div>
  </div>
</div>

<div class="status-pill">
  <span class="pill-logo">InkSlab<span id="pill-temp-wrap" style="display:none"> &middot; <span id="pill-temp"></span></span></span>
  <span id="pill-tcg" class="pill-tcg">InkSlab</span>
  <div class="pill-info">
    <svg id="wifi-icon" width="16" height="12" viewBox="0 0 16 12" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;margin-right:2px">
      <circle cx="8" cy="11" r="1.2" fill="currentColor"/>
      <path d="M5.2 8.2A3.8 3.8 0 0 1 8 7a3.8 3.8 0 0 1 2.8 1.2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" fill="none"/>
      <path d="M2.5 5.5A7.5 7.5 0 0 1 8 3.5a7.5 7.5 0 0 1 5.5 2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" fill="none" opacity="0.7"/>
    </svg>
    <span id="status-text">Loading...</span>
  </div>
</div>

<div class="content">

<!-- DISPLAY TAB -->
<div id="tab-display" class="panel active">
  <div class="display-col-left">
    <div class="hero-wrap">
      <div id="st-preview-wrap" onclick="showCardInfoModal()" style="cursor:pointer" title="Tap for card info">
        <img id="st-preview" class="preview-img" style="visibility:hidden" onerror="this.style.visibility='hidden'" onload="this.style.visibility='visible'">
        <div id="st-preview-loading">
          <div style="font-size:42px;margin-bottom:8px" class="preview-spin">&#8635;</div>
          <div id="st-preview-loading-text">Loading...</div>
        </div>
        <div class="preview-info-hint">&#9432;</div>
      </div>
      <div class="countdown" id="countdown"></div>
      <div class="player-controls">
        <button class="player-btn" id="btn-prev" onclick="prevCard()" title="Previous Card">&#9664;</button>
        <button class="player-btn play-pause" id="btn-pause" onclick="togglePause()" title="Pause/Play">&#10074;&#10074;</button>
        <button class="player-btn" id="btn-next" onclick="nextCard()" title="Next Card">&#9654;</button>
      </div>
    </div>
    <div class="card-info-inline">
      <div class="stats-grid">
        <div class="stat-cell">
          <div class="stat-label" id="si-card-label">Card #</div>
          <div class="stat-value" id="si-card">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label" id="si-total-label">Cards in Deck</div>
          <div class="stat-value" id="si-total">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label" id="si-rarity-label">Rarity</div>
          <div class="stat-value" id="si-rarity">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">Collection</div>
          <div class="stat-value" id="si-tcg">&mdash;</div>
        </div>
        <div class="stat-cell full-width">
          <div class="stat-label">Set</div>
          <div class="stat-value" id="si-set">&mdash;</div>
        </div>
      </div>
    </div>
    <div id="st-error-row" style="display:none;margin:8px 0;padding:8px;background:#ff6b6b22;border-radius:6px;">
      <span style="color:#ff6b6b;font-size:12px" id="st-error"></span>
    </div>
  </div>

  <!-- Card info modal (position:fixed — location in DOM doesn't affect rendering) -->
  <div class="modal-overlay" id="card-info-modal" onclick="this.classList.remove('open')">
    <div class="modal-content card-info-modal-content" onclick="event.stopPropagation()">
      <div class="stats-grid">
        <div class="stat-cell">
          <div class="stat-label" id="st-card-label">Card #</div>
          <div class="stat-value" id="st-card">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label" id="st-total-label">Cards in Deck</div>
          <div class="stat-value" id="st-total">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label" id="st-rarity-label">Rarity</div>
          <div class="stat-value" id="st-rarity">&mdash;</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">Collection</div>
          <div class="stat-value" id="st-tcg">&mdash;</div>
        </div>
        <div class="stat-cell full-width">
          <div class="stat-label">Set</div>
          <div class="stat-value" id="st-set">&mdash;</div>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm modal-close" onclick="document.getElementById('card-info-modal').classList.remove('open')">Close</button>
    </div>
  </div>

  <div class="display-col-right">
    <div class="card" id="queue-card">
      <div class="q-label">Up Next</div>
      <div class="q-list" id="q-next-list">
        <div class="q-card"><div class="q-thumb-placeholder"></div></div>
        <div class="q-card"><div class="q-thumb-placeholder"></div></div>
        <div class="q-card"><div class="q-thumb-placeholder"></div></div>
        <div class="q-card"><div class="q-thumb-placeholder"></div></div>
        <div class="q-card"><div class="q-thumb-placeholder"></div></div>
      </div>
    </div>
    <div class="card" id="prev-card">
      <div class="q-label">Previous</div>
      <div class="q-list" id="q-prev-list">
        <div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>
        <div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>
        <div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>
        <div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>
        <div class="q-placeholder"><div class="q-thumb-placeholder"></div></div>
      </div>
    </div>
    <div class="card mobile-qs-card">
      <h3>Quick Switch</h3>
      <div class="quick-switch-scroll" id="quick-switch-btns"></div>
    </div>
  </div>
</div>

<!-- SETTINGS TAB -->
<div id="tab-settings" class="panel">
  <div class="card">
    <h3>Display Settings</h3>
    <div class="settings-display-grid">
    <div class="form-row">
      <span class="row-label">Active Collection</span>
      <select id="cfg-tcg"></select>
    </div>
    <div class="form-row">
      <span class="row-label">Slab Header</span>
      <select id="cfg-header-mode">
        <option value="normal">Normal</option>
        <option value="inverted">Inverted</option>
        <option value="off">Off</option>
      </select>
    </div>
    <div class="form-row">
      <span class="row-label">Image Fit</span>
      <select id="cfg-image-fit">
        <option value="contain">Contain (letterbox)</option>
        <option value="fill">Fill (crop to fit)</option>
        <option value="stretch">Stretch</option>
      </select>
    </div>
    <div class="form-row">
      <span class="row-label">Letterbox Color</span>
      <select id="cfg-image-bg">
        <option value="black">Black</option>
        <option value="white">White</option>
      </select>
    </div>
    <div class="form-row">
      <span class="row-label">Rotation</span>
      <select id="cfg-rotation"><option value="0">0&deg;</option><option value="90">90&deg;</option><option value="180">180&deg;</option><option value="270">270&deg;</option></select>
    </div>
    <div class="form-row">
      <span class="row-label">Day Interval (min)</span>
      <input type="number" id="cfg-day-interval" min="1" max="120" value="10" inputmode="numeric">
    </div>
    <div class="form-row">
      <span class="row-label">Night Interval (min)</span>
      <input type="number" id="cfg-night-interval" min="1" max="480" value="60" inputmode="numeric">
    </div>
    <div class="form-row">
      <span class="row-label">Day Start (24h)</span>
      <input type="number" id="cfg-day-start" min="0" max="23" value="7" inputmode="numeric">
    </div>
    <div class="form-row">
      <span class="row-label">Day End (24h)</span>
      <input type="number" id="cfg-day-end" min="0" max="23" value="23" inputmode="numeric">
    </div>
    <div class="form-row">
      <span class="row-label">Color Saturation</span>
      <input type="number" id="cfg-saturation" min="0.5" max="5.0" step="0.1" value="2.5" inputmode="decimal">
    </div>
    <div class="form-row">
      <span class="row-label">UI Theme</span>
      <select id="cfg-theme" onchange="saveTheme(this.value)">
        <option value="default">Default (Blue/Green)</option>
        <option value="auto">Auto (Match Collection)</option>
        <option value="lorcana">Lorcana (Purple)</option>
        <option value="pokemon">Pokemon (Blue)</option>
        <option value="mtg">Magic (Teal)</option>
        <option value="manga">Manga (Pink)</option>
        <option value="comics">Comics (Orange)</option>
        <option value="custom">Custom (Amber)</option>
      </select>
    </div>
    <div class="form-row" style="align-items:flex-start;">
      <span class="row-label">Collection Image Caching</span>
      <div style="display:flex;flex-direction:column;align-items:flex-end;">
        <label class="switch">
          <input type="checkbox" id="cfg-thumbnails">
          <span class="switch-slider"></span>
        </label>
        <div id="precache-status" style="font-size:11px;color:var(--text-dim);margin-top:4px;display:none;text-align:right;"></div>
      </div>
    </div>
    </div><!-- end settings-display-grid -->
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">
      <button class="btn btn-primary btn-block" onclick="saveSettings()">Save Settings</button>
    </div>
  </div>
  <div class="settings-mid-cols">
    <div class="settings-col-left">
      <div class="card">
        <h3>Auto-Update Sources</h3>
        <p style="color:var(--text-dim);font-size:12px;margin-bottom:10px;">Sources checked automatically every week. Toggle to enable or disable.</p>
        <div id="auto-update-list"></div>
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
          <div id="auto-update-next" style="font-size:13px;color:var(--text-dim);margin-bottom:10px;">Next scheduled: —</div>
        </div>
        <div class="au-run-wrap">
          <button id="btn-run-all" class="btn btn-secondary btn-block" onclick="runAllNow()">Run All Now</button>
        </div>
      </div>
    </div>
    <div class="settings-col-right">
      <div class="card">
        <h3>Metron Comics Account</h3>
        <p style="color:var(--text-dim);font-size:12px;margin-bottom:10px;">Required for comic book cover downloads. <a href="https://metron.cloud/accounts/signup/" target="_blank" style="color:#F97316;">Sign up free at metron.cloud</a></p>
        <div id="metron-status" style="margin-bottom:10px;"></div>
        <div id="metron-form" style="display:none;">
          <div class="form-group">
            <label>Metron Username</label>
            <input type="text" id="metron-username" placeholder="your username" autocomplete="off">
          </div>
          <div class="form-group">
            <label>Metron Password</label>
            <input type="password" id="metron-password" placeholder="your password" autocomplete="off">
          </div>
          <div style="display:flex;gap:8px;margin-top:4px;">
            <button class="btn btn-secondary" style="flex:1" onclick="testMetronCreds()">Test Connection</button>
            <button class="btn btn-primary" style="flex:1" onclick="saveMetronCreds()">Save Credentials</button>
          </div>
          <div id="metron-test-result" style="margin-top:8px;font-size:13px;display:none;"></div>
        </div>
      </div>
      <div class="card settings-pin-card">
        <h3>Dashboard PIN</h3>
        <p style="color:var(--text-dim);font-size:12px;margin-bottom:10px;">Protect access to InkSlab with a 4-8 digit PIN. Your browser session stays logged in for 30 days.</p>
        <div id="pin-status" style="font-size:13px;margin-bottom:10px;"></div>
        <div id="pin-form" style="display:none;">
          <div class="form-group">
            <label id="pin-current-label">Current PIN</label>
            <input type="password" id="pin-current" inputmode="numeric" pattern="[0-9]*" placeholder="current PIN" maxlength="8" autocomplete="off">
          </div>
          <div class="form-group">
            <label>New PIN <span style="color:var(--text-dim);font-size:11px;">(leave blank to remove PIN)</span></label>
            <input type="password" id="pin-new" inputmode="numeric" pattern="[0-9]*" placeholder="4-8 digits, or blank to remove" maxlength="8" autocomplete="new-password">
          </div>
          <div id="pin-error" style="color:var(--danger);font-size:12px;min-height:16px;margin-bottom:8px;"></div>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-primary" style="flex:1;" onclick="savePinChange()">Save</button>
            <button class="btn" style="flex:1;background:transparent;border:1px solid var(--border);color:var(--text-dim);" onclick="document.getElementById('pin-form').style.display='none'">Cancel</button>
          </div>
        </div>
        <button id="pin-set-btn" class="btn btn-secondary btn-block" onclick="showPinForm()" style="display:none;"></button>
      </div>
      <div class="card" style="margin-bottom:0">
        <h3>WiFi Network</h3>
        <div id="wifi-info" style="font-size:13px;color:var(--text-dim);margin-bottom:10px">Checking WiFi...</div>
        <button class="btn btn-secondary btn-block" onclick="changeWifi()">Change WiFi Network</button>
      </div>
    </div>
  </div>
  <div class="card settings-update-card">
    <h3>Software Update</h3>
    <div id="update-info" style="margin-bottom:10px;font-size:13px;color:var(--text-dim);cursor:default;-webkit-user-select:none;user-select:none" onclick="adminTap()">Loading version...</div>
    <div class="flex-row" style="margin-bottom:8px">
      <button class="btn btn-secondary btn-block" onclick="checkUpdate()">Check for Updates</button>
      <button class="btn btn-primary btn-block" id="btn-update-now" style="display:none" onclick="startUpdate()">Update Now</button>
    </div>
    <div id="update-progress" style="display:none">
      <div style="background:var(--bg-input);border-radius:4px;height:8px;margin:8px 0"><div id="update-bar" style="height:100%;border-radius:4px;background:var(--accent);width:0%;transition:width 0.5s"></div></div>
      <div id="update-stage" style="font-size:12px;color:var(--text-dim);text-align:center"></div>
    </div>
  </div>
  <div class="card" id="admin-panel" style="display:none;border:1px solid var(--danger)">
    <h3 style="color:var(--danger)">Prepare for New Owner</h3>
    <p style="color:var(--text-dim);font-size:12px;margin-bottom:10px">This will delete WiFi, Settings, Metron Credentials, and all Card Libraries. Check any libraries below that you want to keep.</p>
    <div style="margin-bottom:12px;font-size:12px;color:var(--text);">Keep these card libraries:<br>
      <label style="display:block;padding:3px 0;"><input type="checkbox" id="keep-pokemon" checked> Pokemon</label>
      <label style="display:block;padding:3px 0;"><input type="checkbox" id="keep-mtg" checked> Magic: The Gathering</label>
      <label style="display:block;padding:3px 0;"><input type="checkbox" id="keep-lorcana" checked> Disney Lorcana</label>
      <label style="display:block;padding:3px 0;"><input type="checkbox" id="keep-manga" checked> Manga</label>
      <label style="display:block;padding:3px 0;"><input type="checkbox" id="keep-comics" checked> Comics</label>
    </div>
    <button class="btn btn-block" style="background:var(--danger);color:var(--bg);font-weight:600" onclick="factoryReset(this)">Prepare for New Owner</button>
  </div>
</div>

<!-- COLLECTION TAB -->
<div id="tab-collection" class="panel">
  <div class="two-col-cards">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <div>
          <h3 style="margin-bottom:4px">My Collection</h3>
          <p style="color:var(--text-dim);font-size:12px;margin:0">Mark cards as owned to build your collection. Enable <strong>Collection Only Mode</strong> to display only your owned cards.</p>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="clearCollection()" style="flex-shrink:0">Clear All</button>
      </div>
    </div>
    <div class="card collection-only-card">
      <h3>Collection Only Mode</h3>
      <p style="color:var(--text-dim);font-size:12px;margin:0">When ON, only cards you have marked as owned will display on the e-ink screen.</p>
      <label class="switch">
        <input type="checkbox" id="cfg-collection" onchange="saveCollectionMode()">
        <span class="switch-slider"></span>
      </label>
    </div>
  </div>
  <div class="card">
    <h3>Search Collection</h3>
    <p style="color:var(--text-dim);font-size:12px;margin-bottom:8px">Find by name and add all versions to your collection.</p>
    <div id="tcg-browse-pills" class="tcg-browse-row"></div>
    <div id="search-filters" class="search-filters" style="display:none"></div>
    <div class="search-wrap">
      <span class="search-icon">&#128269;</span>
      <input type="text" id="search-input" placeholder="Search by card name..." oninput="debounceSearch()" autocomplete="off">
      <button id="search-clear" class="search-clear-btn" onclick="clearSearch()" style="display:none">&#10005;</button>
    </div>
    <div id="search-results" class="search-results"></div>
  </div>
  <div class="card">
    <h3 style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;" onclick="toggleRarityFilter()">Add to Collection by Rarity <span id="rarity-toggle-icon" style="font-size:12px;color:var(--text-dim);">▼ Show</span></h3>
    <div id="rarity-filter-body" style="display:none;">
      <p style="color:var(--text-dim);font-size:12px;margin-bottom:8px">Toggle rarities on/off across all sets. Checked = cards of that rarity are in your collection.</p>
      <div class="rarity-filter-actions">
        <button class="btn btn-secondary btn-sm" onclick="selectAllRarities(true)">Select All</button>
        <button class="btn btn-secondary btn-sm" onclick="selectAllRarities(false)">Deselect All</button>
      </div>
      <div class="rarity-filter-wrap" id="rarity-chips"></div>
      <div id="rarity-result" style="color:var(--text-dim);font-size:12px;margin-top:6px"></div>
    </div>
  </div>
  <div id="sets-list"></div>
</div>

<!-- DOWNLOADS TAB -->
<div id="tab-downloads" class="panel">
  <div class="dl-col-left">
    <div class="card">
      <h3>Storage</h3>
      <div id="storage-info" style="min-height:80px"></div>
    </div>
    <div class="card">
      <h3>Downloads</h3>
      <div id="dl-buttons" style="min-height:44px"></div>
      <div id="dl-lorcana-search" style="display:none;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <div style="position:relative;flex:1">
            <input id="lorcana-search-input" type="text" placeholder="e.g. D23 Collection, Reign of Jafar... (or leave blank for all)"
              oninput="_dlInputChange(this)" style="width:100%;padding:8px;padding-right:32px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text-hi);font-size:14px;box-sizing:border-box;">
            <button class="search-clear-btn" onclick="_dlClearInput('lorcana-search-input','lorcana-search-results')" style="display:none">&#10005;</button>
          </div>
          <button onclick="lorcanaSearch()"
            style="padding:8px 14px;background:#C084FC;color:var(--bg);border:none;border-radius:6px;cursor:pointer;font-weight:600;">Search</button>
        </div>
        <div id="lorcana-search-results" style="display:none;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;"></div>
      </div>
      <div id="dl-mtg-search" style="display:none;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <div style="position:relative;flex:1">
            <input id="mtg-set-search-input" type="text" placeholder="e.g. Modern Horizons, Bloomburrow, Foundations..."
              oninput="_dlInputChange(this)" style="width:100%;padding:8px;padding-right:32px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text-hi);font-size:14px;box-sizing:border-box;">
            <button class="search-clear-btn" onclick="_dlClearInput('mtg-set-search-input','mtg-set-search-results')" style="display:none">&#10005;</button>
          </div>
          <button onclick="mtgSetSearch()"
            style="padding:8px 14px;background:#6BCCBD;color:var(--bg);border:none;border-radius:6px;cursor:pointer;font-weight:600;">Search</button>
        </div>
        <div id="mtg-set-search-results" style="display:none;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;"></div>
      </div>
      <div id="dl-pokemon-search" style="display:none;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <div style="position:relative;flex:1">
            <input id="pokemon-search-input" type="text" placeholder="e.g. Base Set, Scarlet & Violet, Prismatic Evolutions..."
              oninput="_dlInputChange(this)" style="width:100%;padding:8px;padding-right:32px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text-hi);font-size:14px;box-sizing:border-box;">
            <button class="search-clear-btn" onclick="_dlClearInput('pokemon-search-input','pokemon-search-results')" style="display:none">&#10005;</button>
          </div>
          <button onclick="pokemonSearch()"
            style="padding:8px 14px;background:#36A5CA;color:var(--bg);border:none;border-radius:6px;cursor:pointer;font-weight:600;">Search</button>
        </div>
        <div id="pokemon-search-results" style="display:none;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;"></div>
      </div>
      <div id="dl-manga-search" style="display:none;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <div style="position:relative;flex:1">
            <input id="manga-search-input" type="text" placeholder="e.g. Naruto, Berserk, Chainsaw Man..."
              oninput="_dlInputChange(this)" style="width:100%;padding:8px;padding-right:32px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text-hi);font-size:14px;box-sizing:border-box;">
            <button class="search-clear-btn" onclick="_dlClearInput('manga-search-input','manga-search-results')" style="display:none">&#10005;</button>
          </div>
          <button onclick="mangaSearch()"
            style="padding:8px 14px;background:#F472B6;color:var(--bg);border:none;border-radius:6px;cursor:pointer;font-weight:600;">Search</button>
        </div>
        <div id="manga-search-results" style="display:none;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;"></div>
      </div>
      <div id="dl-comics-search" style="display:none;margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <div style="position:relative;flex:1">
            <input id="comics-search-input" type="text" placeholder="e.g. Batman, Amazing Spider-Man..."
              oninput="_dlInputChange(this)" style="width:100%;padding:8px;padding-right:32px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text-hi);font-size:14px;box-sizing:border-box;">
            <button class="search-clear-btn" onclick="_dlClearInput('comics-search-input','comics-search-results')" style="display:none">&#10005;</button>
          </div>
          <button onclick="comicSearch()"
            style="padding:8px 14px;background:#F97316;color:var(--bg);border:none;border-radius:6px;cursor:pointer;font-weight:600;">Search</button>
        </div>
        <div id="comics-search-results" style="display:none;border:1px solid var(--border);border-radius:6px;margin-bottom:8px;"></div>
      </div>
    </div>
    <div class="card">
      <h3>Custom Images</h3>
      <p style="font-size:12px;color:var(--text-dim);margin-bottom:12px;">Upload your own images to display. Create folders to organize them.</p>
      <div style="display:flex;gap:8px;margin-bottom:12px;">
        <input id="custom-folder-name" type="text" placeholder="New folder name..."
          style="flex:1;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--bg-input);color:var(--text);font-size:14px;">
        <button onclick="createCustomFolder()" class="btn"
          style="background:var(--accent2);color:#010001;border:none;white-space:nowrap;">+ Create</button>
      </div>
      <div id="custom-folders"></div>
    </div>
    <div class="card" id="dl-status-card">
      <h3>Download Status</h3>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div id="dl-status" style="color:var(--text-dim);font-size:13px;">Idle</div>
        <div style="display:flex;gap:6px;align-items:center;">
          <button class="btn btn-sm" id="btn-dl-stop" onclick="stopDownload()" style="display:none;background:var(--danger);color:var(--bg);border:none;">Stop</button>
          <button class="btn btn-sm btn-secondary" id="btn-dl-log-toggle" onclick="toggleDlLog()">Show Log</button>
        </div>
      </div>
      <pre id="dl-log" class="log-box" style="display:none;height:200px;margin:0"></pre>
    </div>
    <div class="card">
      <h3>Delete Entire Library</h3>
      <div id="delete-buttons"></div>
    </div>
  </div>
</div><!-- /tab-downloads -->

</div><!-- /content -->

<!-- Card preview modal -->
<div class="modal-overlay" id="preview-modal" onclick="closePreview()">
  <div class="modal-content preview-modal-content" onclick="event.stopPropagation()">
    <img id="preview-img" src="" onclick="closePreview()" style="cursor:pointer">
    <div class="stats-grid preview-modal-stats" style="margin-top:12px">
      <div class="stat-cell">
        <div class="stat-label" id="pm-num-label">Card #</div>
        <div class="stat-value" id="pm-num">&mdash;</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label" id="pm-rarity-label">Rarity</div>
        <div class="stat-value" id="pm-rarity">&mdash;</div>
      </div>
      <div class="stat-cell full-width">
        <div class="stat-label">Set</div>
        <div class="stat-value" id="pm-set">&mdash;</div>
      </div>
    </div>
    <button class="btn btn-secondary btn-sm modal-close" onclick="closePreview()">Close</button>
  </div>
</div>

<div id="toast" style="display:none;position:fixed;bottom:74px;left:50%;transform:translateX(-50%);background:var(--accent);color:#010001;padding:10px 24px;border-radius:20px;font-size:13px;font-weight:600;z-index:200;opacity:0;transition:opacity 0.3s;pointer-events:none;"></div>

<nav class="bottom-nav">
  <div class="sidebar-brand">
    <img src="/static/apple-touch-icon.png" class="sb-logo-img" alt="InkSlab">
    <div class="sb-brand-text">InkSlab</div>
    <span id="sb-tcg" class="pill-tcg sb-tcg-pill">InkSlab</span>
  </div>
  <div class="sb-section-label">CORE</div>
  <div class="nav-item active" data-tab="display" onclick="showTab('display')">
    <span class="nav-icon">&#9654;</span>
    <span class="nav-label">Display</span>
  </div>
  <div class="nav-item" data-tab="collection" onclick="showTab('collection')">
    <span class="nav-icon">&#9776;</span>
    <span class="nav-label">Collection</span>
  </div>
  <div class="nav-item" data-tab="downloads" onclick="showTab('downloads')">
    <span class="nav-icon">&#8595;</span>
    <span class="nav-label">Downloads</span>
  </div>
  <div class="sb-section-label">FEATURES</div>
  <div class="nav-item" data-tab="settings" onclick="showTab('settings')">
    <span class="nav-icon">&#9881;</span>
    <span class="nav-label">Settings</span>
  </div>
  <div class="sb-widget">
    <div class="sb-widget-label">Quick Switch</div>
    <div class="quick-switch-scroll" id="sb-quick-switch-btns"></div>
  </div>
  <div class="sb-widget sb-widget-stats">
    <div class="sb-widget-label">Raspberry Pi</div>
    <div id="system-stats">
      <div class="stat"><span class="stat-label">CPU Temp</span><span class="stat-value">&mdash;</span></div>
      <div class="stat"><span class="stat-label">RAM</span><span class="stat-value">&mdash;</span></div>
      <div class="stat"><span class="stat-label">Uptime</span><span class="stat-value">&mdash;</span></div>
      <div class="stat"><span class="stat-label">WiFi</span><span class="stat-value">&mdash;</span></div>
    </div>
  </div>
  <div class="sb-bottom">
    <div id="sb-version" style="font-size:10px;color:var(--text-dim)"></div>
  </div>
</nav>

<script src="/static/app.js?v=3"></script>
<script src="/static/collection_view.js"></script>
<script src="/static/delete_library.js"></script>
<script src="/static/search_fix.js"></script>
<script src="/static/pokemon_bulk.js"></script>
<script src=/static/mtg_sets.js></script>
</body>
</html>"""


@app.route('/')
def dashboard():
    if _wifi_setup_mode:
        return WIFI_SETUP_HTML
    token = _get_csrf_token()
    return DASHBOARD_HTML.replace('__CSRF_TOKEN__', token)


# --- Auto-update background thread ---

def _run_auto_updates():
    """Background thread: check weekly and run enabled downloaders."""
    global _download_proc, _download_tcg
    import time as _time
    import logging as _logging
    _tlog = _logging.getLogger(__name__)
    _time.sleep(5)  # brief startup delay
    while True:
        try:
            config = load_config()
            sources = config.get("auto_update_sources", [])
            if sources:
                now = datetime.datetime.now()
                last_times = {}
                if os.path.exists(LAST_UPDATE_FILE):
                    try:
                        with open(LAST_UPDATE_FILE) as f:
                            last_times = json.load(f)
                    except Exception:
                        pass
                for tcg in sources:
                    last_str = last_times.get(tcg)
                    run_it = not last_str
                    if not run_it and last_str:
                        try:
                            last_dt = datetime.datetime.fromisoformat(last_str)
                            if (now - last_dt).days >= 7:
                                run_it = True
                        except Exception:
                            run_it = True
                    if run_it:
                        reg = TCG_REGISTRY.get(tcg)
                        if not reg or not reg.get("download_script"):
                            continue
                        if not _has_disk_space():
                            _tlog.warning(f"Auto-update: skipping {tcg} - low disk space")
                            continue
                        _tlog.info(f"Auto-update: running {tcg} downloader")
                        cmd = ["python3", os.path.join(SCRIPT_DIR, "scripts", reg["download_script"])]
                        proc = None
                        with _download_lock:
                            if _download_proc and _download_proc.poll() is None:
                                _tlog.warning(f"Auto-update: skipping {tcg} - download already running")
                                continue
                            try:
                                proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
                                _download_proc = proc
                                _download_tcg = tcg
                            except Exception as e:
                                _tlog.error(f"Auto-update {tcg} failed to start: {e}")
                                continue
                        try:
                            proc.wait(timeout=3600)
                            last_times[tcg] = now.isoformat()
                            _atomic_write_json(LAST_UPDATE_FILE, last_times)
                            _tlog.info(f"Auto-update: {tcg} complete")
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            _tlog.error(f"Auto-update {tcg} timed out")
                        except Exception as e:
                            _tlog.error(f"Auto-update {tcg} failed: {e}")
                        finally:
                            with _download_lock:
                                if _download_proc is proc:
                                    _download_proc = None
                                    _download_tcg = None
        except Exception as e:
            _tlog.error(f"Auto-update thread error: {e}")
        _time.sleep(3600)  # check every hour

@app.route('/api/auto_update/status')
def api_auto_update_status():
    """Return last update times and configured sources."""
    last_times = {}
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            with open(LAST_UPDATE_FILE) as f:
                last_times = json.load(f)
        except Exception:
            pass
    config = load_config()
    sources = config.get('auto_update_sources', [])
    result = {}
    for tcg, info in TCG_REGISTRY.items():
        if not info.get('download_script'):
            continue
        result[tcg] = {
            'name': info['name'],
            'enabled': tcg in sources,
            'last_update': last_times.get(tcg, None),
        }
    return jsonify(result)

@app.route('/api/auto_update/save', methods=['POST'])
@protected
def api_auto_update_save():
    """Save auto-update source selection."""
    data = request.get_json(force=True) if request.data else {}
    sources = data.get('sources', [])
    config = load_config()
    config['auto_update_sources'] = sources
    _atomic_write_json(CONFIG_FILE, config, indent=2)
    return jsonify({'ok': True})

@app.route('/api/auto_update/run_now', methods=['POST'])
@protected
def api_auto_update_run_now():
    """Manually trigger update for a specific TCG."""
    global _download_proc, _download_tcg, _download_log_fh
    data = request.get_json(force=True) if request.data else {}
    tcg = data.get('tcg')
    reg = TCG_REGISTRY.get(tcg)
    if not reg or not reg.get('download_script'):
        return jsonify({'ok': False, 'error': 'Unknown TCG'})
    with _download_lock:
        if _download_proc and _download_proc.poll() is None:
            return jsonify({'ok': False, 'error': 'Download already running'})
        _close_download_log()
        cmd = ['python3', os.path.join(SCRIPT_DIR, 'scripts', reg['download_script'])]
        try:
            _download_log_fh = open(DOWNLOAD_LOG, 'w')
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            _download_proc = subprocess.Popen(cmd, stdout=_download_log_fh, stderr=subprocess.STDOUT, cwd=SCRIPT_DIR, env=env)
            _download_tcg = tcg
        except Exception as e:
            _close_download_log()
            return jsonify({'ok': False, 'error': str(e)})
    return jsonify({'ok': True, 'tcg': tcg})

@app.route('/api/auto_update/run_all', methods=['POST'])
@protected
def api_auto_update_run_all():
    """Manually trigger all enabled auto-update sources sequentially in a background thread."""
    global _run_all_running
    if _run_all_running:
        return jsonify({'ok': False, 'error': 'Already running'})
    config = load_config()
    sources = config.get('auto_update_sources', [])
    if not sources:
        return jsonify({'ok': False, 'error': 'No sources enabled'})
    def _do_run_all():
        global _run_all_running, _download_proc, _download_tcg
        _run_all_running = True
        try:
            last_times = {}
            if os.path.exists(LAST_UPDATE_FILE):
                try:
                    with open(LAST_UPDATE_FILE) as f:
                        last_times = json.load(f)
                except Exception:
                    pass
            for tcg in sources:
                reg = TCG_REGISTRY.get(tcg)
                if not reg or not reg.get('download_script'):
                    continue
                if not _has_disk_space():
                    continue
                cmd = ['python3', os.path.join(SCRIPT_DIR, 'scripts', reg['download_script'])]
                proc = None
                with _download_lock:
                    if _download_proc and _download_proc.poll() is None:
                        continue
                    try:
                        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
                        _download_proc = proc
                        _download_tcg = tcg
                    except Exception:
                        continue
                try:
                    proc.wait(timeout=3600)
                    last_times[tcg] = datetime.datetime.now().isoformat()
                    _atomic_write_json(LAST_UPDATE_FILE, last_times)
                except subprocess.TimeoutExpired:
                    proc.kill()
                except Exception:
                    pass
                finally:
                    with _download_lock:
                        if _download_proc is proc:
                            _download_proc = None
                            _download_tcg = None
        finally:
            _run_all_running = False
    threading.Thread(target=_do_run_all, daemon=True).start()
    return jsonify({'ok': True, 'count': len(sources)})

import logging as _logging
_logging.basicConfig(level=_logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_logger = _logging.getLogger(__name__)

_startup_done = False
_startup_lock = threading.Lock()


def _app_startup():
    """One-time startup: background threads, WiFi check. Safe to call from Gunicorn workers."""
    global _startup_done, _wifi_setup_mode
    if _startup_done:
        return
    with _startup_lock:
        if _startup_done:
            return
        _startup_done = True

    _logger.info("InkSlab Web Dashboard starting...")

    # Start auto-update background thread
    _auto_update_thread = threading.Thread(target=_run_auto_updates, daemon=True)
    _auto_update_thread.start()

    # Auto-start thumbnail background caching if toggle was on before restart
    if load_config().get('thumbnail_cache'):
        _start_precache_thread()

    # Pre-warm storage cache so Downloads tab loads instantly on first visit
    _trigger_storage_recompute()

    # Enter setup mode if WiFi is not connected AND no saved profile exists.
    try:
        if not wifi_manager.is_wifi_connected():
            _wifi_setup_mode = True
            _logger.info("No WiFi connection on boot — entering setup mode")
            wifi_manager.start_hotspot()
        else:
            _logger.info("WiFi configured — serving dashboard")
    except Exception as e:
        _logger.warning("WiFi check failed, skipping setup mode: %s", e)


@app.before_request
def _lazy_startup():
    _app_startup()


if __name__ == '__main__':
    _app_startup()
    try:
        app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
    except Exception as e:
        _logger.error("Web server crashed: %s", e, exc_info=True)
