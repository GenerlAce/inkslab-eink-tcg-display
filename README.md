# InkSlab — e-Ink TCG Card Display

![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Display](https://img.shields.io/badge/display-Waveshare%204%22%20Spectra%206-green)

**InkSlab** is a Raspberry Pi Zero 2 W project that displays your TCG card collection on a 7-color e-ink screen, rotating through cards on a configurable schedule. A full web dashboard lets you browse your collection, manage downloads, and control the display from any device on your network — no app required.

Supports **Pokémon**, **Magic: The Gathering**, **Disney Lorcana**, **Manga covers**, **Comics covers**, and **custom images**.

> **Forked from** [costamesatechsolutions/inkslab-eink-tcg-display](https://github.com/costamesatechsolutions/inkslab-eink-tcg-display) — significantly extended with a full UI redesign, security hardening, and new features.

---

<p align="center">
  <img src="https://github.com/user-attachments/assets/46a55bb4-11ae-4b68-ab9b-53ce9e76e3d2" alt="InkSlab e-ink display showing a card in graded slab layout" width="600"/>
  <br/>
  <em>InkSlab running on a Waveshare 4" Spectra 6 — 7-color e-ink display</em>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/1320e2fe-e625-4ec2-b95c-909ccfdf07a4" alt="InkSlab desktop dashboard" width="100%"/>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/f1ad18b3-6ee8-4423-916d-763a30ed8475" alt="InkSlab mobile dashboard" width="100%"/>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/560cbaf3-73e3-4a56-8c7a-e98599a34923" alt="InkSlab themes" width="100%"/>
</p>

---

## Features

### Web Dashboard
- Responsive layout: desktop sidebar + mobile bottom tab bar
- Display tab with live card preview, Up Next queue (5 cards), and Previous cards panel (5 cards)
- Collection tab with grid and list views, thumbnails, and hover/tap preview
- Downloads tab with per-source selector and progress log
- Settings tab with display config, auto-update, PIN protection, and WiFi management

### Display
- 7-color e-ink (Spectra 6: black, white, green, blue, red, yellow, orange)
- Slab header with set name, year, card number, and rarity — three modes: Normal, Inverted, Off
- Full-bleed overlay headers for manga/comics
- Color saturation boost and dithering (Floyd-Steinberg)
- Smart shuffle — recently shown cards pushed to back of queue
- Day/night intervals with configurable hours

### Collection Management
- **All Cards / Owned Only** — segmented control; Owned Only shows only cards you've marked as owned in the collection
- Grid view with thumbnails; List view with hover preview and mobile accordion
- Quick Switch Collection — change active TCG instantly with a pending-queue notification on other clients
- Search by card name and add all printings at once
- Per-series delete with two-step confirmation
- Favorites list per TCG

### Downloads
- Unified collection selector — one interface for all sources
- Per-set search and download for all TCGs
- Pokémon bulk download by name (e.g., search "Charizard" → download all prints)
- MTG set search via Scryfall API
- Manga series search via MangaDex (no account required)
- Comics series search via Metron API (free account required)
- Download status log with timestamps and color-coded output (blue = Done, red = failures)
- Storage breakdown by library + free space gauge

### Settings
- Display interval, rotation, saturation, image fit and background
- Auto-update scheduler (weekly, per source, configurable day)
- Metron Comics account (credentials encrypted with device-specific key)
- PIN protection — 4–8 digit PIN, PBKDF2-SHA256, rate-limited login
- Admin mode — PIN re-authentication gate, 60-second auto-close
- OTA updates — check and install from GitHub directly from the dashboard
- WiFi setup and management
- System info panel (CPU temperature, RAM, uptime, IP address)
- Factory reset for clean handoff for a new owner

### Custom Images
- Upload PNG or JPG files organized into named folders
- Editable card name, number, rarity, and set metadata
- Treated as a first-class collection alongside TCGs

### Infrastructure
- Automated installer (`install.sh`)
- Self-healing on boot (`selfheal.sh`) — verifies files, resets from git on corruption
- OTA update with rollback safety (`ota_update.sh`)
- Hardware watchdog and journal size cap
- Atomic JSON writes (temp file + `os.rename`) throughout
- Non-blocking thumbnail generation (background thread)
- Captive portal for WiFi setup on first boot

---

## Hardware

| Part | Notes |
|------|-------|
| **Raspberry Pi Zero 2 W** | Required. Pi Zero W H also works but is noticeably slower |
| **Waveshare 4" e-Paper HAT+ (E) — Spectra 6** | 400×600, 7-color. Must be this exact model |
| **MicroSD card** | 8 GB minimum. 32–64 GB recommended for full TCG libraries |
| **5V micro USB power supply** | Standard Pi power supply |
| **90-degree micro USB cable** | Optional but recommended — hides the cable behind the frame |
| **3D printed frame** | [InkSlab on MakerWorld](https://makerworld.com/en/models/2452200-inkslab-open-source-e-ink-tcg-display) |

**Storage estimates by library:**
- Pokémon: ~15–20 GB (all sets)
- MTG: ~15–20 GB (all sets)
- Lorcana: ~2–4 GB
- Manga / Comics: varies by series

---

## Setup — DIY Flash

### 1. Flash Raspberry Pi OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite (64-bit)** to your SD card. In the imager's advanced settings, configure your hostname, SSH, and optionally your WiFi credentials.

### 2. Enable SPI

SSH into your Pi and run:
```bash
sudo raspi-config
```
Navigate to **Interface Options → SPI → Enable**. The install script will also check and enable SPI automatically.

### 3. Run the Installer

```bash
cd /home/pi
git clone https://github.com/GenerlAce/inkslab-eink-tcg-display.git inkslab
cd inkslab
chmod +x scripts/install.sh
bash scripts/install.sh
```

The installer will:
- Check and enable SPI (prompts reboot if needed)
- Install all system and Python dependencies
- Install and start both systemd services
- Verify the services are running

### 4. Install Dependencies Manually (if needed)

```bash
# System packages
sudo apt update
sudo apt install -y python3-pip python3-pil python3-spidev \
  python3-gpiozero python3-requests python3-flask python3-qrcode \
  python3-cryptography git gpiod libgpiod-dev

# Python packages
pip3 install waitress --break-system-packages
pip3 install cryptography --break-system-packages
```

### 5. First Boot

Power on the Pi with the display attached. Within 30–60 seconds:
- The display shows the InkSlab setup screen with the local IP address
- Open `http://<your-pi-ip>` in a browser
- If no cards are downloaded yet, the display shows a placeholder

The Waveshare driver is bundled in `lib/waveshare_epd/` — no additional library installation is needed.

---

## Starting and Managing Services

```bash
# Start
sudo systemctl start inkslab inkslab_web

# Stop
sudo systemctl stop inkslab inkslab_web

# Restart
sudo systemctl restart inkslab inkslab_web

# Enable on boot
sudo systemctl enable inkslab inkslab_web

# View logs
sudo journalctl -u inkslab -f
sudo journalctl -u inkslab_web -f
```

### selfheal.sh

`selfheal.sh` runs automatically before the display daemon starts (via `ExecStartPre=` in the service file). It:
- Syntax-checks all Python files
- Resets corrupted files from git if needed (with rollback on failure)
- Removes stale lock/temp files from crashed sessions
- Enables the hardware watchdog (auto-reboots if the daemon hangs for 10+ minutes)
- Caps the systemd journal at 50 MB to protect the SD card

---

## File Reference

### Static Files (`static/`)

| File | Purpose |
|------|---------|
| `app.js` | Main dashboard JS — display tab, polling, auth overlay, collection browser, downloads, settings, state management |
| `style.css` | Full dashboard stylesheet — dark theme, responsive layout, sidebar, modals, cards, animations |
| `collection_view.js` | Grid/list view toggle, thumbnail lazy loading, checkbox state, badge updates |
| `collection_list_preview.js` | Series list with set preview on hover |
| `dl_picker.js` | Downloads tab pill selector — TCG switching, action buttons |
| `mobile_qs.js` | Quick Switch Collection bottom sheet for mobile |
| `mtg_sets.js` | MTG set search UI (Scryfall), download button per result |
| `pokemon_bulk.js` | Pokémon bulk download by name — search and download all prints |
| `qs_pending.js` | Pending collection switch banner with cross-client sync |
| `modal_helpers.js` | Reusable modal objects — generic confirm, prompt, and card metadata editor |
| `apple-touch-icon.png` | iOS bookmark/home screen icon |
| `inkslab_qr_bg.png` | Background image for QR code screens |

### Scripts (`scripts/`)

| File | Purpose | When to Run |
|------|---------|-------------|
| `install.sh` | Full automated installer — SPI, packages, services | Once, on fresh Pi |
| `selfheal.sh` | Pre-boot health check and auto-repair | Automatically via systemd |
| `ota_update.sh` | Over-the-air update with rollback safety | Via dashboard or manually |
| `download_cards_pokemon.py` | Download Pokémon card images (PokemonTCG GitHub) | Via dashboard Downloads tab |
| `download_pokemon_bulk.py` | Bulk download Pokémon cards by name | Via dashboard Downloads tab |
| `download_cards_mtg.py` | Download MTG card images (Scryfall API) | Via dashboard Downloads tab |
| `download_cards_lorcana.py` | Download Lorcana card images (Lorcast API) | Via dashboard Downloads tab |
| `download_covers_manga.py` | Download manga volume covers (MangaDex API) | Via dashboard Downloads tab |
| `download_manga_series.py` | Search and download a specific manga series | Via dashboard Downloads tab |
| `download_covers_comics.py` | Download comic cover images (Metron API) | Via dashboard Downloads tab |
| `download_comic_series.py` | Search and download a specific comics series | Via dashboard Downloads tab |
| `download_utils.py` | Shared utilities — disk space check, file download helper | Internal (imported by other scripts) |

---

## Configuration

All settings are stored in `/home/pi/.inkslab/inkslab_config.json` and managed through the Settings tab. You can also edit the file directly while the services are stopped.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `active_tcg` | string | `"pokemon"` | Active library: `pokemon`, `mtg`, `lorcana`, `manga`, `comics`, `custom` |
| `rotation_angle` | int | `270` | Display rotation in degrees: `0`, `90`, `180`, `270` |
| `day_interval` | int | `600` | Seconds between cards during day hours |
| `night_interval` | int | `3600` | Seconds between cards during night hours |
| `day_start` | int | `7` | Hour that day mode begins (24h, 0–23) |
| `day_end` | int | `23` | Hour that night mode begins (24h, 0–23) |
| `color_saturation` | float | `2.5` | Color boost applied before rendering (1.0 = none, 4.0 = vivid) |
| `collection_only` | bool | `false` | Only display cards marked as owned |
| `slab_header_mode` | string | `"normal"` | Header style: `"normal"` (white bg), `"inverted"` (black bg), `"off"` (full-bleed) |
| `image_fit` | string | `"contain"` | Image scaling: `"contain"` (letterbox) or `"cover"` (crop to fill) |
| `image_bg` | string | `"black"` | Background color when letterboxing: `"black"` or `"white"` |
| `thumbnail_cache` | bool | `false` | Pre-generate thumbnails for faster collection browsing |
| `auto_update_sources` | list | `[]` | Libraries included in weekly auto-update: `["pokemon", "mtg", ...]` |
| `auto_update_day` | int | `0` | Day of week for auto-update: `0` = Sunday, `6` = Saturday |
| `update_branch` | string | `"master"` | GitHub branch used for OTA update checks and installs |
| `pin_hash` | string | — | PBKDF2-SHA256 hash of PIN (set automatically when PIN is configured) |
| `pin_salt` | string | — | Random salt for PIN hash (set automatically) |
| `pin_setup_done` | bool | — | Tracks whether the first-boot PIN prompt has been completed |

### Data Files

| File | Location | Description |
|------|----------|-------------|
| `inkslab_config.json` | `/home/pi/.inkslab/` | Main configuration |
| `inkslab_collection.json` | `/home/pi/.inkslab/` | Owned card state per TCG |
| `inkslab_last_update.json` | `/home/pi/.inkslab/` | Auto-update timestamps per source |
| `.metron_credentials` | `/home/pi/.inkslab/` | Encrypted Metron API credentials |
| `.inkslab_secret_key` | `/home/pi/` | Flask session secret (generated on first boot) |

---

## API Sources

| Source | API | Auth Required | Notes |
|--------|-----|---------------|-------|
| Pokémon | PokemonTCG | No | 1.5–3s delay per image, 30s cooldown every 50 downloads |
| Magic: The Gathering | Scryfall API | No | 10 req/s respected (100ms between API calls); 0.1–0.3s delay per image |
| Disney Lorcana | Lorcast API | No | 150ms between API calls; 0.1–0.3s delay per image, exponential backoff on 429 |
| Manga | MangaDex API | No | 1.5s between API calls; 0.5s delay per image; 60s backoff on rate limit; English preferred, Japanese fallback |
| Comics | Metron API | Yes (free account) | 4s between API calls; 0.5s delay per image; 60s backoff on rate limit. Configure credentials in Settings → Metron Comics Account |

---

## Project Structure

```
inkslab/
├── inkslab.py                  # Display daemon — main loop, e-ink rendering
├── inkslab_web.py              # Flask web server — all API routes and dashboard HTML
├── wifi_manager.py             # WiFi hotspot and nmcli wrapper
├── inkslab.service             # systemd unit for display daemon
├── inkslab_web.service         # systemd unit for web server
├── requirements.txt            # Python dependencies
│
├── static/
│   ├── app.js                  # Main dashboard JavaScript
│   ├── style.css               # Dashboard stylesheet
│   ├── collection_view.js      # Grid/list view
│   ├── collection_list_preview.js
│   ├── dl_picker.js            # Downloads pill selector
│   ├── mobile_qs.js            # Mobile Quick Switch
│   ├── mtg_sets.js             # MTG set search
│   ├── pokemon_bulk.js         # Pokémon bulk download
│   ├── qs_pending.js           # Pending switch banner
│   ├── modal_helpers.js        # Reusable confirm/prompt/card-meta modals
│   ├── apple-touch-icon.png
│   └── inkslab_qr_bg.png
│
├── scripts/
│   ├── install.sh              # Automated installer
│   ├── selfheal.sh             # Pre-boot repair
│   ├── ota_update.sh           # OTA update with rollback
│   ├── download_cards_pokemon.py
│   ├── download_cards_mtg.py
│   ├── download_cards_lorcana.py
│   ├── download_covers_manga.py
│   ├── download_manga_series.py
│   ├── download_covers_comics.py
│   ├── download_comic_series.py
│   ├── download_pokemon_bulk.py
│   └── download_utils.py
│
└── lib/
    └── waveshare_epd/          # Bundled Waveshare e-paper driver (vendor snapshot)
```

**Runtime directories (created automatically):**
```
/home/pi/.inkslab/              # Config, collection, credentials
/home/pi/inkslab-collections/   # Card image libraries
    pokemon/  mtg/  lorcana/
    manga/    comics/  custom/
    .thumbcache/                # Thumbnail cache (shared)
/tmp/inkslab_*                  # Trigger files and status (volatile)
```

---

## Updating

### From the Dashboard

Go to **Settings → OTA Updates → Check for Updates**. If an update is available, click **Install**. The update runs in the background with rollback safety — if the new version fails to start, the previous version is automatically restored.

### Via SSH

```bash
cd /home/pi/inkslab
git pull
sudo systemctl restart inkslab inkslab_web
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Display shows nothing after boot | Wait 60–90 seconds — first render is slow. Check `sudo journalctl -u inkslab -n 50` |
| "No cards available" on screen | No card images downloaded yet. Go to Downloads tab and download a set |
| Owned Only mode shows no cards | Switch to **All Cards**, browse a set, and mark cards as owned first |
| Queue switch not firing immediately | The switch fires at the next card interval, not instantly |
| Admin mode requires PIN entry | Enter your dashboard PIN to access admin features — resets on page refresh |
| Collection list thumbnails missing | Thumbnails generate from downloaded images. Download content first, then enable thumbnail cache in Settings |
| Cooldown timer won't let me skip | The Waveshare Spectra 6 requires 3 minutes between full refreshes to prevent display damage. Queue the skip or wait |
| Downloads fail with permission error | The download scripts run as root via systemd. Check that `/home/pi/inkslab-collections/` is writable by root |
| Comics search returns no results | Metron API credentials required. Set them in Settings → Metron Comics Account |
| WiFi setup page doesn't appear | Connect to the **InkSlab-Setup** network, then navigate to `http://192.168.4.1` manually |
| Display colors look washed out | Increase **Color Saturation** in Settings (default 2.5, try 3.0–3.5) |
| Service fails to start | Run `sudo bash /home/pi/inkslab/scripts/selfheal.sh` manually to check and repair |
| OTA update failed | The previous version is automatically restored. Check `sudo journalctl -u inkslab_web -n 50` |
| Update checker shows updates on dev branch | Expected — set `update_branch` in Settings to match your active branch |

---

## Credits

- Original project: [costamesatechsolutions/inkslab-eink-tcg-display](https://github.com/costamesatechsolutions/inkslab-eink-tcg-display)
- Waveshare e-Paper library: [waveshare/e-Paper](https://github.com/waveshare/e-Paper)
- Card data: [PokemonTCG](https://github.com/PokemonTCG/pokemon-tcg-data), [Scryfall](https://scryfall.com/docs/api), [Lorcast](https://lorcast.com), [MangaDex](https://api.mangadex.org), [Metron](https://metron.cloud)
- 3D printed frame: [InkSlab on MakerWorld](https://makerworld.com/en/models/2452200-inkslab-open-source-e-ink-tcg-display)
- v4.0 development assisted by [Claude Sonnet 4.6](https://anthropic.com/claude)

---

## License

[AGPL-3.0](LICENSE)
