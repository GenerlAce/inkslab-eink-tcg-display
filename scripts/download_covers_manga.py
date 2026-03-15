#!/usr/bin/python3
"""
Download manga cover images from the MangaDex API.
Saves covers organized by manga title with metadata.
Supports resume - re-run safely to pick up where you left off.

No login required - uses the public MangaDex API.

Usage:
    python3 download_covers_manga.py
"""

import os
import requests
import json
import time
import random
import gc

# --- CONFIGURATION ---
BASE_DIR = "/home/pi/manga_covers"

API_BASE = "https://api.mangadex.org"
CDN_BASE = "https://uploads.mangadex.org"

HEADERS = {
    'User-Agent': 'InkSlab/1.0 (https://github.com/costamesatechsolutions/inkslab-eink-tcg-display)',
    'Accept': 'application/json',
}

# How many manga to download covers for (set to None for all)
MANGA_LIMIT = 500

# Content ratings to include: "safe", "suggestive", "erotica", "pornographic"
CONTENT_RATINGS = ["safe", "suggestive"]

# Rate limiting - MangaDex asks to be polite
API_DELAY = 1.5       # seconds between API calls (stay well under rate limits)
DOWNLOAD_DELAY = 0.5  # seconds between image downloads
COOLDOWN_EVERY = 50
COOLDOWN_SECONDS = 10

# Page size for API requests (max 100)
PAGE_SIZE = 100


def download_file(url, filepath):
    """Download a file, skipping if it already exists."""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return "EXISTS"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(r.content)
            return "DOWNLOADED"
        return f"HTTP {r.status_code}"
    except Exception as e:
        return f"FAIL: {e}"


def fetch_popular_manga(offset=0):
    """Fetch a page of popular manga sorted by follow count."""
    params = {
        "limit": PAGE_SIZE,
        "offset": offset,
        "order[followedCount]": "desc",
        "includes[]": "cover_art",
        "contentRating[]": CONTENT_RATINGS,
        "availableTranslatedLanguage[]": "en",
    }
    time.sleep(API_DELAY)
    try:
        r = requests.get(f"{API_BASE}/manga", headers=HEADERS, params=params, timeout=30)
        if r.status_code == 429:
            print("   Rate limited, waiting 60s...")
            time.sleep(60)
            return None, 0
        r.raise_for_status()
        data = r.json()
        return data.get("data", []), data.get("total", 0)
    except Exception as e:
        print(f"   Error fetching manga list: {e}")
        return None, 0


def get_cover_url(manga):
    """Extract the cover image URL from a manga object with included cover_art."""
    try:
        for rel in manga.get("relationships", []):
            if rel.get("type") == "cover_art":
                attrs = rel.get("attributes", {})
                filename = attrs.get("fileName", "")
                if filename:
                    manga_id = manga["id"]
                    return f"{CDN_BASE}/covers/{manga_id}/{filename}"
    except Exception:
        pass
    return None


def get_manga_title(manga):
    """Get the best available English title for a manga."""
    try:
        titles = manga.get("attributes", {}).get("title", {})
        return (titles.get("en") or
                titles.get("ja-ro") or
                titles.get("ja") or
                next(iter(titles.values()), "Unknown"))
    except Exception:
        return "Unknown"


def safe_dirname(title):
    """Convert a manga title to a safe directory name."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return safe.strip()[:60]  # limit length


def main():
    print("=== MangaDex Cover Downloader ===\n")
    print(f"Saving to: {BASE_DIR}")
    print(f"Content ratings: {', '.join(CONTENT_RATINGS)}")
    print(f"Target: top {MANGA_LIMIT} manga by popularity\n")

    os.makedirs(BASE_DIR, exist_ok=True)

    # Fetch all manga pages
    print("1. Fetching manga list from MangaDex...")
    all_manga = []
    offset = 0
    total = None

    while True:
        manga_page, page_total = fetch_popular_manga(offset)
        if manga_page is None:
            print("   Failed to fetch page, stopping.")
            break
        if total is None:
            total = page_total
            print(f"   Total available: {total} manga")

        all_manga.extend(manga_page)
        offset += len(manga_page)
        print(f"   Fetched {len(all_manga)} so far...")

        if not manga_page or (MANGA_LIMIT and len(all_manga) >= MANGA_LIMIT):
            break

    if MANGA_LIMIT:
        all_manga = all_manga[:MANGA_LIMIT]

    print(f"   Total to process: {len(all_manga)} manga\n")

    # Build master index
    master_index = {}
    for manga in all_manga:
        manga_id = manga["id"]
        title = get_manga_title(manga)
        dirname = safe_dirname(title)
        attrs = manga.get("attributes", {})
        year = str(attrs.get("year", "")) if attrs.get("year") else ""
        master_index[dirname] = {
            "name": title,
            "year": year,
            "id": manga_id,
        }

    index_path = os.path.join(BASE_DIR, "master_index.json")
    with open(index_path, "w") as f:
        json.dump(master_index, f, ensure_ascii=False, indent=2)
    print(f"2. Saved master_index.json ({len(master_index)} manga)\n")

    print("3. Downloading covers...")
    print("   Press CTRL+C to stop (you can resume later).\n")

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    for i, manga in enumerate(all_manga):
        manga_id = manga["id"]
        title = get_manga_title(manga)
        dirname = safe_dirname(title)
        attrs = manga.get("attributes", {})
        year = str(attrs.get("year", "")) if attrs.get("year") else ""

        cover_url = get_cover_url(manga)
        if not cover_url:
            print(f"[{i+1}/{len(all_manga)}] {title} — no cover, skipping")
            continue

        # Determine extension from URL
        ext = ".jpg"
        if ".png" in cover_url.lower():
            ext = ".png"

        manga_dir = os.path.join(BASE_DIR, dirname)
        os.makedirs(manga_dir, exist_ok=True)

        # Save metadata
        data_file = os.path.join(manga_dir, "_data.json")
        if not os.path.exists(data_file):
            with open(data_file, "w") as f:
                json.dump({
                    manga_id: {
                        "name": title,
                        "number": str(i + 1),
                        "rarity": (attrs.get("publicationDemographic") or "Manga").title(),
                        "year": year,
                    }
                }, f, ensure_ascii=False)

        filepath = os.path.join(manga_dir, f"{manga_id}{ext}")
        status = download_file(cover_url, filepath)

        if status == "DOWNLOADED":
            total_downloaded += 1
            print(f"[{i+1}/{len(all_manga)}] Downloaded: {title}")
            time.sleep(DOWNLOAD_DELAY)
            if total_downloaded % COOLDOWN_EVERY == 0:
                print(f"   [Cooldown {COOLDOWN_SECONDS}s...]")
                time.sleep(COOLDOWN_SECONDS)
        elif status == "EXISTS":
            total_skipped += 1
        else:
            total_failed += 1
            print(f"[{i+1}/{len(all_manga)}] Failed: {title} ({status})")

        # Free memory periodically
        if i % 100 == 0:
            gc.collect()

    print(f"\n=== Done! Downloaded: {total_downloaded}, "
          f"Skipped: {total_skipped}, Failed: {total_failed} ===")


if __name__ == "__main__":
    main()
