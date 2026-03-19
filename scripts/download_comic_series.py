#!/usr/bin/python3
"""
Download all covers for a specific comic series from the Metron API.
Can be run interactively or non-interactively via args.
Supports resume - re-run safely to pick up where you left off.

Requires /home/pi/.metron_credentials

Usage:
    python3 download_comic_series.py                              # interactive
    python3 download_comic_series.py --id <series_id> --title "Batman"  # from web
"""

import os
import sys
import argparse
import requests
import json
import time

BASE_DIR = "/home/pi/inkslab-collections/comics"
CREDENTIALS_FILE = "/home/pi/.metron_credentials"
API_BASE = "https://metron.cloud/api"

API_DELAY = 4.0
DOWNLOAD_DELAY = 0.5
COOLDOWN_EVERY = 50
COOLDOWN_SECONDS = 15

HEADERS = {
    'User-Agent': 'InkSlab/1.0 (https://github.com/costamesatechsolutions/inkslab-eink-tcg-display)',
    'Accept': 'application/json',
}


def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: Credentials file not found: {CREDENTIALS_FILE}")
        return None, None
    creds = {}
    with open(CREDENTIALS_FILE) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                creds[key.strip()] = val.strip()
    # Handle encrypted format written by the web UI
    if creds.get('METRON_ENC'):
        try:
            import hashlib, json, base64
            from cryptography.fernet import Fernet
            serial = ''
            try:
                with open('/proc/cpuinfo') as f:
                    for line in f:
                        if line.startswith('Serial'):
                            serial = line.split(':', 1)[1].strip()
                            break
            except Exception:
                pass
            key = base64.urlsafe_b64encode(hashlib.pbkdf2_hmac('sha256', (serial or 'inkslab-device').encode(), b'inkslab-metron-v1', 100000))
            obj = json.loads(Fernet(key).decrypt(creds['METRON_ENC'][4:].encode()))
            return obj['u'], obj['p']
        except Exception as e:
            print(f"ERROR: Failed to decrypt credentials: {e}")
            return None, None
    return creds.get('METRON_USERNAME'), creds.get('METRON_PASSWORD')


def safe_dirname(name):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip()[:60]


def download_file(url, filepath, auth=None):
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


def search_series(query, auth):
    time.sleep(API_DELAY)
    try:
        r = requests.get(f"{API_BASE}/series/", headers=HEADERS, auth=auth,
                         params={"name": query, "page_size": 10}, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"   Search error: {e}")
        return []


def fetch_series_issues(series_id, auth):
    issues = []
    params = {"page": 1, "page_size": 100}
    while True:
        time.sleep(API_DELAY)
        try:
            r = requests.get(f"{API_BASE}/series/{series_id}/issue_list/",
                             headers=HEADERS, auth=auth, params=params, timeout=30)
            if r.status_code == 429:
                print("   Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"   Error fetching issues: {e}")
            break

        results = data.get("results", [])
        issues.extend(results)
        if not data.get("next"):
            break
        params["page"] += 1

    return issues


def fetch_issue_cover(issue_id, auth):
    """Fetch full issue details to get cover image URL."""
    time.sleep(API_DELAY)
    try:
        r = requests.get(f"{API_BASE}/issue/{issue_id}/",
                         headers=HEADERS, auth=auth, timeout=30)
        r.raise_for_status()
        return r.json().get("image", "")
    except Exception:
        return ""


def download_series(series_id, title, auth):
    dirname = safe_dirname(title)
    series_dir = os.path.join(BASE_DIR, dirname)
    os.makedirs(series_dir, exist_ok=True)

    print(f"Fetching issues for: {title}")
    issues = fetch_series_issues(series_id, auth)
    print(f"Found {len(issues)} issues. Downloading covers...\n")

    slim_db = {}
    downloaded = 0
    skipped = 0
    failed = 0

    for i, issue in enumerate(issues):
        issue_id = str(issue["id"])
        number = issue.get("number", "0")
        cover_date = issue.get("cover_date", "")

        # Get cover URL — issue_list may not include image, fetch detail if needed
        image_url = issue.get("image", "")
        if not image_url:
            print(f"  [{i+1}/{len(issues)}] #{number} — fetching cover URL...")
            image_url = fetch_issue_cover(issue_id, auth)

        slim_db[issue_id] = {
            "name": title,
            "number": str(number),
            "rarity": f"#{number}",
            "year": cover_date[:4] if cover_date else "",
        }

        if not image_url:
            print(f"  [{i+1}/{len(issues)}] #{number} — no image, skipping")
            continue

        ext = ".png" if ".png" in image_url.lower() else ".jpg"
        filepath = os.path.join(series_dir, f"{issue_id}{ext}")
        status = download_file(image_url, filepath, auth)

        if status == "DOWNLOADED":
            downloaded += 1
            print(f"  [{i+1}/{len(issues)}] #{number} — downloaded")
            time.sleep(DOWNLOAD_DELAY)
            if downloaded % COOLDOWN_EVERY == 0:
                print(f"  [Cooldown {COOLDOWN_SECONDS}s...]")
                time.sleep(COOLDOWN_SECONDS)
        elif status == "EXISTS":
            skipped += 1
            print(f"  [{i+1}/{len(issues)}] #{number} — exists")
        else:
            failed += 1
            print(f"  [{i+1}/{len(issues)}] #{number} — FAILED ({status})")

    # Save _data.json
    data_file = os.path.join(series_dir, "_data.json")
    existing = {}
    if os.path.exists(data_file):
        try:
            with open(data_file) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(slim_db)
    with open(data_file, "w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # Update master_index.json
    index_path = os.path.join(BASE_DIR, "master_index.json")
    master_index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path) as f:
                master_index = json.load(f)
        except Exception:
            pass
    # Extract year from title if present e.g. "Batman (2024)"
    import re as _re
    year_match = _re.search(r'\((\d{4})\)', title)
    series_year = year_match.group(1) if year_match else ""
    master_index[dirname] = {"name": title, "year": series_year, "id": series_id}
    with open(index_path, "w") as f:
        json.dump(master_index, f, ensure_ascii=False, indent=2)

    print(f"\n=== Done! {title} — Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed} ===")


def interactive_mode(auth):
    query = input("Enter comic series to search for: ").strip()
    if not query:
        print("No title entered, exiting.")
        return

    print(f"\nSearching for '{query}'...")
    results = search_series(query, auth)
    if not results:
        print("No results found.")
        return

    print(f"\nFound {len(results)} result(s):\n")
    for i, series in enumerate(results):
        pub = series.get("publisher", {}).get("name", "?")
        year = series.get("year_began", "?")
        count = series.get("issue_count", "?")
        print(f"  [{i+1}] {series['name']} ({year}) — {pub}, {count} issues")

    print()
    choice = input(f"Enter number (1-{len(results)}), or 0 to cancel: ").strip()
    try:
        idx = int(choice) - 1
        if idx == -1:
            print("Cancelled.")
            return
        if not (0 <= idx < len(results)):
            print("Invalid choice.")
            return
    except ValueError:
        print("Invalid input.")
        return

    selected = results[idx]
    download_series(selected["id"], selected["name"], auth)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Metron series ID")
    parser.add_argument("--title", help="Series title")
    args = parser.parse_args()

    username, password = load_credentials()
    if not username:
        return

    auth = (username, password)
    os.makedirs(BASE_DIR, exist_ok=True)

    print("   Click 'Stop Download' in the web UI to stop (you can resume later).\n")
    if args.id and args.title:
        print(f"=== Metron Comic Series Downloader: {args.title} ===\n")
        download_series(args.id, args.title, auth)
    else:
        print("=== Metron Comic Series Downloader ===\n")
        interactive_mode(auth)


if __name__ == "__main__":
    main()
