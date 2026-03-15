#!/usr/bin/python3
import os, sys, argparse, requests, json, time, gc

BASE_DIR = "/home/pi/manga_covers"
API_BASE = "https://api.mangadex.org"
CDN_BASE = "https://uploads.mangadex.org"
HEADERS = {'User-Agent': 'InkSlab/1.0', 'Accept': 'application/json'}
API_DELAY = 1.5
DOWNLOAD_DELAY = 0.5
COOLDOWN_EVERY = 50
COOLDOWN_SECONDS = 10
PAGE_SIZE = 100

def download_file(url, filepath):
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

def get_manga_title(manga):
    try:
        titles = manga.get("attributes", {}).get("title", {})
        return (titles.get("en") or titles.get("ja-ro") or
                titles.get("ja") or next(iter(titles.values()), "Unknown"))
    except:
        return "Unknown"

def safe_dirname(title):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return safe.strip()[:60]

def search_manga(query):
    params = {"title": query, "limit": 10,
              "contentRating[]": ["safe", "suggestive", "erotica"],
              "order[relevance]": "desc"}
    time.sleep(API_DELAY)
    try:
        r = requests.get(f"{API_BASE}/manga", headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print(f"   Search error: {e}")
        return []

def fetch_all_covers(manga_id):
    covers = []
    offset = 0
    while True:
        params = {"manga[]": manga_id, "limit": PAGE_SIZE,
                  "offset": offset, "order[volume]": "asc"}
        time.sleep(API_DELAY)
        try:
            r = requests.get(f"{API_BASE}/cover", headers=HEADERS, params=params, timeout=30)
            if r.status_code == 429:
                print("   Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"   Error fetching covers: {e}")
            break
        page = data.get("data", [])
        covers.extend(page)
        total = data.get("total", 0)
        offset += len(page)
        if not page or offset >= total:
            break
    return covers

def download_series(manga_id, title):
    dirname = safe_dirname(title)
    # Fetch series year from API
    series_year = ""
    try:
        import time as _t
        _t.sleep(API_DELAY)
        r = requests.get(f"{API_BASE}/manga/{manga_id}", headers=HEADERS, timeout=30)
        if r.status_code == 200:
            attrs = r.json().get("data", {}).get("attributes", {})
            yr = attrs.get("year")
            if yr:
                series_year = str(yr)
    except Exception:
        pass
    print(f"Fetching all covers for: {title}")
    covers = fetch_all_covers(manga_id)
    # Deduplicate: keep one cover per volume, prefer ja > en > other
    seen_volumes = {}
    for cover in covers:
        vol = cover.get('attributes', {}).get('volume') or '?'
        locale = cover.get('attributes', {}).get('locale', '')
        if vol not in seen_volumes:
            seen_volumes[vol] = cover
        else:
            existing_locale = seen_volumes[vol].get('attributes', {}).get('locale', '')
            # ja wins over everything, en wins over other
            if locale == 'ja':
                seen_volumes[vol] = cover
            elif locale == 'en' and existing_locale != 'ja':
                seen_volumes[vol] = cover
    covers = list(seen_volumes.values())
    covers.sort(key=lambda c: (float(c.get('attributes', {}).get('volume') or 0)))
    if not covers:
        print("No covers found for this manga.")
        return
    print(f"Found {len(covers)} cover(s). Downloading...\n")
    manga_dir = os.path.join(BASE_DIR, dirname)
    os.makedirs(manga_dir, exist_ok=True)
    slim_db = {}
    for cover in covers:
        cover_id = cover["id"]
        cover_attrs = cover.get("attributes", {})
        volume = cover_attrs.get("volume") or "?"
        slim_db[cover_id] = {"name": title, "number": str(volume),
                             "rarity": f"Vol. {volume}" if volume != "?" else "Cover", "year": series_year}
    with open(os.path.join(manga_dir, "_data.json"), "w") as f:
        json.dump(slim_db, f, ensure_ascii=False, indent=2)
    index_path = os.path.join(BASE_DIR, "master_index.json")
    master_index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                master_index = json.load(f)
        except:
            pass
    master_index[dirname] = {"name": title, "year": series_year, "id": manga_id}
    with open(index_path, "w") as f:
        json.dump(master_index, f, ensure_ascii=False, indent=2)
    downloaded = skipped = failed = 0
    for i, cover in enumerate(covers):
        cover_id = cover["id"]
        cover_attrs = cover.get("attributes", {})
        filename = cover_attrs.get("fileName", "")
        volume = cover_attrs.get("volume") or "unknown"
        if not filename:
            failed += 1
            continue
        ext = ".png" if filename.lower().endswith(".png") else ".jpg"
        url = f"{CDN_BASE}/covers/{manga_id}/{filename}"
        filepath = os.path.join(manga_dir, f"{cover_id}{ext}")
        status = download_file(url, filepath)
        if status == "DOWNLOADED":
            downloaded += 1
            print(f"  [{i+1}/{len(covers)}] Vol {volume} — downloaded")
            time.sleep(DOWNLOAD_DELAY)
            if downloaded % COOLDOWN_EVERY == 0:
                print(f"  [Cooldown {COOLDOWN_SECONDS}s...]")
                time.sleep(COOLDOWN_SECONDS)
        elif status == "EXISTS":
            skipped += 1
            print(f"  [{i+1}/{len(covers)}] Vol {volume} — already exists")
        else:
            failed += 1
            print(f"  [{i+1}/{len(covers)}] Vol {volume} — FAILED ({status})")
    print(f"\n=== Done! {title} — Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed} ===")

def interactive_mode():
    query = input("Enter manga title to search for: ").strip()
    if not query:
        print("No title entered, exiting.")
        return
    print(f"\nSearching for '{query}'...")
    results = search_manga(query)
    if not results:
        print("No results found.")
        return
    print(f"\nFound {len(results)} result(s):\n")
    for i, manga in enumerate(results):
        title = get_manga_title(manga)
        attrs = manga.get("attributes", {})
        print(f"  [{i+1}] {title} ({attrs.get('year','?')}) — {attrs.get('status','?').title()}")
    print()
    choice = input(f"Enter number (1-{len(results)}), or 0 to cancel: ").strip()
    try:
        choice_idx = int(choice) - 1
        if choice_idx == -1:
            print("Cancelled.")
            return
        if not (0 <= choice_idx < len(results)):
            print("Invalid choice.")
            return
    except ValueError:
        print("Invalid input.")
        return
    selected = results[choice_idx]
    download_series(selected["id"], get_manga_title(selected))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="MangaDex manga ID")
    parser.add_argument("--title", help="Manga title")
    args = parser.parse_args()
    os.makedirs(BASE_DIR, exist_ok=True)
    if args.id and args.title:
        print(f"=== MangaDex Series Downloader: {args.title} ===\n")
        download_series(args.id, args.title)
    else:
        print("=== MangaDex Series Cover Downloader ===\n")
        interactive_mode()

if __name__ == "__main__":
    main()
