#!/bin/bash
# InkSlab Path Migration Script
# Migrates an existing installation from the old nested path to /home/pi/inkslab/
# and reorganizes card libraries into /home/pi/inkslab-collections/
#
# Run this ONCE on your Pi after cloning InkSlab to /home/pi/inkslab/
# Safe to run multiple times — skips moves if destination already exists.

set -e

echo "=== InkSlab Path Migration ==="
echo ""

# Stop services before migrating
echo "Stopping InkSlab services..."
sudo systemctl stop inkslab inkslab_web 2>/dev/null || true

# Create new collections directory
echo "Creating /home/pi/inkslab-collections/..."
mkdir -p /home/pi/inkslab-collections

# Migrate card libraries
migrate_dir() {
    local OLD="$1"
    local NEW="$2"
    local LABEL="$3"
    if [ -d "$OLD" ] && [ ! -d "$NEW" ]; then
        echo "  Moving $LABEL: $OLD → $NEW"
        mv "$OLD" "$NEW"
    elif [ -d "$NEW" ]; then
        echo "  $LABEL already at $NEW — skipping"
    else
        echo "  $LABEL not found at $OLD — skipping (will be created on first download)"
    fi
}

echo ""
echo "Migrating card libraries..."
migrate_dir "/home/pi/pokemon_cards"   "/home/pi/inkslab-collections/pokemon"  "Pokemon"
migrate_dir "/home/pi/mtg_cards"       "/home/pi/inkslab-collections/mtg"      "Magic: The Gathering"
migrate_dir "/home/pi/lorcana_cards"   "/home/pi/inkslab-collections/lorcana"  "Disney Lorcana"
migrate_dir "/home/pi/manga_covers"    "/home/pi/inkslab-collections/manga"    "Manga"
migrate_dir "/home/pi/comic_covers"    "/home/pi/inkslab-collections/comics"   "Comics"
migrate_dir "/home/pi/custom_images"   "/home/pi/inkslab-collections/custom"   "Custom"
migrate_dir "/home/pi/inkslab_thumbcache" "/home/pi/inkslab-collections/.thumbcache" "Thumbnail cache"

# Install and enable new service files
echo ""
echo "Installing service files..."
sudo cp /home/pi/inkslab/inkslab.service /etc/systemd/system/inkslab.service
sudo cp /home/pi/inkslab/inkslab_web.service /etc/systemd/system/inkslab_web.service
sudo systemctl daemon-reload

# Install Gunicorn if not present
if ! command -v gunicorn &>/dev/null; then
    echo ""
    echo "Installing Gunicorn..."
    sudo pip3 install gunicorn --break-system-packages
fi

# Enable and start services
echo ""
echo "Enabling and starting services..."
sudo systemctl enable inkslab inkslab_web
sudo systemctl start inkslab inkslab_web

echo ""
echo "=== Migration complete! ==="
echo ""
echo "Services started. Check status with:"
echo "  sudo systemctl status inkslab inkslab_web"
echo ""
echo "Old program path (safe to delete after verifying everything works):"
echo "  ~/4inch_e-Paper_E/"
