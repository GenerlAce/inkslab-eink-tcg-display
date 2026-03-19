#!/usr/bin/python3
"""
Download comic book cover images from the Metron API.
Downloads all issues released this week (new comic day = Wednesday).
Organized by series, supports resume.

Requires a free Metron account: https://metron.cloud/accounts/signup/
Credentials stored in /home/pi/.metron_credentials

Usage:
    python3 download_covers_comics.py           # this week's releases
    python3 download_covers_comics.py --weeks 4 # last 4 weeks
    python3 download_covers_comics.py --since 2025-01-01  # since a date
"""

import os
import sys
import argparse
import requests
import json
import time
import datetime
import gc

# --- CONFIGURATION ---
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
        print("Create it with:")
        print("  METRON_USERNAME=yourusername")
        print("  METRON_PASSWORD=yourpassword")
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
    username = creds.get('METRON_USERNAME')
    password = creds.get('METRON_PASSWORD')
    if not username or not password:
        print("ERROR: METRON_USERNAME or METRON_PASSWORD missing from credentials file")
        return None, None
    return username, password


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


def safe_dirname(name):
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip()[:60]


def get_week_range(weeks_back=0):
    """Get date range for new comic day (Wednesday to Wednesday)."""
    today = datetime.date.today()
    # Find most recent Wednesday (weekday 2)
    days_since_wed = (today.weekday() - 2) % 7
    this_wednesday = today - datetime.timedelta(days=days_since_wed)
    # Go back extra weeks if requested
    end_date = this_wednesday - datetime.timedelta(weeks=weeks_back)
    start_date = end_date - datetime.timedelta(weeks=max(1, weeks_back) if weeks_back > 0 else 1)
    return start_date, end_date


def fetch_weekly_issues(date_after, date_before, auth):
    """Fetch all issues released in a date range."""
    issues = []
    params = {
        "store_date_range_after": date_after.isoformat(),
        "store_date_range_before": date_before.isoformat(),
        "page_size": 100,
        "page": 1,
    }

    print(f"   Fetching releases from {date_after} to {date_before}...")

    while True:
        time.sleep(API_DELAY)
        try:
            r = requests.get(f"{API_BASE}/issue/", headers=HEADERS, auth=auth,
                             params=params, timeout=30)
            if r.status_code == 429:
                print("   Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"   Error fetching page {params['page']}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for issue in results:
            if issue.get("image"):
                issues.append(issue)

        total = data.get("count", 0)
        fetched = (params["page"] - 1) * 100 + len(results)
        print(f"   Fetched {len(issues)} issues with covers ({fetched}/{total} total)...")

        if not data.get("next"):
            break
        params["page"] += 1

    return issues


def process_issues(issues):
    """Download covers and save metadata. Returns (downloaded, skipped, failed)."""
    downloaded = 0
    skipped = 0
    failed = 0

    # Group by series
    series_map = {}
    for issue in issues:
        series = issue.get("series", {})
        series_name = series.get("name", "Unknown")
        series_year = str(series.get("year_began", "")) if series.get("year_began") else ""
        series_dirname = safe_dirname(series_name)
        issue_id = str(issue["id"])
        number = issue.get("number", "0")
        cover_date = issue.get("cover_date", "")
        store_date = issue.get("store_date", "")
        image_url = issue.get("image", "")
        publisher = series.get("publisher", {}).get("name", "") if isinstance(series.get("publisher"), dict) else ""

        if series_dirname not in series_map:
            series_map[series_dirname] = {
                "name": series_name,
                "year": series_year,
                "publisher": publisher,
                "issues": {}
            }

        series_map[series_dirname]["issues"][issue_id] = {
            "name": series_name,
            "number": str(number),
            "rarity": f"#{number}",
            "year": cover_date[:4] if cover_date else store_date[:4] if store_date else series_year,
            "image_url": image_url,
        }

    # Save metadata and download images
    for series_dirname, series_data in series_map.items():
        series_dir = os.path.join(BASE_DIR, series_dirname)
        os.makedirs(series_dir, exist_ok=True)

        # Merge with existing _data.json
        slim_db = {}
        data_file = os.path.join(series_dir, "_data.json")
        if os.path.exists(data_file):
            try:
                with open(data_file) as f:
                    slim_db = json.load(f)
            except Exception:
                pass

        for iid, idata in series_data["issues"].items():
            slim_db[iid] = {
                "name": idata["name"],
                "number": idata["number"],
                "rarity": idata["rarity"],
                "year": idata["year"],
            }

        with open(data_file, "w") as f:
            json.dump(slim_db, f, ensure_ascii=False)

        # Download images
        for issue_id, idata in series_data["issues"].items():
            image_url = idata["image_url"]
            if not image_url:
                continue

            ext = ".png" if ".png" in image_url.lower() else ".jpg"
            filepath = os.path.join(series_dir, f"{issue_id}{ext}")
            status = download_file(image_url, filepath)

            if status == "DOWNLOADED":
                downloaded += 1
                print(f"   Downloaded: {idata['name']} #{idata['number']}")
                time.sleep(DOWNLOAD_DELAY)
                if downloaded % COOLDOWN_EVERY == 0:
                    print(f"   [Cooldown {COOLDOWN_SECONDS}s...]")
                    time.sleep(COOLDOWN_SECONDS)
            elif status == "EXISTS":
                skipped += 1
            else:
                failed += 1
                print(f"   Failed: {idata['name']} #{idata['number']} ({status})")

    return downloaded, skipped, failed, series_map


def update_master_index(series_map):
    """Update master_index.json with any new series."""
    index_path = os.path.join(BASE_DIR, "master_index.json")
    master_index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path) as f:
                master_index = json.load(f)
        except Exception:
            pass

    for series_dirname, series_data in series_map.items():
        if series_dirname not in master_index:
            master_index[series_dirname] = {
                "name": series_data["name"],
                "year": series_data["year"],
                "publisher": series_data.get("publisher", ""),
            }

    with open(index_path, "w") as f:
        json.dump(master_index, f, ensure_ascii=False, indent=2)

    return len(master_index)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=1,
                        help="How many weeks back to fetch (default: 1)")
    parser.add_argument("--since", type=str, default=None,
                        help="Fetch all issues since this date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("   Click 'Stop Download' in the web UI to stop (you can resume later).\n")
    print("=== Metron Weekly Comic Cover Downloader ===\n")

    username, password = load_credentials()
    if not username:
        return

    auth = (username, password)
    print(f"Logged in as: {username}")
    print(f"Saving to: {BASE_DIR}\n")

    os.makedirs(BASE_DIR, exist_ok=True)

    # Determine date range
    if args.since:
        try:
            date_after = datetime.date.fromisoformat(args.since)
            date_before = datetime.date.today()
        except ValueError:
            print(f"ERROR: Invalid date format: {args.since}. Use YYYY-MM-DD")
            return
        print(f"Fetching all releases since {date_after}...")
    else:
        date_after, date_before = get_week_range(args.weeks - 1)
        if args.weeks == 1:
            print(f"Fetching this week's new releases (Wednesday {date_after} to {date_before})...")
        else:
            print(f"Fetching last {args.weeks} weeks of releases ({date_after} to {date_before})...")

    print()
    issues = fetch_weekly_issues(date_after, date_before, auth)

    if not issues:
        print("No issues with covers found for this period.")
        return

    print(f"\nFound {len(issues)} issues with covers. Downloading...\n")

    downloaded, skipped, failed, series_map = process_issues(issues)
    index_count = update_master_index(series_map)

    print(f"\nUpdated master_index.json ({index_count} series total)")
    print(f"\n=== Done! Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed} ===")
    if downloaded > 0:
        print(f"New covers saved to: {BASE_DIR}")


if __name__ == "__main__":
    main()
