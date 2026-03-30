#!/bin/bash
# InkSlab Install Script
# Usage: bash install.sh
# Or one-liner: curl -sSL https://raw.githubusercontent.com/GenerlAce/inkslab-eink-tcg-display/main/scripts/install.sh | bash

set -e

INKSLAB_DIR="/home/pi/inkslab"
COLLECTIONS_DIR="/home/pi/inkslab-collections"
REPO_URL="https://github.com/GenerlAce/inkslab-eink-tcg-display.git"
REPO_BRANCH="main"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        InkSlab Installer v3.0        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# Must not run as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Run this script as the pi user, not as root/sudo.${NC}"
    exit 1
fi

# ── Screen Selection ──────────────────────────────────────────────────────────
echo -e "${BLUE}Which e-ink screen are you using?${NC}"
echo -e "  ${YELLOW}1${NC}) Waveshare 4\" Spectra 6  (4in0e)"
echo -e "  ${YELLOW}2${NC}) Inky Impression 7.3\" Spectra 6  (7in3f)"
echo ""
read -rp "Enter 1 or 2 [1]: " _screen_choice
echo ""

if [[ "$_screen_choice" == "2" ]]; then
    SCREEN_TYPE="7in3f"
    echo -e "      ${GREEN}✓ Screen: Inky Impression 7.3\" Spectra 6 (7in3f)${NC}"
else
    SCREEN_TYPE="4in0e"
    echo -e "      ${GREEN}✓ Screen: Waveshare 4\" Spectra 6 (4in0e)${NC}"
fi
echo ""

# ── Step 1: Hardware setup ─────────────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking hardware configuration...${NC}"
_NEED_REBOOT=false

# SPI — required for both screens
if ls /dev/spi* &>/dev/null 2>&1; then
    echo -e "      ${GREEN}✓ SPI already enabled${NC}"
else
    echo -e "      Enabling SPI..."
    sudo raspi-config nonint do_spi 0
    _NEED_REBOOT=true
fi

# I2C + spi0-0cs overlay — required for Inky Impression 7.3"
if [ "$SCREEN_TYPE" = "7in3f" ]; then
    if ! grep -qE '^dtparam=i2c_arm=on' /boot/firmware/config.txt; then
        echo -e "      Enabling I2C..."
        sudo sed -i 's/^#\s*dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/firmware/config.txt
        if ! grep -qE '^dtparam=i2c_arm=on' /boot/firmware/config.txt; then
            echo 'dtparam=i2c_arm=on' | sudo tee -a /boot/firmware/config.txt > /dev/null
        fi
        _NEED_REBOOT=true
    else
        echo -e "      ${GREEN}✓ I2C already enabled${NC}"
    fi
    if ! grep -q 'dtoverlay=spi0-0cs' /boot/firmware/config.txt; then
        echo -e "      Adding spi0-0cs overlay (required for Inky CS pin)..."
        echo 'dtoverlay=spi0-0cs' | sudo tee -a /boot/firmware/config.txt > /dev/null
        _NEED_REBOOT=true
    else
        echo -e "      ${GREEN}✓ spi0-0cs overlay already present${NC}"
    fi
fi

if [ "$_NEED_REBOOT" = true ]; then
    echo ""
    echo -e "${YELLOW}Hardware settings changed — a reboot is required before continuing.${NC}"
    echo -e "After reboot, re-run this script to finish installation:"
    echo -e "  ${BLUE}bash ~/install.sh${NC}"
    echo ""
    read -rp "Reboot now? [Y/n] " _reboot
    if [[ "$_reboot" != "n" && "$_reboot" != "N" ]]; then
        cp "$0" ~/install.sh 2>/dev/null || true
        sudo reboot
    fi
    exit 0
fi

# ── Step 2: System packages ────────────────────────────────────────────────────
echo -e "${YELLOW}[2/6] Installing system packages...${NC}"
sudo apt-get update -qq
sudo apt-get install -y \
    python3-pip python3-pil python3-spidev \
    python3-gpiozero python3-requests python3-flask python3-qrcode \
    python3-cryptography git gpiod libgpiod-dev unzip \
    fonts-dejavu-core
echo -e "      ${GREEN}✓ Packages installed${NC}"

# ── Step 3: Python packages ────────────────────────────────────────────────────
echo -e "${YELLOW}[3/6] Installing Python packages...${NC}"
sudo pip3 install waitress --break-system-packages -q
echo -e "      ${GREEN}✓ Waitress installed${NC}"

if [ "$SCREEN_TYPE" = "7in3f" ]; then
    echo -e "      Installing Inky drivers..."
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    DIST_PKGS="/usr/local/lib/python${PY_VER}/dist-packages"
    TMP=$(mktemp -d)
    # Install gpiodevice first (inky depends on it), then inky
    # Uses pip download + manual copy to work around a piwheels bug on Python 3.13
    # where wheels are downloaded but install as 0-byte files.
    for PKG in gpiodevice inky; do
        pip3 download "$PKG" --no-deps -d "$TMP/${PKG}" -q 2>/dev/null
        WHL=$(ls "$TMP/${PKG}"/*.whl 2>/dev/null | head -1)
        if [ -n "$WHL" ]; then
            unzip -q "$WHL" -d "$TMP/${PKG}_src"
            sudo cp -r "$TMP/${PKG}_src/$PKG" "$DIST_PKGS/" 2>/dev/null || true
        fi
    done
    rm -rf "$TMP"
    echo -e "      ${GREEN}✓ Inky drivers installed${NC}"
fi

# ── Step 4: Clone or update InkSlab ───────────────────────────────────────────
echo -e "${YELLOW}[4/6] Installing InkSlab...${NC}"
if [ -d "$INKSLAB_DIR/.git" ]; then
    echo -e "      Found existing install at $INKSLAB_DIR — pulling latest..."
    git -C "$INKSLAB_DIR" pull
else
    git clone -b "$REPO_BRANCH" "$REPO_URL" "$INKSLAB_DIR"
fi
mkdir -p "$COLLECTIONS_DIR"

# Write screen type to config
python3 - <<PYEOF
import json, os
cfg_path = "$INKSLAB_DIR/inkslab_config.json"
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        try:
            cfg = json.load(f)
        except Exception:
            pass
cfg['screen'] = '$SCREEN_TYPE'
with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
PYEOF

echo -e "      ${GREEN}✓ InkSlab installed at $INKSLAB_DIR${NC}"
echo -e "      ${GREEN}✓ Collections directory: $COLLECTIONS_DIR${NC}"
echo -e "      ${GREEN}✓ Screen configured: $SCREEN_TYPE${NC}"

# ── Step 5: Install systemd services ──────────────────────────────────────────
echo -e "${YELLOW}[5/6] Installing services...${NC}"
sudo cp "$INKSLAB_DIR/inkslab.service" /etc/systemd/system/
sudo cp "$INKSLAB_DIR/inkslab_web.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable inkslab inkslab_web
echo -e "      ${GREEN}✓ Services installed and enabled${NC}"

# ── Step 6: Start services ─────────────────────────────────────────────────────
echo -e "${YELLOW}[6/6] Starting InkSlab...${NC}"
# Use nohup to avoid D-Bus disconnection over SSH killing the start command
sudo systemctl start inkslab inkslab_web 2>/dev/null || true
sleep 3

_ok=true
if ! systemctl is-active --quiet inkslab; then
    echo -e "      ${RED}⚠ inkslab service failed to start${NC}"
    echo -e "        Check: journalctl -u inkslab -f"
    _ok=false
fi
if ! systemctl is-active --quiet inkslab_web; then
    echo -e "      ${RED}⚠ inkslab_web service failed to start${NC}"
    echo -e "        Check: journalctl -u inkslab_web -f"
    _ok=false
fi

if [ "$_ok" = true ]; then
    echo -e "      ${GREEN}✓ Both services running${NC}"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     InkSlab installation complete!   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "Open your browser to: ${BLUE}http://inkslab.local${NC}"
echo -e "Or check the e-ink display for the IP address and QR code."
echo ""
echo -e "Next: go to the ${BLUE}Downloads${NC} tab and download your card library."
echo ""
