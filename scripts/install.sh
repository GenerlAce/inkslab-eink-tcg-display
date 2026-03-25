#!/bin/bash
# InkSlab Install Script
# Usage: bash install.sh
# Or one-liner: curl -sSL https://raw.githubusercontent.com/GenerlAce/inkslab-eink-tcg-display/inkslab-4/scripts/install.sh | bash

set -e

INKSLAB_DIR="/home/pi/inkslab"
COLLECTIONS_DIR="/home/pi/inkslab-collections"
REPO_URL="https://github.com/GenerlAce/inkslab-eink-tcg-display.git"
REPO_BRANCH="inkslab-4"

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

# ── Step 1: SPI ────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking SPI...${NC}"
if ls /dev/spi* &>/dev/null 2>&1; then
    echo -e "      ${GREEN}✓ SPI already enabled${NC}"
else
    echo -e "      Enabling SPI..."
    sudo raspi-config nonint do_spi 0
    echo ""
    echo -e "${YELLOW}SPI enabled — a reboot is required before continuing.${NC}"
    echo -e "After reboot, re-run this script to finish installation:"
    echo -e "  ${BLUE}bash ~/install.sh${NC}"
    echo ""
    read -rp "Reboot now? [Y/n] " _reboot
    if [[ "$_reboot" != "n" && "$_reboot" != "N" ]]; then
        # Copy script to home so it's easy to re-run after reboot
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
    python3-cryptography git gpiod libgpiod-dev
echo -e "      ${GREEN}✓ Packages installed${NC}"

# ── Step 3: Waitress ──────────────────────────────────────────────────────────
echo -e "${YELLOW}[3/6] Installing Waitress...${NC}"
sudo pip3 install waitress --break-system-packages -q
echo -e "      ${GREEN}✓ Waitress installed${NC}"

# ── Step 4: Clone or update InkSlab ───────────────────────────────────────────
echo -e "${YELLOW}[4/6] Installing InkSlab...${NC}"
if [ -d "$INKSLAB_DIR/.git" ]; then
    echo -e "      Found existing install at $INKSLAB_DIR — pulling latest..."
    git -C "$INKSLAB_DIR" pull
else
    git clone -b "$REPO_BRANCH" "$REPO_URL" "$INKSLAB_DIR"
fi
mkdir -p "$COLLECTIONS_DIR"
echo -e "      ${GREEN}✓ InkSlab installed at $INKSLAB_DIR${NC}"
echo -e "      ${GREEN}✓ Collections directory: $COLLECTIONS_DIR${NC}"

# ── Step 5: Install systemd services ──────────────────────────────────────────
echo -e "${YELLOW}[5/6] Installing services...${NC}"
sudo cp "$INKSLAB_DIR/inkslab.service" /etc/systemd/system/
sudo cp "$INKSLAB_DIR/inkslab_web.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable inkslab inkslab_web
echo -e "      ${GREEN}✓ Services installed and enabled${NC}"

# ── Step 6: Start services ─────────────────────────────────────────────────────
echo -e "${YELLOW}[6/6] Starting InkSlab...${NC}"
sudo systemctl start inkslab inkslab_web
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
