#!/usr/bin/python3
"""
Convert all .avif card images to .png, keeping the original .avif files.
Supports resume - skips any card that already has a .png.

Usage:
    sudo pip install pillow pillow-avif-plugin --break-system-packages
    sudo python3 convert_avif_to_png.py
"""

import os
import sys

BASE_DIR = "/home/pi/inkslab-collections/lorcana"

try:
    import pillow_avif  # registers AVIF support with Pillow
except ImportError:
    print("ERROR: pillow-avif-plugin not found.")
    print("Run: sudo pip install pillow pillow-avif-plugin --break-system-packages")
    sys.exit(1)

from PIL import Image

def convert_all():
    print(f"=== AVIF -> PNG Converter ===")
    print(f"Scanning: {BASE_DIR}\n")

    converted = 0
    skipped = 0
    failed = 0

    for root, dirs, files in os.walk(BASE_DIR):
        avif_files = [f for f in files if f.endswith(".avif")]
        if not avif_files:
            continue

        print(f"[{os.path.relpath(root, BASE_DIR)}] {len(avif_files)} avif files...")

        for filename in avif_files:
            avif_path = os.path.join(root, filename)
            png_path = os.path.join(root, filename.replace(".avif", ".png"))

            # Skip if PNG already exists
            if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                skipped += 1
                continue

            try:
                with Image.open(avif_path) as img:
                    img.save(png_path, "PNG")
                converted += 1
            except Exception as e:
                print(f"   FAILED: {filename} — {e}")
                failed += 1

    print(f"\n=== Done! Converted: {converted}, Already PNG: {skipped}, Failed: {failed} ===")


if __name__ == "__main__":
    convert_all()
