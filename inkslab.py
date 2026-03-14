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
}

# --- DYNAMIC TCG REGISTRY ---
TCG_REGISTRY = {
    "pokemon": {"name": "Pokemon", "path": "/home/pi/pokemon_cards", "color": "#36A5CA", "download_script": "download_cards_pokemon.py"},
    "mtg":     {"name": "Magic: The Gathering", "path": "/home/pi/mtg_cards", "color": "#6BCCBD", "download_script": "download_cards_mtg.py"},
    "lorcana": {"name": "Disney Lorcana", "path": "/home/pi/lorcana_cards", "color": "#C084FC", "download_script": "download_cards_lorcana.py"},
    "custom":  {"name": "Custom", "path": "/home/pi/custom_cards", "color": "#F59E0B", "download_script": None},
}
TCG_LIBRARIES = {k: v["path"] for k, v in TCG_REGISTRY.items()}

# Supported image formats
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')

CONFIG_FILE = "/home/pi/inkslab_config.json"
COLLECTION_FILE = "/home/pi/inkslab_collection.json"
STATUS_FILE = "/tmp/inkslab_status.json"
NEXT_TRIGGER = "/tmp/inkslab_next"
PREV_TRIGGER = "/tmp/inkslab_prev"
PAUSE_FILE = "/tmp/inkslab_pause"
COLLECTION_TRIGGER = "/tmp/inkslab_collection_changed"

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

from waveshare_epd import epd4in0e


def load_config():
    """Load config from file, falling back to defaults for missing keys."""
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                saved = json.load(f)
            config.update(saved)
        except Exception as e:
            logger.warning(f"Error reading config: {e}, using defaults")
    return config


def load_collection(tcg):
    """Load the collection list for a given TCG. Returns a set of card IDs."""
    if os.path.exists(COLLECTION_FILE):
        try:
            with open(COLLECTION_FILE, 'r') as f:
                data = json.load(f)
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
    """Write current display status for the web dashboard."""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(info, f)
    except Exception:
        pass


def _is_card_image(filename):
    """Check if a file is a supported card image."""
    return filename.lower().endswith(IMAGE_EXTENSIONS) and not filename.startswith('_')


def get_local_ip():
    """Get the Pi's local IP address."""
    try:
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        parts = result.stdout.strip().split()
        return parts[0] if parts else None
    except Exception:
        return None


def show_splash_screen(epd, config):
    """Show a branded splash screen with the dashboard URL on the e-ink display."""
    try:
        ip = get_local_ip()
        if not ip:
            logger.info("No IP address available yet, skipping splash screen")
            return

        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Load fonts
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_url = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            font_title = ImageFont.load_default()
            font_url = font_title
            font_sub = font_title

        # Draw content centered
        cx = DISPLAY_WIDTH // 2

        # Title
        draw.text((cx, 180), "InkSlab", fill=(0, 0, 0), font=font_title, anchor="mm")

        # Dashboard URL (prominent)
        url_text = f"http://{ip}"
        draw.text((cx, 260), "Dashboard:", fill=(0, 0, 0), font=font_sub, anchor="mm")
        draw.text((cx, 290), url_text, fill=(0, 0, 255), font=font_url, anchor="mm")

        # Subtitle
        draw.text((cx, 350), "Open this address in your browser", fill=(0, 0, 0), font=font_sub, anchor="mm")
        draw.text((cx, 375), "to control your display.", fill=(0, 0, 0), font=font_sub, anchor="mm")

        # Bottom credit
        draw.text((cx, 540), "Costa Mesa Tech Solutions", fill=(0, 0, 0), font=font_sub, anchor="mm")

        # Process for e-paper display
        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        final = img_dithered.convert("RGB").rotate(config["rotation_angle"], expand=True)

        epd.display(epd.getbuffer(final))
        logger.info(f"Splash screen shown: dashboard at {url_text}")

    except Exception as e:
        logger.warning(f"Splash screen skipped: {e}")


def show_setup_screen(epd, config):
    """Show WiFi setup instructions on the e-ink display when no WiFi is configured."""
    try:
        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Load fonts
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
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
        draw.text((cx, 80), "InkSlab", fill=(0, 0, 0), font=font_title, anchor="mm")
        draw.text((cx, 110), "WiFi Setup", fill=(0, 0, 255), font=font_heading, anchor="mm")

        # Step 1
        draw.text((cx, 175), "1. Connect to WiFi:", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 205), "InkSlab-Setup", fill=(255, 0, 0), font=font_url, anchor="mm")

        # Step 2
        draw.text((cx, 275), "2. Open in browser:", fill=(0, 0, 0), font=font_body, anchor="mm")
        draw.text((cx, 305), "10.42.0.1", fill=(0, 0, 255), font=font_url, anchor="mm")

        # Hint
        draw.text((cx, 380), "A setup page should appear", fill=(0, 0, 0), font=font_small, anchor="mm")
        draw.text((cx, 400), "automatically on most phones.", fill=(0, 0, 0), font=font_small, anchor="mm")

        # Bottom credit
        draw.text((cx, 540), "Costa Mesa Tech Solutions", fill=(0, 0, 0), font=font_small, anchor="mm")

        # Process for e-paper display
        img = ImageEnhance.Contrast(canvas).enhance(CONTRAST_BOOST)
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)
        final = img_dithered.convert("RGB").rotate(config["rotation_angle"], expand=True)

        epd.display(epd.getbuffer(final))
        logger.info("Setup screen shown: connect to InkSlab-Setup WiFi")

    except Exception as e:
        logger.warning(f"Setup screen skipped: {e}")


def get_card_metadata(img_path, master_index):
    """Extract set name, card number, and rarity from card image path."""
    info = {"set_info": "", "stats": "", "set_name": "", "card_num": "", "rarity": ""}
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
            with open(json_path, "r") as f:
                data = json.load(f)
                if card_id in data:
                    entry = data[card_id]
                    num = entry.get("number", "00")

                    if entry.get("rarity"):
                        extra = entry["rarity"].upper()
                        extra = extra.replace("RARE HOLO", "HOLO").replace("DOUBLE RARE", "DBL RARE")
        else:
            # Auto-generate metadata from filename (for custom images)
            name = card_id.replace('_', ' ').replace('-', ' ').title()
            # No number or rarity to extract

        # Try extracting number from card ID if not found in metadata
        if num == "00" and "-" in card_id:
            parts = card_id.split("-")
            if parts[-1].isdigit():
                num = parts[-1]

        info["card_num"] = f"#{num}"
        info["rarity"] = extra

        # Format: "#201  •  HOLO" or just "#201"
        if extra:
            info["stats"] = f"#{num}  \u2022  {extra}"
        else:
            info["stats"] = f"#{num}"

    except Exception as e:
        logger.debug(f"Metadata error for {img_path}: {e}")
    return info


def create_slab_layout(img_path, master_index, header_mode="normal"):
    """Create a PSA-slab-style layout with card info header above the card image.
    header_mode: 'normal' (white bg, black text), 'inverted' (black bg, white text), 'off' (full card)"""
    info = get_card_metadata(img_path, master_index)

    with Image.open(img_path) as card:
        card = card.convert("RGB")

        if header_mode == "off":
            # Full-screen: center-crop card to fill entire display
            aspect = card.width / card.height
            display_aspect = DISPLAY_WIDTH / DISPLAY_HEIGHT
            if aspect > display_aspect:
                # Card is wider — fit height, crop width
                new_h = DISPLAY_HEIGHT
                new_w = int(new_h * aspect)
            else:
                # Card is taller — fit width, crop height
                new_w = DISPLAY_WIDTH
                new_h = int(new_w / aspect)
            card = card.resize((new_w, new_h), Image.Resampling.LANCZOS)
            # Center crop
            left = (new_w - DISPLAY_WIDTH) // 2
            top = (new_h - DISPLAY_HEIGHT) // 2
            card = card.crop((left, top, left + DISPLAY_WIDTH, top + DISPLAY_HEIGHT))
            canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
            canvas.paste(card, (0, 0))
            return canvas, info

        # Normal or inverted: scale card to fill display width
        aspect = card.height / card.width
        new_h = int(DISPLAY_WIDTH * aspect)
        card = card.resize((DISPLAY_WIDTH, new_h), Image.Resampling.LANCZOS)

        # Background color depends on mode
        bg_color = (0, 0, 0) if header_mode == "inverted" else (255, 255, 255)
        text_color = (255, 255, 255) if header_mode == "inverted" else (0, 0, 0)

        canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), bg_color)
        draw = ImageDraw.Draw(canvas)

        # Position card flush to bottom
        y_pos = DISPLAY_HEIGHT - new_h
        canvas.paste(card, (0, y_pos))

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

        return canvas, info


def create_palette_image():
    """Create a reference palette image for Floyd-Steinberg dithering."""
    p_img = Image.new('P', (1, 1))
    full_palette = PALETTE_COLORS + [0, 0, 0] * (256 - len(PALETTE_COLORS) // 3)
    p_img.putpalette(full_palette)
    return p_img


def process_image(img_path, master_index, config):
    """Full image pipeline: layout -> enhance -> dither -> rotate for display."""
    try:
        header_mode = config.get("slab_header_mode", "normal")
        img, info = create_slab_layout(img_path, master_index, header_mode)

        # Boost colors for the e-paper display
        img = ImageEnhance.Color(img).enhance(config["color_saturation"])
        img = ImageEnhance.Contrast(img).enhance(CONTRAST_BOOST)
        img = ImageEnhance.Sharpness(img).enhance(SHARPNESS_BOOST)

        # Quantize to 7-color palette with dithering
        palette_ref = create_palette_image()
        img_dithered = img.quantize(palette=palette_ref, dither=Image.Dither.FLOYDSTEINBERG)

        return img_dithered.convert("RGB").rotate(config["rotation_angle"], expand=True), info
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        return None, {}


class ShuffleDeck:
    """Manages a shuffled deck of all card image paths. Re-shuffles when exhausted."""

    def __init__(self, root_dir, collection=None, recent=None):
        self.root_dir = root_dir
        self.collection = collection
        self.deck = []
        self.total = 0
        self.history = list(recent) if recent else []
        self.reshuffle()

    def reshuffle(self):
        logger.info("Shuffling deck...")
        temp = []
        if os.path.isdir(self.root_dir):
            for root, dirs, files in os.walk(self.root_dir):
                for f in files:
                    if _is_card_image(f):
                        # If collection mode, only include owned cards
                        if self.collection is not None:
                            card_id = os.path.splitext(f)[0]
                            if card_id not in self.collection:
                                continue
                        temp.append(os.path.join(root, f))

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

        self.deck = temp
        self.total = len(temp)
        logger.info(f"Deck loaded: {self.total} cards")

    def draw(self):
        if not self.deck:
            self.reshuffle()
        if not self.deck:
            return None
        card = self.deck.pop(0)
        self.history.insert(0, card)
        if len(self.history) > 30:
            self.history = self.history[:30]
        return card

    def peek(self, n=3):
        """Return the next n cards without removing them."""
        return self.deck[:n]


def card_summary(card_path, master_index):
    """Extract minimal card info for the status file (used for prev/next queue)."""
    set_id = os.path.basename(os.path.dirname(card_path))
    card_id = os.path.splitext(os.path.basename(card_path))[0]
    info = get_card_metadata(card_path, master_index)
    return {
        "set_id": set_id,
        "card_id": card_id,
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

    while elapsed < seconds or os.path.exists(PAUSE_FILE):
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

        # Periodically re-read config
        if time.time() - last_config_check >= config_check_interval:
            new_config = load_config()
            if new_config["active_tcg"] != config["active_tcg"]:
                logger.info(f"TCG changed to {new_config['active_tcg']}")
                return new_config, "tcg_changed"
            config = new_config
            last_config_check = time.time()

        time.sleep(1)
        # Only count elapsed time when not paused
        if not os.path.exists(PAUSE_FILE):
            elapsed += 1

    return config, None


def main():
    logger.info("InkSlab starting...")

    config = load_config()
    active_tcg = config["active_tcg"]
    library_dir = TCG_LIBRARIES.get(active_tcg, TCG_LIBRARIES["pokemon"])
    master_index = load_master_index(library_dir)

    # Load collection if collection mode is on
    collection = None
    if config["collection_only"]:
        loaded = load_collection(active_tcg)
        collection = loaded if loaded else []
        logger.info(f"Collection mode: {len(collection)} owned cards")

    deck = ShuffleDeck(library_dir, collection)
    _deck_collection_only = config["collection_only"]

    # If no cards available, wait and poll for config changes or new downloads
    while deck.total == 0:
        logger.warning(f"No cards found for {active_tcg} in {library_dir}. "
                       f"Waiting for cards to be downloaded or TCG to be changed...")
        err_msg = (f"Collection mode is on but no cards selected. Add cards from the Collection tab."
                   if config["collection_only"] else
                   f"No {active_tcg.upper()} cards found. Download cards from the web dashboard.")
        write_status({
            "card_path": "",
            "set_name": "",
            "set_info": f"No {active_tcg.upper()} cards available",
            "card_num": "",
            "rarity": "",
            "timestamp": int(time.time()),
            "tcg": active_tcg,
            "total_cards": 0,
            "error": err_msg,
        })
        config, action = wait_with_polling(60)
        new_tcg = config["active_tcg"]
        if (new_tcg != active_tcg
                or config["collection_only"] != _deck_collection_only
                or action == "collection_changed"):
            active_tcg = new_tcg
            _deck_collection_only = config["collection_only"]
            library_dir = TCG_LIBRARIES.get(active_tcg, TCG_LIBRARIES["pokemon"])
            master_index = load_master_index(library_dir)
            if config["collection_only"]:
                loaded = load_collection(active_tcg)
                collection = loaded if loaded else []
            else:
                collection = None
            deck = ShuffleDeck(library_dir, collection)
        else:
            # Same TCG — reshuffle in case cards were just downloaded
            deck.reshuffle()

    try:
        epd = epd4in0e.EPD()
        epd.init()
        epd.Clear()
        logger.info("Display initialized and cleared")
    except Exception as e:
        logger.error(f"Display init failed: {e}")
        return

    # Check WiFi status — show setup screen or splash screen
    if wifi_manager.is_wifi_connected():
        # Normal boot: show dashboard IP
        show_splash_screen(epd, config)
    else:
        # No WiFi: show setup instructions and wait for connection
        show_setup_screen(epd, config)
        logger.info("Waiting for WiFi connection via setup mode...")
        wifi_connected = False
        while not wifi_connected:
            # Check for the trigger file from the web dashboard
            trigger = "/tmp/inkslab_wifi_connected"
            if os.path.exists(trigger):
                try:
                    os.remove(trigger)
                except OSError:
                    pass
                wifi_connected = True
                break
            # Also check nmcli directly
            if wifi_manager.is_wifi_connected():
                wifi_connected = True
                break
            time.sleep(5)
        # WiFi is now connected — show the splash screen with the new IP
        logger.info("WiFi connected! Showing dashboard IP...")
        show_splash_screen(epd, config)

    # Graceful shutdown: ensure display is put to sleep on exit
    _shutdown = False

    def _handle_shutdown(signum, frame):
        nonlocal _shutdown
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
            collection = loaded if loaded else []  # empty list = 0 cards, not fallback to all
        else:
            collection = None  # None = show all cards
        deck = ShuffleDeck(library_dir, collection, recent=old_history)

    consecutive_failures = 0

    try:
        while not _shutdown:
            card_path = deck.draw()
            if not card_path:
                logger.warning(f"No cards available for {active_tcg}. Checking for changes...")
                err_msg = (f"Collection mode is on but no cards selected. Add cards from the Collection tab."
                           if config["collection_only"] else
                           f"No {active_tcg.upper()} cards found. Download cards or switch TCG.")
                write_status({
                    "card_path": "", "set_name": "", "card_num": "", "rarity": "",
                    "set_info": f"No {active_tcg.upper()} cards available",
                    "timestamp": int(time.time()), "tcg": active_tcg, "total_cards": 0,
                    "error": err_msg,
                })
                config, action = wait_with_polling(60)
                if (config["active_tcg"] != active_tcg
                        or config["collection_only"] != _deck_collection_only
                        or action == "collection_changed"):
                    rebuild_deck()
                else:
                    deck.reshuffle()
                continue

            logger.info(f"Displaying: {os.path.basename(card_path)}")
            final_img, card_info = process_image(card_path, master_index, config)

            if not final_img:
                consecutive_failures += 1
                logger.warning(f"Skipping bad image ({consecutive_failures}): {card_path}")
                if consecutive_failures >= 10:
                    logger.warning("Too many consecutive bad images. Waiting 60s...")
                    write_status({
                        "card_path": "", "set_name": "", "card_num": "", "rarity": "",
                        "set_info": f"Too many bad images in {active_tcg.upper()}",
                        "timestamp": int(time.time()), "tcg": active_tcg,
                        "total_cards": deck.total,
                        "error": f"Many corrupt images found. Try re-downloading {active_tcg.upper()} cards.",
                    })
                    config, action = wait_with_polling(60)
                    consecutive_failures = 0
                    if (config["active_tcg"] != active_tcg
                            or config["collection_only"] != _deck_collection_only
                            or action == "collection_changed"):
                        rebuild_deck()
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
            status_info = {
                "card_path": card_path,
                "set_name": card_info.get("set_name", ""),
                "set_info": card_info.get("set_info", ""),
                "card_num": card_info.get("card_num", ""),
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

            # Display refresh complete — clear the updating flag
            status_info["display_updating"] = False
            write_status(status_info)

            logger.info(f"Next card in {wait // 60} minutes")
            del final_img

            # Poll during wait — picks up config changes, skip/prev triggers, and pause
            config, action = wait_with_polling(wait)

            if action == "prev":
                # Go back: put current card back in deck, put previous at front
                if len(deck.history) > 1:
                    current = deck.history.pop(0)
                    previous = deck.history.pop(0)
                    deck.deck.insert(0, current)
                    deck.deck.insert(0, previous)
                continue

            # Collection content changed — rebuild deck but keep showing current card
            if action == "collection_changed" and config["collection_only"]:
                rebuild_deck(preserve_history=True)
                # Update status with new queue immediately (no card advance)
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
                remaining = max(0, next_change - int(time.time())) if next_change else wait
                write_status({
                    "card_path": card_path,
                    "set_name": card_info.get("set_name", ""),
                    "set_info": card_info.get("set_info", ""),
                    "card_num": card_info.get("card_num", ""),
                    "rarity": card_info.get("rarity", ""),
                    "timestamp": int(time.time()),
                    "tcg": active_tcg,
                    "total_cards": deck.total,
                    "prev_cards": new_prev,
                    "next_cards": new_next,
                    "next_change": next_change,
                    "paused": paused,
                    "interval": wait,
                })
                logger.info(f"Collection updated — deck rebuilt ({deck.total} cards), queue refreshed")
                # Go back to waiting, don't advance card
                config, action = wait_with_polling(remaining)
                # Handle whatever woke us from the resumed wait
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
                             or config["collection_only"] != _deck_collection_only
                             or action == "collection_changed")
            if needs_rebuild:
                rebuild_deck(preserve_history=(new_tcg == active_tcg))
                if deck.total == 0:
                    logger.warning(f"No cards found for {active_tcg}. Will retry.")

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
    main()
