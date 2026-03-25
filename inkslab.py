#!/usr/bin/python3
# -*- coding:utf-8 -*-
"""
InkSlab - e-Ink TCG Card Display
https://github.com/costamesatechsolutions/inkslab-eink-tcg-display

Displays random TCG cards on a Waveshare 4" e-Paper (E) / Spectra 6 color display
in a graded-slab-style layout with set name, year, card number, and rarity.
Cards rotate every 10 minutes during the day (7am-11pm) and every hour at night.

By Costa Mesa Tech Solutions (a brand of Pine Heights Ventures LLC)
"""

import sys
import os
import time
import random
import json
import logging
import signal
import tempfile
from collections import deque
from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageOps
import wifi_manager

# --- DEFAULT CONFIGURATION ---
# These defaults are used if no config file exists.
# The web dashboard writes to the config file to change settings on the fly.
DEFAULTS = {
    "active_tcg": "pokemon",
    "rotation_angle": 270,
    "day_interval": 600,
    "night_interval": 3600,
    "day_start": 7,
    "day_end": 23,
    "color_saturation": 2.5,
    "collection_only": False,
    "slab_header_mode": "normal",
    "image_fit": "contain",
    "image_bg": "black",
}

# --- DYNAMIC TCG REGISTRY ---
TCG_REGISTRY = {
    "pokemon": {"name": "Pokemon", "path": "/home/pi/inkslab-collections/pokemon", "color": "#36A5CA", "download_script": "download_cards_pokemon.py"},
    "mtg":     {"name": "Magic: The Gathering", "path": "/home/pi/inkslab-collections/mtg", "color": "#6BCCBD", "download_script": "download_cards_mtg.py"},
    "lorcana": {"name": "Disney Lorcana", "path": "/home/pi/inkslab-collections/lorcana", "color": "#C084FC", "download_script": "download_cards_lorcana.py"},
    "manga":   {"name": "Manga", "path": "/home/pi/inkslab-collections/manga", "color": "#FF6B6B", "download_script": "download_covers_manga.py"},
    "comics":  {"name": "Comics", "path": "/home/pi/inkslab-collections/comics", "color": "#F97316", "download_script": "download_covers_comics.py"},
    "custom":  {"name": "Custom", "path": "/home/pi/inkslab-collections/custom", "color": "#F59E0B", "download_script": None},
}
TCG_LIBRARIES = {k: v["path"] for k, v in TCG_REGISTRY.items()}

# Supported image formats
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')

CONFIG_FILE = "/home/pi/.inkslab/inkslab_config.json"
COLLECTION_FILE = "/home/pi/.inkslab/inkslab_collection.json"
STATUS_FILE = "/tmp/inkslab_status.json"
NEXT_TRIGGER = "/tmp/inkslab_next"
PREV_TRIGGER = "/tmp/inkslab_prev"
PAUSE_FILE = "/tmp/inkslab_pause"
COLLECTION_TRIGGER = "/tmp/inkslab_collection_changed"
REDRAW_TRIGGER = "/tmp/inkslab_redraw"
WIFI_CONNECTED_TRIGGER = "/tmp/inkslab_wifi_connected"
WIFI_SETUP_TRIGGER = "/tmp/inkslab_wifi_setup"
UNBOX_TRIGGER = "/tmp/inkslab_unbox"

# Graceful shutdown flag (module-level so wait_with_polling can check it)
_shutdown = False

# Image processing (not configurable via web — these are display-specific)
DISPLAY_WIDTH = 400
DISPLAY_HEIGHT = 600
CONTRAST_BOOST = 1.1
SHARPNESS_BOOST = 1.4

# 7-color palette for Spectra 6: Black, White, Green, Blue, Red, Yellow, Orange
PALETTE_COLORS = [0, 0, 0, 255, 255, 255, 0, 255, 0, 0, 0, 255, 255, 0, 0, 255, 255, 0, 255, 128, 0]

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- HARDWARE SETUP ---
# Try the Waveshare SDK lib (three levels up: project dir -> examples -> python -> lib)
_script_dir = os.path.dirname(os.path.realpath(__file__))
_sdk_libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(_script_dir))), 'lib')
_local_libdir = os.path.join(_script_dir, 'lib')

if os.path.exists(_sdk_libdir):
    sys.path.insert(0, _sdk_libdir)
if os.path.exists(_local_libdir):
    sys.path.insert(0, _local_libdir)

try:
    from waveshare_epd import epd4in0e
except ImportError:
    logger.error(f"Cannot import waveshare_epd. Checked: {_sdk_libdir}, {_local_libdir}")
    logger.error("Make sure the Waveshare e-Paper library is installed.")
    sys.exit(1)


def load_config():
    """Load config from file, falling back to defaults for missing keys."""
    import fcntl
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    saved = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            config.update(saved)
        except Exception as e:
            logger.warning(f"Error reading config: {e}, using defaults")
    return config


def load_collection(tcg):
    """Load the collection list for a given TCG. Returns a set of card IDs."""
    import fcntl
    if os.path.exists(COLLECTION_FILE):
        try:
            with open(COLLECTION_FILE, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            return set(data.get(tcg, []))
        except Exception:
            pass
    return set()


def load_master_index(library_dir):
    """Load the master set index from a library directory.
    Falls back to auto-discovering subdirectories for custom folders."""
    index_file = os.path.join(library_dir, "master_index.json")
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r') as f:
                index = json.load(f)
            # Also discover any subdirs not in the index (newly added custom folders)
            if os.path.isdir(library_dir):
                for d in os.listdir(library_dir):
                    if os.path.isdir(os.path.join(library_dir, d)) and d not in index:
                        index[d] = {"name": d.replace('_', ' ').replace('-', ' ').title(), "year": ""}
            return index
        except Exception:
            pass
    # No index file — auto-discover from subdirectories
    index = {}
    if os.path.isdir(library_dir):
        for d in os.listdir(library_dir):
            if os.path.isdir(os.path.join(library_dir, d)):
                index[d] = {"name": d.replace('_', ' ').replace('-', ' ').title(), "year": ""}
    return index


def write_status(info):
    """Write current display status for the web dashboard (atomic)."""
    try:
        dir_name = os.path.dirname(STATUS_FILE) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(info, f)
            os.replace(tmp, STATUS_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        pass


def _is_card_image(filename):
    """Check if a file is a supported card image."""
    return filename.lower().endswith(IMAGE_EXTENSIONS) and not filename.startswith('_')


def get_local_ip():
    """Get the Pi's local IP address (non-hotspot)."""
    try:
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        parts = result.stdout.strip().split()
        # Filter out hotspot IPs so splash screen shows the real LAN address
        for ip in parts:
            if not ip.startswith("10.42."):
                return ip
        return parts[0] if parts else None
    except Exception:
        return None


def make_qr(url, box_size=4, border=1):
    """Generate a QR code as a PIL RGB image."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=box_size, border=border,
                            error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGB")
    except Exception as e:
        logger.warning(f"QR code generation failed: {e}")
        return None


def show_splash_screen(epd, config):
    """Show a branded splash screen with the dashboard URL on the e-ink display.
    Handles full init/display/sleep cycle internally."""
    try:
        # Wait up to 30s for an IP address (network may still be coming up)
        ip = None
        for _ in range(6):
            ip = get_local_ip()
            if ip:
                break
            time.sleep(5)
        if not ip:
            logger.info("No IP address available after 30s, showing splash without URL")
            ip = "<no IP yet>"

        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        MARGIN = 20
        max_w = DISPLAY_WIDTH - 2 * MARGIN
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        def fit_font(size):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                return ImageFont.load_default()

        def shrink_to_fit(text, size):
            """Return a font that fits text within max_w."""
            f = fit_font(size)
            while size > 10 and draw.textlength(text, font=f) > max_w:
                size -= 1
                f = fit_font(size)
            return f

        font_title = fit_font(42)
        font_body  = fit_font(18)
        font_small = fit_font(14)

        # Draw content centered
        cx = DISPLAY_WIDTH // 2

        # Title
        draw.text((cx, 70), "InkSlab", fill=(0, 0, 0), font=font_title, anchor="mm")

        # Dashboard URL with QR code
        url_text = f"http://{ip}"
        font_url = shrink_to_fit(url_text, 28)
        draw.text((cx, 120), "Scan or open in your", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 144), "web browser:", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 186), url_text, fill=(0, 0, 0), font=font_url, anchor="mm")

        # QR code — larger to fill available space
        qr_img = make_qr(url_text)
        if qr_img:
            qr_size = min(qr_img.size[0], 190)
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            canvas.paste(qr_img, (cx - qr_size // 2, 216))
            qr_img.close()

        # Transition note (two lines to stay within 400px width)
        draw.text((cx, 428), "Your collection will appear", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 450), "in ~3 minutes.", fill=(0, 0, 0), font=font_body, anchor="mm")

        # Bottom credit
        draw.text((cx, 555), "Costa Mesa Tech Solutions", fill=(0, 0, 0), font=font_small, anchor="mm")

        # Process for e-paper display
        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        canvas.close()
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        img.close()
        palette_ref.close()
        img_rgb = img_dithered.convert("RGB")
        img_dithered.close()
        final = img_rgb.rotate(config["rotation_angle"], expand=True)
        img_rgb.close()

        epd.init()
        epd.display(epd.getbuffer(final))
        epd.sleep()
        final.close()
        logger.info(f"Splash screen shown: dashboard at {url_text}")

    except Exception as e:
        logger.warning(f"Splash screen skipped: {e}")
        try:
            epd.sleep()
        except Exception:
            pass


def show_setup_screen(epd, config):
    """Show WiFi setup instructions on the e-ink display when no WiFi is configured.
    Handles full init/display/sleep cycle internally."""
    try:
        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Load fonts
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            font_heading = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            font_url = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        except Exception:
            font_title = ImageFont.load_default()
            font_heading = font_title
            font_body = font_title
            font_url = font_title
            font_small = font_title

        cx = DISPLAY_WIDTH // 2

        # Title
        draw.text((cx, 40), "InkSlab WiFi Setup", fill=(0, 0, 0), font=font_title, anchor="mm")

        # Step 1
        draw.text((cx, 90), "Step 1", fill=(0, 0, 0), font=font_heading, anchor="mm")
        draw.text((cx, 118), "On your phone, go to Settings", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 141), "and connect to this WiFi:", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 178), "InkSlab-Setup", fill=(0, 0, 0), font=font_url, anchor="mm")
        draw.text((cx, 206), "(no password needed)", fill=(0, 0, 0), font=font_small, anchor="mm")

        # Step 2
        draw.text((cx, 255), "Step 2", fill=(0, 0, 0), font=font_heading, anchor="mm")
        draw.text((cx, 283), "A setup page should appear.", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 306), "If not, scan this code or", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 329), "type in your web browser:", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 363), "10.42.0.1", fill=(0, 0, 0), font=font_url, anchor="mm")

        # QR code for setup URL
        qr_img = make_qr("http://10.42.0.1", box_size=3, border=1)
        if qr_img:
            qr_size = min(qr_img.size[0], 100)
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            canvas.paste(qr_img, (cx - qr_size // 2, 390))
            qr_img.close()

        # Step 3
        draw.text((cx, 530), "Then pick your WiFi and", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 553), "enter the password.", fill=(0, 0, 0), font=font_body, anchor="mm")

        # Process for e-paper display
        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        canvas.close()
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        img.close()
        palette_ref.close()
        img_rgb = img_dithered.convert("RGB")
        img_dithered.close()
        final = img_rgb.rotate(config["rotation_angle"], expand=True)
        img_rgb.close()

        epd.init()
        epd.display(epd.getbuffer(final))
        epd.sleep()
        final.close()
        logger.info("Setup screen shown: connect to InkSlab-Setup WiFi")

    except Exception as e:
        logger.warning(f"Setup screen skipped: {e}")
        try:
            epd.sleep()
        except Exception:
            pass


def show_no_cards_screen(epd, config, ip=None):
    """Show a welcome screen when no cards are downloaded yet."""
    try:
        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
            font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            font_url = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            font_title = ImageFont.load_default()
            font_body = font_title
            font_url = font_title
            font_small = font_title

        cx = DISPLAY_WIDTH // 2

        draw.text((cx, 55), "InkSlab", fill=(0, 0, 0), font=font_title, anchor="mm")
        draw.text((cx, 115), "No cards downloaded yet.", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 160), "Scan or open in your", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 190), "web browser:", fill=(0, 0, 0), font=font_body, anchor="mm")

        if ip:
            url_text = f"http://{ip}"
            draw.text((cx, 235), url_text, fill=(0, 0, 0), font=font_url, anchor="mm")
            # QR code
            qr_img = make_qr(url_text)
            if qr_img:
                qr_size = min(qr_img.size[0], 130)
                qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
                canvas.paste(qr_img, (cx - qr_size // 2, 270))
                qr_img.close()

        draw.text((cx, 430), "Tap Downloads and pick", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 460), "a collection to download.", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 520), "Images will appear here", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 550), "once ready.", fill=(0, 0, 0), font=font_body, anchor="mm")

        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        canvas.close()
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        img.close()
        palette_ref.close()
        img_rgb = img_dithered.convert("RGB")
        img_dithered.close()
        final = img_rgb.rotate(config["rotation_angle"], expand=True)
        img_rgb.close()

        epd.init()
        epd.display(epd.getbuffer(final))
        epd.sleep()
        final.close()
        logger.info("No-cards welcome screen shown")

    except Exception as e:
        logger.warning(f"No-cards screen skipped: {e}")
        try:
            epd.sleep()
        except Exception:
            pass


def show_unbox_screen(epd, config):
    """Show a customer-facing 'Plug me in!' screen for shipping. E-ink retains this when powered off."""
    try:
        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
            font_action = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            font_title = ImageFont.load_default()
            font_action = font_title
            font_body = font_title
            font_small = font_title

        cx = DISPLAY_WIDTH // 2

        draw.text((cx, 80), "Welcome!", fill=(0, 0, 0), font=font_title, anchor="mm")
        draw.text((cx, 140), "to InkSlab", fill=(0, 0, 0), font=font_body, anchor="mm")

        draw.text((cx, 240), "Plug me in", fill=(0, 0, 0), font=font_action, anchor="mm")
        draw.text((cx, 280), "to get started!", fill=(0, 0, 0), font=font_action, anchor="mm")

        draw.text((cx, 370), "After plugging in, wait about", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 400), "90 seconds for this screen", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 430), "to update with setup instructions.", fill=(0, 0, 0), font=font_body, anchor="mm")

        draw.text((cx, 500), "Do not unplug during setup.", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 555), "Costa Mesa Tech Solutions", fill=(0, 0, 0), font=font_small, anchor="mm")

        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        canvas.close()
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        img.close()
        palette_ref.close()
        img_rgb = img_dithered.convert("RGB")
        img_dithered.close()
        final = img_rgb.rotate(config["rotation_angle"], expand=True)
        img_rgb.close()

        epd.init()
        epd.display(epd.getbuffer(final))
        epd.sleep()
        final.close()
        logger.info("Unbox/shipping screen shown")

    except Exception as e:
        logger.warning(f"Unbox screen skipped: {e}")
        try:
            epd.sleep()
        except Exception:
            pass


def get_card_metadata(img_path, master_index):
    """Extract set name, card number, and rarity from card image path."""
    info = {"set_info": "", "stats": "", "set_name": "", "card_num": "", "rarity": "", "number": ""}
    try:
        folder_path = os.path.dirname(img_path)
        filename = os.path.basename(img_path)
        set_id = os.path.basename(folder_path)
        card_id = os.path.splitext(filename)[0]

        # Set info (top line)
        if set_id in master_index:
            year = master_index[set_id].get("year", "")
            real_set = master_index[set_id]["name"].upper().replace(" AND ", " & ")
            if year:
                info["set_info"] = f"{year} {real_set}"
            else:
                info["set_info"] = real_set
            info["set_name"] = master_index[set_id]["name"]
        else:
            info["set_info"] = set_id.upper()
            info["set_name"] = set_id

        # Card stats (bottom line)
        num = "00"
        extra = ""

        json_path = os.path.join(folder_path, "_data.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                if card_id in data:
                    entry = data[card_id]
                    num = entry.get("number", "00")
                    if entry.get("rarity"):
                        extra = entry["rarity"].upper()
                        extra = extra.replace("RARE HOLO", "HOLO").replace("DOUBLE RARE", "DBL RARE")
            except Exception as e:
                logger.warning(f"Corrupt _data.json at {json_path}: {e}")

        # Try extracting number from card ID if not found in metadata
        if num == "00" and "-" in card_id:
            parts = card_id.split("-")
            if parts[-1].isdigit():
                num = parts[-1]

        info["card_num"] = f"#{num}"
        info["number"] = num
        info["rarity"] = extra

        # Format: "#201  •  HOLO" or just "#201"
        if extra:
            info["stats"] = f"#{num}  \u2022  {extra}"
        else:
            info["stats"] = f"#{num}"

    except Exception as e:
        logger.debug(f"Metadata error for {img_path}: {e}")
    return info


def create_slab_layout(img_path, master_index, header_mode="normal", image_fit="contain", image_bg="black"):
    """Create a PSA-slab-style layout with card info header above the card image.
    header_mode: 'normal' (white bg, black text), 'inverted' (black bg, white text), 'off' (full card)
    image_fit: 'contain' (letterbox), 'fill' (crop to fill), 'stretch'
    image_bg: 'black' or 'white' — letterbox fill color for contain mode"""
    info = get_card_metadata(img_path, master_index)
    bg_fill = (0, 0, 0) if image_bg == "black" else (255, 255, 255)

    with Image.open(img_path) as card_raw:
        card = card_raw.convert("RGB")

        if image_fit == "stretch":
            card_fitted = card.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
            card.close()
        elif image_fit == "fill":
            # Scale to cover, center-crop
            aspect = card.width / card.height
            display_aspect = DISPLAY_WIDTH / DISPLAY_HEIGHT
            if aspect > display_aspect:
                new_h = DISPLAY_HEIGHT
                new_w = int(new_h * aspect)
            else:
                new_w = DISPLAY_WIDTH
                new_h = int(new_w / aspect)
            card_resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)
            card.close()
            left = (new_w - DISPLAY_WIDTH) // 2
            top = (new_h - DISPLAY_HEIGHT) // 2
            card_fitted = card_resized.crop((left, top, left + DISPLAY_WIDTH, top + DISPLAY_HEIGHT))
            card_resized.close()
        else:  # contain (letterbox)
            scale = min(DISPLAY_WIDTH / card.width, DISPLAY_HEIGHT / card.height)
            new_w = int(card.width * scale)
            new_h = int(card.height * scale)
            card_resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)
            card.close()
            canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), bg_fill)
            x_pos = (DISPLAY_WIDTH - new_w) // 2
            y_pos = (DISPLAY_HEIGHT - new_h) // 2
            canvas.paste(card_resized, (x_pos, y_pos))
            card_resized.close()
            if header_mode == "off":
                return canvas, info
            card_fitted = canvas

        if header_mode == "off":
            canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), bg_fill)
            canvas.paste(card_fitted, (0, 0))
            card_fitted.close()
            return canvas, info

        # Normal or inverted: place card and draw header overlay
        bg_color = (0, 0, 0) if header_mode == "inverted" else (255, 255, 255)
        text_color = (255, 255, 255) if header_mode == "inverted" else (0, 0, 0)

        if image_fit == "contain":
            # card_fitted is already a full canvas — draw header on top
            canvas = card_fitted
            draw = ImageDraw.Draw(canvas)
            y_pos = (DISPLAY_HEIGHT - new_h) // 2  # top of the card in canvas
        else:
            canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), bg_color)
            draw = ImageDraw.Draw(canvas)
            canvas.paste(card_fitted, (0, 0))
            card_fitted.close()
            y_pos = 0  # card fills from top; overlay bar drawn at top

        # Draw header text in the space above the card
        if y_pos > 30:
            try:
                font_set = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
                font_stats = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            except IOError:
                font_set = ImageFont.load_default()
                font_stats = ImageFont.load_default()

            line1 = info["set_info"]
            line2 = info["stats"]

            # Measure text width
            w1 = draw.textbbox((0, 0), line1, font=font_set)[2]
            w2 = draw.textbbox((0, 0), line2, font=font_stats)[2]

            # Auto-shrink set name if it overflows
            if w1 > 380:
                try:
                    font_set = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
                    w1 = draw.textbbox((0, 0), line1, font=font_set)[2]
                except IOError:
                    pass

            # Center text vertically in header area
            h1, h2, gap = 14, 18, 4
            total_h = h1 + h2 + gap
            start_y = (y_pos - total_h) // 2

            draw.text(((DISPLAY_WIDTH - w1) / 2, start_y), line1, font=font_set, fill=text_color)
            draw.text(((DISPLAY_WIDTH - w2) / 2, start_y + h1 + gap), line2, font=font_stats, fill=text_color)

        # If no header space, draw overlay bar at top of image
        if y_pos <= 30:
            try:
                font_set = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
                font_stats = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            except IOError:
                font_set = ImageFont.load_default()
                font_stats = ImageFont.load_default()
            line1 = info["set_info"]
            line2 = info["stats"]
            bar_h = 48
            bar = Image.new("RGB", (DISPLAY_WIDTH, bar_h), bg_color)
            canvas.paste(bar, (0, 0))
            bar.close()
            w1 = draw.textbbox((0, 0), line1, font=font_set)[2]
            w2 = draw.textbbox((0, 0), line2, font=font_stats)[2]
            if w1 > 380:
                try:
                    font_set = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
                    w1 = draw.textbbox((0, 0), line1, font=font_set)[2]
                except IOError:
                    pass
            draw.text(((DISPLAY_WIDTH - w1) / 2, 4), line1, font=font_set, fill=text_color)
            draw.text(((DISPLAY_WIDTH - w2) / 2, 22), line2, font=font_stats, fill=text_color)
        return canvas, info


def create_palette_image():
    """Create a reference palette image for Floyd-Steinberg dithering (cached)."""
    return _PALETTE_IMAGE.copy()

# Pre-create the palette image once at module load
_PALETTE_IMAGE = Image.new('P', (1, 1))
_PALETTE_IMAGE.putpalette(PALETTE_COLORS + [0, 0, 0] * (256 - len(PALETTE_COLORS) // 3))


def process_image(img_path, master_index, config):
    """Full image pipeline: layout -> enhance -> dither -> rotate for display."""
    try:
        header_mode = config.get("slab_header_mode", "normal")
        image_fit = config.get("image_fit", "contain")
        image_bg = config.get("image_bg", "black")
        img, info = create_slab_layout(img_path, master_index, header_mode, image_fit, image_bg)

        # Boost colors for the e-paper display (each enhance creates a new image)
        img = ImageEnhance.Color(img).enhance(config["color_saturation"])
        img = ImageEnhance.Contrast(img).enhance(CONTRAST_BOOST)
        img = ImageEnhance.Sharpness(img).enhance(SHARPNESS_BOOST)

        # Quantize to 7-color palette with dithering
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        img.close()
        palette_ref.close()

        img_rgb = img_dithered.convert("RGB")
        img_dithered.close()
        final = img_rgb.rotate(config["rotation_angle"], expand=True)
        img_rgb.close()

        return final, info
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        return None, {}


class ShuffleDeck:
    """Manages a shuffled deck of all card image paths. Re-shuffles when exhausted."""

    def __init__(self, root_dir, collection=None, recent=None):
        self.root_dir = root_dir
        self.collection = collection
        self.deck = deque()
        self.total = 0
        self.history = list(recent) if recent else []
        self.reshuffle()

    def reshuffle(self):
        logger.info("Shuffling deck...")
        temp = []
        if os.path.isdir(self.root_dir):
            for set_dir in os.listdir(self.root_dir):
                set_path = os.path.join(self.root_dir, set_dir)
                if not os.path.isdir(set_path):
                    continue
                for f in os.listdir(set_path):
                    if _is_card_image(f):
                        # If collection mode, only include owned cards
                        if self.collection is not None:
                            card_id = os.path.splitext(f)[0]
                            if card_id not in self.collection:
                                continue
                        temp.append(os.path.join(set_path, f))

        if self.collection is not None and len(temp) == 0:
            logger.info("Collection mode: no matching cards on disk yet")

        # Smart shuffle: push recently-shown cards to the back of the deck
        # so you see fresh cards first after a reshuffle or deck rebuild
        if self.history:
            recent_set = set(self.history)
            not_recent = [c for c in temp if c not in recent_set]
            was_recent = [c for c in temp if c in recent_set]
            random.shuffle(not_recent)
            random.shuffle(was_recent)
            temp = not_recent + was_recent
        else:
            random.shuffle(temp)

        self.deck = deque(temp)
        self.total = len(temp)
        logger.info(f"Deck loaded: {self.total} cards")

    def draw(self):
        if not self.deck:
            self.reshuffle()
        if not self.deck:
            return None
        card = self.deck.popleft()
        self.history.insert(0, card)
        if len(self.history) > 30:
            self.history = self.history[:30]
        return card

    def peek(self, n=3):
        """Return the next n cards without removing them."""
        return list(self.deck)[:n]


def card_summary(card_path, master_index):
    """Extract minimal card info for the status file (used for prev/next queue)."""
    set_id = os.path.basename(os.path.dirname(card_path))
    card_id = os.path.splitext(os.path.basename(card_path))[0]
    info = get_card_metadata(card_path, master_index)
    return {
        "set_id": set_id,
        "card_id": card_id,
        "set_name": info.get("set_name", ""),
        "set_info": info.get("set_info", ""),
        "card_num": info.get("card_num", ""),
        "rarity": info.get("rarity", ""),
    }


def wait_with_polling(seconds, config_check_interval=5):
    """Sleep for `seconds`, checking triggers every 1s and config every 5s.

    While PAUSE_FILE exists, the countdown freezes (stays in loop indefinitely).
    Returns (config, action) where action is 'next', 'prev', 'tcg_changed', or None.
    """
    config = load_config()
    last_config_check = time.time()
    elapsed = 0

    while (elapsed < seconds or os.path.exists(PAUSE_FILE)) and not _shutdown:
        # Check for prev trigger
        if os.path.exists(PREV_TRIGGER):
            try:
                os.remove(PREV_TRIGGER)
            except OSError:
                pass
            logger.info("Previous card trigger detected")
            return load_config(), "prev"

        # Check for collection change trigger
        if os.path.exists(COLLECTION_TRIGGER):
            try:
                os.remove(COLLECTION_TRIGGER)
            except OSError:
                pass
            logger.info("Collection changed trigger detected")
            return load_config(), "collection_changed"

        # Check for skip/next trigger
        if os.path.exists(NEXT_TRIGGER):
            try:
                os.remove(NEXT_TRIGGER)
            except OSError:
                pass
            logger.info("Skip trigger detected — advancing to next card")
            return load_config(), "next"

        # Check for redraw trigger (re-render current card with new settings, no advance)
        if os.path.exists(REDRAW_TRIGGER):
            try:
                os.remove(REDRAW_TRIGGER)
            except OSError:
                pass
            logger.info("Redraw trigger detected — re-rendering current card")
            return load_config(), "redraw"

        # Check for WiFi state change triggers
        if os.path.exists(WIFI_CONNECTED_TRIGGER):
            try:
                os.remove(WIFI_CONNECTED_TRIGGER)
            except OSError:
                pass
            logger.info("WiFi connected trigger detected")
            return load_config(), "wifi_connected"

        if os.path.exists(WIFI_SETUP_TRIGGER):
            try:
                os.remove(WIFI_SETUP_TRIGGER)
            except OSError:
                pass
            logger.info("WiFi setup mode trigger detected")
            return load_config(), "wifi_setup"

        if os.path.exists(UNBOX_TRIGGER):
            try:
                os.remove(UNBOX_TRIGGER)
            except OSError:
                pass
            logger.info("Unbox screen trigger detected")
            return load_config(), "unbox"

        # Periodically re-read config
        if time.time() - last_config_check >= config_check_interval:
            new_config = load_config()
            if new_config["active_tcg"] != config["active_tcg"]:
                logger.info(f"TCG changed to {new_config['active_tcg']}")
                return new_config, "tcg_changed"
            config = new_config
            last_config_check = time.time()

        time.sleep(2)
        # Only count elapsed time when not paused
        if not os.path.exists(PAUSE_FILE):
            elapsed += 2

    return config, None


def main():
    logger.info("InkSlab starting...")

    # Write startup status immediately so web UI shows correct state
    write_status({
        "card_path": "", "set_name": "", "set_info": "",
        "card_num": "", "rarity": "",
        "timestamp": int(time.time()), "tcg": "",
        "total_cards": 0, "pending": "Starting up...",
    })

    config = load_config()
    active_tcg = config["active_tcg"]
    library_dir = TCG_LIBRARIES.get(active_tcg, TCG_LIBRARIES["pokemon"])
    master_index = load_master_index(library_dir)

    # Load collection if collection mode is on
    collection = None
    if config["collection_only"]:
        loaded = load_collection(active_tcg)
        collection = loaded if loaded is not None else set()
        logger.info(f"Collection mode: {len(collection)} owned cards")

    deck = ShuffleDeck(library_dir, collection)
    _deck_collection_only = config["collection_only"]

    # Initialize the e-paper display (retry up to 5 times with increasing delays)
    # Note: we skip Clear() here — the first screen (setup/splash/no-cards) will
    # overwrite the display anyway, saving one unnecessary e-ink refresh flash.
    epd = None
    for attempt in range(1, 6):
        try:
            epd = epd4in0e.EPD()
            epd.init()
            epd.sleep()
            logger.info("Display initialized successfully")
            break
        except Exception as e:
            logger.error(f"Display init attempt {attempt}/5 failed: {e}")
            if attempt < 5:
                delay = attempt * 10  # 10s, 20s, 30s, 40s
                logger.info(f"Retrying display init in {delay}s...")
                time.sleep(delay)
            else:
                logger.error("Display init failed after 5 attempts. Exiting.")
                return

    # Check WiFi status — show setup screen or splash screen
    try:
        wifi_connected = wifi_manager.is_wifi_connected()
    except Exception as e:
        logger.warning(f"WiFi check failed, assuming connected: {e}")
        wifi_connected = True

    # Waveshare ACeP minimum refresh interval: 180s between full updates.
    # IP/QR screen counts as one refresh — wait full 180s before first card.
    EINK_MIN_INTERVAL = 180  # seconds — Waveshare ACeP recommended minimum

    if wifi_connected:
        if deck.total > 0:
            show_splash_screen(epd, config)
            logger.info(f"IP/QR screen shown — waiting {EINK_MIN_INTERVAL}s before first card (Waveshare ACeP minimum)")
            for _ in range(EINK_MIN_INTERVAL // 5):
                time.sleep(5)
                if os.path.exists(NEXT_TRIGGER) or os.path.exists(PREV_TRIGGER):
                    break
        else:
            logger.info("WiFi connected but no cards — skipping splash, will show no-cards screen")

    else:
        # Not connected — show setup instructions and wait
        # (Covers both first boot AND failed previous connection attempts)
        show_setup_screen(epd, config)
        logger.info("No WiFi connection — showing setup screen, waiting...")
        wait_count = 0
        max_wait = 120  # Give up after 2 minutes and proceed anyway
        while wait_count < max_wait:
            if os.path.exists(WIFI_CONNECTED_TRIGGER):
                try:
                    os.remove(WIFI_CONNECTED_TRIGGER)
                except OSError:
                    pass
                break
            try:
                if wifi_manager.is_wifi_connected():
                    break
            except Exception:
                break  # WiFi check crashed — proceed anyway
            time.sleep(5)
            wait_count += 5
        # WiFi connected — skip splash if no cards (no-cards screen shows IP)
        if deck.total > 0:
            logger.info("WiFi wait complete, showing splash screen...")
            show_splash_screen(epd, config)
            time.sleep(EINK_MIN_INTERVAL)
        else:
            logger.info("WiFi connected but no cards — skipping splash")

    # Graceful shutdown: ensure display is put to sleep on exit
    global _shutdown

    def _handle_shutdown(signum, frame):
        global _shutdown
        _shutdown = True

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    def rebuild_deck(preserve_history=False):
        """Helper to rebuild the deck when TCG, collection mode, or collection content changes."""
        nonlocal active_tcg, library_dir, master_index, collection, deck, _deck_collection_only
        old_history = deck.history if preserve_history else []
        active_tcg = config["active_tcg"]
        _deck_collection_only = config["collection_only"]
        library_dir = TCG_LIBRARIES.get(active_tcg, TCG_LIBRARIES["pokemon"])
        master_index = load_master_index(library_dir)
        if config["collection_only"]:
            loaded = load_collection(active_tcg)
            collection = loaded if loaded is not None else set()
        else:
            collection = None
        deck = ShuffleDeck(library_dir, collection, recent=old_history)

    consecutive_failures = 0

    # Main loop: alternates between no-cards screen and card display
    # If cards are deleted mid-operation, falls back to no-cards screen
    try:
        while not _shutdown:

            # No cards available — show welcome screen and wait for downloads
            _no_cards_shown = False
            while deck.total == 0 and not _shutdown:
                if not _no_cards_shown:
                    show_no_cards_screen(epd, config, get_local_ip())
                    _no_cards_shown = True
                logger.warning(f"No cards found for {active_tcg}. Waiting for downloads...")
                err_msg = ("Collection mode is on but no cards are selected. Add cards from the Collection tab."
                           if config["collection_only"] else
                           "No cards downloaded yet. Use the Downloads tab to get started.")
                write_status({
                    "card_path": "", "set_name": "",
                    "set_info": "", "card_num": "", "rarity": "",
                    "timestamp": int(time.time()), "tcg": active_tcg,
                    "total_cards": 0, "error": err_msg,
                })
                config, action = wait_with_polling(60)

                # Handle WiFi state changes even while waiting for cards
                if action == "wifi_setup":
                    show_setup_screen(epd, config)
                    while not os.path.exists(WIFI_CONNECTED_TRIGGER) and not _shutdown:
                        try:
                            if wifi_manager.is_wifi_connected():
                                break
                        except Exception:
                            break
                        time.sleep(5)
                    try:
                        os.remove(WIFI_CONNECTED_TRIGGER)
                    except OSError:
                        pass
                    _no_cards_shown = False
                    continue

                if action == "unbox":
                    show_unbox_screen(epd, config)
                    continue

                if action == "wifi_connected":
                    # Skip splash — no-cards screen will re-show with the new IP
                    _no_cards_shown = False
                    continue

                new_tcg = config["active_tcg"]
                if (new_tcg != active_tcg
                        or config["collection_only"] != _deck_collection_only
                        or (action == "collection_changed" and config["collection_only"])):
                    rebuild_deck()
                    _no_cards_shown = False  # Show updated screen if TCG changed
                else:
                    deck.reshuffle()

            if _shutdown:
                break

            # Card display loop — runs until cards run out or shutdown
            while not _shutdown:
                card_path = deck.draw()
                if not card_path:
                    # No card drawn — deck may be empty after deletion
                    rebuild_deck()
                    if deck.total == 0:
                        break  # Back to no-cards loop
                    continue

                # Check if the card file still exists (user may have deleted cards)
                if not os.path.exists(card_path):
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        logger.info("Multiple missing card files — rebuilding deck")
                        rebuild_deck()
                        consecutive_failures = 0
                        if deck.total == 0:
                            break  # Back to no-cards loop
                    continue

                logger.info(f"Displaying: {os.path.basename(card_path)}")
                final_img, card_info = process_image(card_path, master_index, config)

                if not final_img:
                    consecutive_failures += 1
                    logger.warning(f"Skipping bad image ({consecutive_failures}): {card_path}")
                    if consecutive_failures >= 10:
                        logger.warning("Too many consecutive bad images. Rebuilding deck...")
                        rebuild_deck()
                        consecutive_failures = 0
                        if deck.total == 0:
                            break  # Back to no-cards loop
                        write_status({
                            "card_path": "", "set_name": "", "card_num": "", "rarity": "",
                            "set_info": "",
                            "timestamp": int(time.time()), "tcg": active_tcg,
                            "total_cards": deck.total,
                            "error": "Some card images may be corrupted. Try re-downloading from the Downloads tab.",
                        })
                        config, action = wait_with_polling(60)
                        if (config["active_tcg"] != active_tcg
                                or config["collection_only"] != _deck_collection_only
                                or (action == "collection_changed" and config["collection_only"])):
                            rebuild_deck()
                            if deck.total == 0:
                                break  # Back to no-cards loop
                    else:
                        time.sleep(2)
                    continue

                consecutive_failures = 0

                # Build prev/next card queue for the web dashboard
                prev_cards = []
                for p in deck.history[1:5]:
                    try:
                        prev_cards.append(card_summary(p, master_index))
                    except Exception:
                        pass
                next_cards = []
                for n in deck.peek(5):
                    try:
                        next_cards.append(card_summary(n, master_index))
                    except Exception:
                        pass

                # Calculate wait time and next change
                hr = time.localtime().tm_hour
                wait = config["day_interval"] if config["day_start"] <= hr < config["day_end"] else config["night_interval"]
                paused = os.path.exists(PAUSE_FILE)
                next_change = 0 if paused else int(time.time()) + wait

                # Write status BEFORE display refresh so web dashboard updates instantly
                cur_set_id = os.path.basename(os.path.dirname(card_path))
                cur_card_id = os.path.splitext(os.path.basename(card_path))[0]
                status_info = {
                    "card_path": card_path,
                    "set_id": cur_set_id,
                    "card_id": cur_card_id,
                    "set_name": card_info.get("set_name", ""),
                    "set_info": card_info.get("set_info", ""),
                    "card_num": card_info.get("card_num", ""),
                    "number": card_info.get("number", ""),
                    "rarity": card_info.get("rarity", ""),
                    "timestamp": int(time.time()),
                    "tcg": active_tcg,
                    "total_cards": deck.total,
                    "prev_cards": prev_cards,
                    "next_cards": next_cards,
                    "next_change": next_change,
                    "paused": paused,
                    "interval": wait,
                    "display_updating": True,
                }
                write_status(status_info)

                try:
                    epd.init()
                    epd.display(epd.getbuffer(final_img))
                except Exception as e:
                    logger.error(f"Display error: {e}")
                finally:
                    try:
                        epd.sleep()
                    except Exception:
                        pass

                # Display refresh complete — clear the updating flag, record when card went live
                status_info["display_updating"] = False
                status_info["display_start"] = int(time.time())
                write_status(status_info)

                logger.info(f"Next card in {wait // 60} minutes")
                final_img.close()

                # Poll during wait — picks up config changes, skip/prev triggers, and pause
                config, action = wait_with_polling(wait)

                if action == "prev":
                    if len(deck.history) > 1:
                        current = deck.history.pop(0)
                        previous = deck.history.pop(0)
                        deck.deck.insert(0, current)
                        deck.deck.insert(0, previous)
                    continue

                # WiFi connected — show splash screen with new IP, then resume cards
                if action == "wifi_connected":
                    logger.info("WiFi connected — resuming cards")
                    remaining = max(0, next_change - int(time.time())) if next_change else 0
                    if remaining > 0:
                        config, action = wait_with_polling(remaining)
                    continue

                # WiFi setup mode — show setup instructions on display
                if action == "wifi_setup":
                    logger.info("WiFi setup mode — showing setup screen")
                    show_setup_screen(epd, config)
                    while not _shutdown:
                        if os.path.exists(WIFI_CONNECTED_TRIGGER):
                            try:
                                os.remove(WIFI_CONNECTED_TRIGGER)
                            except OSError:
                                pass
                            break
                        try:
                            if wifi_manager.is_wifi_connected():
                                break
                        except Exception:
                            break
                        time.sleep(5)
                    show_splash_screen(epd, config)
                    time.sleep(EINK_MIN_INTERVAL)
                    continue

                if action == "unbox":
                    show_unbox_screen(epd, config)
                    continue

                # Re-render current card with new settings (e.g. saturation change), no advance
                if action == "redraw":
                    if deck.history:
                        current = deck.history.pop(0)
                        deck.deck.insert(0, current)
                    continue

                # Collection content changed — rebuild deck but keep showing current card
                if action == "collection_changed" and config["collection_only"]:
                    # Loop to handle rapid successive collection changes without cycling the card
                    while action == "collection_changed":
                        rebuild_deck(preserve_history=True)
                        if deck.total == 0:
                            break  # handled below
                        new_next = []
                        for nc in deck.peek(5):
                            try:
                                new_next.append(card_summary(nc, master_index))
                            except Exception:
                                pass
                        new_prev = []
                        for pc in deck.history[:4]:
                            try:
                                new_prev.append(card_summary(pc, master_index))
                            except Exception:
                                pass
                        paused = os.path.exists(PAUSE_FILE)
                        remaining = max(0, next_change - int(time.time())) if next_change else 0
                        write_status({
                            "card_path": card_path,
                            "set_name": card_info.get("set_name", ""),
                            "set_info": card_info.get("set_info", ""),
                            "card_num": card_info.get("card_num", ""),
                            "number": card_info.get("number", ""),
                            "rarity": card_info.get("rarity", ""),
                            "timestamp": int(time.time()),
                            "tcg": active_tcg,
                            "total_cards": deck.total,
                            "prev_cards": new_prev,
                            "next_cards": new_next,
                            "next_change": next_change,
                            "paused": paused,
                            "interval": wait,
                            "display_start": status_info.get("display_start", 0),
                        })
                        logger.info(f"Collection updated — deck rebuilt ({deck.total} cards), queue refreshed")
                        if remaining <= 0:
                            break  # natural advance time reached
                        config, action = wait_with_polling(remaining)
                    if deck.total == 0:
                        break  # Back to no-cards loop
                    if action == "prev":
                        if len(deck.history) > 1:
                            current = deck.history.pop(0)
                            previous = deck.history.pop(0)
                            deck.deck.insert(0, current)
                            deck.deck.insert(0, previous)
                        continue

                # If TCG or collection mode changed, rebuild and advance to new card
                new_tcg = config["active_tcg"]
                needs_rebuild = (new_tcg != active_tcg
                                 or config["collection_only"] != _deck_collection_only)
                if needs_rebuild:
                    rebuild_deck(preserve_history=(new_tcg == active_tcg))
                    if deck.total == 0:
                        break  # Back to no-cards loop

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Always clean up the display on exit
        logger.info("Cleaning up display...")
        try:
            epd.sleep()
        except Exception:
            pass
        try:
            epd.Dev_exit()
        except Exception:
            pass
        logger.info("InkSlab stopped.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"InkSlab crashed: {e}", exc_info=True)
        sys.exit(1)
