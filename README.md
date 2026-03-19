# InkSlab — e-Ink TCG Card Display

A Raspberry Pi-powered e-ink display that shows your Pokemon, Magic: The Gathering, Disney Lorcana, Manga, and Comic Book covers in a graded-slab style layout. Upload your own custom images too. Control everything from your phone — switch between libraries, download content, curate your collection, and more.

**No command line needed.** Pre-flashed units have built-in WiFi setup — just power on, connect to the InkSlab network, and pick your WiFi. Everything else runs through a clean web dashboard — including software updates.

**By [Costa Mesa Tech Solutions](https://github.com/costamesatechsolutions)** (a brand of Pine Heights Ventures LLC)
**Fork maintained by [GenerlAce](https://github.com/GenerlAce)** with extended manga, comics, and dashboard features.

---

## What It Does

- Cycles through TCG cards and cover art on a 7-color e-ink display (black, white, red, yellow, blue, green, orange)
- Shows card art in a graded-slab frame with set name, year, card number, and rarity
- **Full-bleed overlay header** for manga and comics — text overlays directly on the cover when no header space is available
- **Slab Header Modes:** Normal (white bg), Inverted (black bg), or Off (full-screen card art)
- **Web Dashboard:** Control everything from your phone or browser at `http://<your-pi-ip>`
- **Live Player Controls:** Pause, play, skip, or go back, complete with an "Up Next" queue and countdown timer
- **Collection Mode & Search:** Only display cards you own. Search for a card (e.g., "Pikachu") and instantly add *all* variations across every set to your collection.
- **Rarity Filtering:** Select or deselect all cards of a specific rarity across every set with one tap
- **Smart Shuffle:** Remembers recently shown cards and pushes them to the back of the deck upon reshuffling
- **Custom Images:** Upload your own images and organize them into sets with optional metadata
- **WiFi Setup Mode:** Automatically creates an "InkSlab-Setup" WiFi network when no connection is found on boot
- **OTA Updates:** Update InkSlab software directly from the web dashboard
- **Auto-Update:** Weekly automatic refresh of all enabled content sources
- Runs 24/7 as a desk display, rotating cards every 10 minutes (configurable for day/night)

### Supported Libraries
- **Pokemon** — via [PokemonTCG data](https://github.com/PokemonTCG/pokemon-tcg-data)
- **Magic: The Gathering** — via [Scryfall API](https://scryfall.com/)
- **Disney Lorcana** — via [Lorcast API](https://lorcast.com/)
- **Manga** — via [MangaDex API](https://api.mangadex.org) (no login required)
- **Comics** — via [Metron API](https://metron.cloud) (free account required)
- **Custom** — upload your own PNG/JPG images

```
+-----------------------+
|  2023 OBSIDIAN FLAMES |
|    #201  *  HOLO      |
| +-------------------+ |
| |                   | |
| |    Card Image     | |
| |                   | |
| |                   | |
| +-------------------+ |
+-----------------------+
```

---

## What You Need

| Part | Notes |
|------|-------|
| **Raspberry Pi Zero W H** | The "H" means headers are pre-soldered (required for the display HAT) |
| **[Waveshare 4" e-Paper HAT+ (E)](https://www.waveshare.com/wiki/4inch_e-Paper_HAT%2B_(E)_Manual)** | Spectra 6 — the 7-color model |
| **Micro SD card** | 32 GB for one TCG, 64 GB+ for all (Pokemon ~13 GB, MTG ~13 GB, Lorcana ~2 GB, Manga ~2 GB, Comics grows weekly) |
| **90-degree micro USB cable** | Optional but recommended — keeps the power cable hidden behind the frame |
| **3D printed frame** | Print files on MakerWorld: **[InkSlab on MakerWorld](https://makerworld.com/en/models/2452200-inkslab-open-source-e-ink-tcg-display)** |

---

## Setup

### Pre-Flashed Units (Easiest)

If you received a pre-flashed InkSlab, setup takes about 30 seconds:

1. **Power on** the InkSlab — wait about 90 seconds for the e-ink display to show setup instructions
2. On your phone, go to **Settings > WiFi** and connect to `InkSlab-Setup` (no password needed)
3. A setup page should appear automatically. If not, open `http://10.42.0.1` in your web browser
4. **Pick your home WiFi** from the list, enter the password, and tap Connect
5. The display will show your new dashboard address with a scannable QR code
6. **Reconnect your phone** to your home WiFi and open that address — you're done!

---

### DIY Setup (Flash Your Own SD Card)

### Step 1 — Flash the SD Card

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Choose **Raspberry Pi Zero** > **Raspberry Pi OS (Legacy, 32-bit) Lite**
3. Click **Next** > **Edit Settings**:
   - Set hostname to `inkslab`, username to `pi`, pick a password
   - Enter your Wi-Fi name and password
   - Under **Services**, enable SSH
4. Flash, insert the SD card, power on the Pi, and wait ~2 minutes

### Step 2 — SSH In and Install

```bash
ssh pi@inkslab.local
sudo raspi-config nonint do_spi 0
sudo reboot
```

After reboot, SSH back in and run:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy python3-spidev python3-gpiozero python3-requests python3-flask python3-qrcode git
sudo apt-get install -y gpiod libgpiod-dev

# Clone InkSlab
git clone https://github.com/GenerlAce/inkslab-eink-tcg-display.git /home/pi/inkslab

# Create card library directory
mkdir -p /home/pi/inkslab-collections

# Install Gunicorn (production web server)
sudo pip3 install gunicorn --break-system-packages
```

### Step 3 — Start the Services

```bash
sudo cp /home/pi/inkslab/inkslab.service /etc/systemd/system/
sudo cp /home/pi/inkslab/inkslab_web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable inkslab inkslab_web
sudo systemctl start inkslab inkslab_web
```

---

## Migrating from an Older Installation?

If you have an existing InkSlab installation at the old path (`~/4inch_e-Paper_E/.../inkslab-eink-tcg-display/`), run the migration script to move your card libraries and config to the new layout:

```bash
git clone https://github.com/GenerlAce/inkslab-eink-tcg-display.git /home/pi/inkslab
bash /home/pi/inkslab/scripts/migrate_paths.sh
```

The script safely moves your existing card libraries (Pokemon, MTG, etc.) to `/home/pi/inkslab-collections/`, installs the new service files, and restarts everything. Your old program directory (`~/4inch_e-Paper_E/`) is left in place — delete it manually once you've verified the new setup is working.

---

## Manga Setup

Manga downloads from MangaDex — no account needed.

- **Bulk download** (top 500 popular): Run `scripts/download_covers_manga.py`
- **Series search**: Use the Downloads tab in the web dashboard to search and download all covers for a specific manga

---

## Comics Setup

Comics download from [Metron](https://metron.cloud) — a free account is required.

1. [Sign up at metron.cloud](https://metron.cloud/accounts/signup/)
2. In the InkSlab web dashboard, go to **Settings** > **Metron Comics Account** and enter your credentials
3. Credentials are stored securely on the Pi at `/home/pi/.metron_credentials` — never committed to git

- **Weekly new releases**: Run `scripts/download_covers_comics.py` (auto-runs weekly if enabled)
- **Series search**: Use the Downloads tab to search and download all covers for a specific series

---

## Web Dashboard

### Display Tab
- Live preview, player controls, Up Next queue, Quick Switch between libraries

### Settings Tab
- Active library, slab header mode, rotation, intervals, collection mode
- **Metron Comics Account**: Connect/disconnect your Metron account
- **Auto-Update Sources**: Check which libraries refresh automatically each week
- **Software Update**: OTA updates from the dashboard

### Collection Tab
- Browse sets in **List** or **Grid** view
- Hover over any card name or thumbnail for an instant preview
- **Filter by Rarity**: Collapsible section — toggle rarities on/off across all sets
- **Per-series delete**: Two-step confirm delete button on every set
- Alphabetical sorting across all libraries

### Downloads Tab
- **Storage**: Visual breakdown of SD card usage by library
- **Download Cards**: One-click download for all libraries
- **Manga Series Search**: Search MangaDex and download all covers for a specific manga
- **Comic Series Search**: Search Metron and download all covers for a specific comic series
- **Delete Entire Library**: Two-step confirm to wipe a full library
- Live download progress log

---

## Auto-Update

Enable weekly automatic updates in **Settings > Auto-Update Sources**:

| Source | What it downloads |
|--------|------------------|
| Pokemon | Full card list from PokéAPI |
| Magic: The Gathering | Full card list from Scryfall |
| Disney Lorcana | Full card list from Lorcast |
| Manga  | Top 500 popular titles from MangaDex |
| Comics | Weekly new releases from Metron |

- Runs automatically once per week per enabled source
- Skips download if less than 500MB free disk space
- Last updated date shown per source

---

## Updating

### From the Web Dashboard (Recommended)
1. Go to **Settings** tab
2. Click **Check for Updates**
3. If updates are available, click **Update Now**

### Via SSH
```bash
cd /home/pi/inkslab
git pull
sudo systemctl restart inkslab inkslab_web
```

---

## Project Structure

```
/home/pi/inkslab/               ← Program files
  inkslab.py                    # Display daemon
  inkslab_web.py                # Web dashboard (Flask + Gunicorn)
  wifi_manager.py               # WiFi setup mode (nmcli wrapper)
  inkslab.service               # systemd service for display
  inkslab_web.service           # systemd service for web dashboard
  requirements.txt              # Python dependencies
  lib/
    waveshare_epd/              # Bundled display driver (see note below)
  static/
    app.js                      # Main web dashboard JS
    style.css                   # Web dashboard styles
    collection_view.js          # Grid/list view toggle and thumbnails
    delete_library.js           # Two-step library delete
  scripts/
    download_cards_pokemon.py   # Pokemon card downloader
    download_cards_mtg.py       # MTG card downloader (Scryfall API)
    download_cards_lorcana.py   # Lorcana card downloader (Lorcast API)
    download_covers_manga.py    # Manga bulk downloader (MangaDex API)
    download_manga_series.py    # Manga series downloader (MangaDex API)
    download_covers_comics.py   # Comics weekly downloader (Metron API)
    download_comic_series.py    # Comics series downloader (Metron API)
    ota_update.sh               # OTA update script
    selfheal.sh                 # Service health monitor
    migrate_paths.sh            # One-time migration from old path layout

/home/pi/inkslab-collections/   ← Card library data (separate from program)
  pokemon/
  mtg/
  lorcana/
  manga/
  comics/
  custom/
  .thumbcache/                  # Thumbnail cache (shared across all libraries)

/home/pi/                       ← Config and credentials
  inkslab_config.json           # All settings (managed via web dashboard)
  inkslab_collection.json       # Your owned card collection
  inkslab_last_update.json      # Auto-update timestamps
  .metron_credentials           # Metron API credentials (never committed to git)
```

---

## Bundled Display Driver

InkSlab ships with a **snapshot** of the Waveshare e-Paper display driver (`lib/waveshare_epd/`), version **V1.2 (2022-10-29)**. This is included for install simplicity — no separate driver download is required.

**Full credit to Waveshare Electronics** for developing and maintaining this driver. The driver is licensed under the MIT License and is reproduced here with attribution as permitted.

| Resource | Link |
|----------|------|
| Waveshare official driver repo | [waveshare/e-Paper on GitHub](https://github.com/waveshare/e-Paper) |
| 4" e-Paper HAT+ (E) product page | [Waveshare Wiki](https://www.waveshare.com/wiki/4inch_e-Paper_HAT%2B_(E)_Manual) |
| Driver download (latest) | [4inch_e-Paper_E.zip](https://files.waveshare.com/wiki/4inch-e-Paper-HAT%2B-(E)/4inch_e-Paper_E.zip) |

**Want the latest driver?** The bundled version works with the Waveshare 4" HAT+ (E) and has been stable since 2022. If Waveshare releases a new driver and you need it, replace the contents of `lib/waveshare_epd/` with the files from:
```
4inch_e-Paper_E.zip → RaspberryPi_JetsonNano/python/lib/waveshare_epd/
```

InkSlab does not modify the Waveshare driver in any way — it is used as-is.

---

## Configuration

All settings are managed from the web dashboard. Stored in `/home/pi/inkslab_config.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| `active_tcg` | `"pokemon"` | Active library (`pokemon`, `mtg`, `lorcana`, `manga`, `comics`, `custom`) |
| `slab_header_mode` | `"normal"` | Slab header style: `"normal"`, `"inverted"`, or `"off"` |
| `rotation_angle` | `270` | Display rotation (0/90/180/270) |
| `day_interval` | `600` | Seconds between cards during the day |
| `night_interval` | `3600` | Seconds between cards at night |
| `day_start` / `day_end` | `7` / `23` | Day mode hours (24h format) |
| `color_saturation` | `2.5` | Color boost for e-paper |
| `collection_only` | `false` | Only show cards marked as owned |
| `auto_update_sources` | `[]` | List of libraries to auto-update weekly |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Can't find the dashboard | The IP is shown on the e-ink display at boot. Run `hostname -I` on the Pi or check your router. |
| Display not updating | Check SPI is enabled: `ls /dev/spi*`. Check logs: `journalctl -u inkslab -f` |
| Washed-out colors | Increase **Color Saturation** in Settings (default 2.5, try 3.0–4.0) |
| Web dashboard not loading | Run `journalctl -u inkslab_web -f` |
| Collection mode shows nothing | Mark some cards as owned in the Collection tab first |
| Download fails or stalls | Click Stop Download then restart — it resumes safely from where it left off |
| Comics search returns no results | Check your Metron credentials in Settings > Metron Comics Account |
| Manga covers showing multiple per volume | Re-run `download_manga_series.py` — it now deduplicates to one cover per volume (Japanese preferred) |
| Auto-update not running | Check Settings > Auto-Update Sources has sources checked. Check logs: `journalctl -u inkslab_web | grep auto` |
| Low disk space warning | Free up space by deleting unused libraries in the Downloads tab |
| WiFi not connecting after change | The old WiFi profile is automatically deleted before connecting to the new one |

---

## Credits

- Pokemon card data: [PokemonTCG/pokemon-tcg-data](https://github.com/PokemonTCG/pokemon-tcg-data) (open data)
- MTG card data: [Scryfall](https://scryfall.com/) (free API)
- Lorcana card data: [Lorcast](https://lorcast.com/) (free API)
- Manga data: [MangaDex](https://mangadex.org/) (free API, no login required)
- Comics data: [Metron](https://metron.cloud/) (free account required)
- Display driver: [Waveshare e-Paper](https://github.com/waveshare/e-Paper) (MIT License) — bundled as a vendor snapshot, unmodified
- Extended features developed with [Claude Sonnet 4.6](https://anthropic.com) by Anthropic

## License

AGPL-3.0 — see [LICENSE](LICENSE)


## Star History

<a href="https://www.star-history.com/?repos=costamesatechsolutions%2Finkslab-eink-tcg-display&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=costamesatechsolutions/inkslab-eink-tcg-display&type=date&theme=dark&legend=bottom-right" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=costamesatechsolutions/inkslab-eink-tcg-display&type=date&legend=bottom-right" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=costamesatechsolutions/inkslab-eink-tcg-display&type=date&legend=bottom-right" />
 </picture>
</a>
