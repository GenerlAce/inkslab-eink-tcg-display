#!/usr/bin/python3
"""
Download all cards for a specific Pokemon name across all sets.
Usage: python3 download_pokemon_bulk.py --name "Pikachu"
"""
import os, sys, argparse, requests, json, time, random
import sys as _sys; _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); del _sys
from download_utils import MIN_FREE_SPACE_MB, check_disk_space, download_file

BASE_DIR = "/home/pi/pokemon_cards"
SETS_URL = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/sets/en.json"
CARDS_BASE_URL = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/cards/en/"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True, help='Pokemon name e.g. "Pikachu"')
    args = parser.parse_args()
    target = args.name.strip().lower()

    os.makedirs(BASE_DIR, exist_ok=True)
    print("   Click 'Stop Download' in the web UI to stop (you can resume later).\n")
    print(f"=== Pokemon Bulk Downloader: {args.name} ===")
    print("Fetching set list...")

    try:
        r = requests.get(SETS_URL, headers=HEADERS, timeout=15)
        sets = r.json()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    master_index = {}
    index_path = os.path.join(BASE_DIR, "master_index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path) as f:
                master_index = json.load(f)
        except Exception:
            pass
    for s in sets:
        master_index[s['id']] = {"name": s['name'], "year": s['releaseDate'][:4]}
    with open(index_path, 'w') as f:
        json.dump(master_index, f)

    downloaded = skipped = failed = found = 0

    for s in sets:
        set_id = s['id']
        set_name = s['name']
        try:
            r = requests.get(f"{CARDS_BASE_URL}{set_id}.json", headers=HEADERS, timeout=15)
            cards = r.json()
        except Exception:
            continue

        matching = [c for c in cards if c.get('name', '').lower() == target]
        if not matching:
            continue

        print(f"[{set_name}] {len(matching)} card(s) found")
        set_dir = os.path.join(BASE_DIR, set_id)
        os.makedirs(set_dir, exist_ok=True)

        data_file = os.path.join(set_dir, "_data.json")
        slim_db = {}
        if os.path.exists(data_file):
            try:
                with open(data_file) as f:
                    slim_db = json.load(f)
            except Exception:
                pass
        for card in cards:
            slim_db[card['id']] = {"name": card.get('name', 'Unknown'), "number": card.get('number', '00'), "rarity": card.get('rarity', 'Common')}
        with open(data_file, 'w') as f:
            json.dump(slim_db, f)

        for card in matching:
            found += 1
            if 'images' not in card:
                continue
            img_url = card['images'].get('large', card['images'].get('small'))
            if not img_url:
                continue
            if not check_disk_space(BASE_DIR):
                print(f"Low disk space! Stopping. Downloaded {downloaded} cards.")
                sys.exit(0)
            filepath = os.path.join(set_dir, f"{card['id']}.png")
            status = download_file(img_url, filepath, HEADERS)
            if status == "DOWNLOADED":
                downloaded += 1
                print(f"  Downloaded: {card['id']}")
                time.sleep(random.uniform(1.0, 2.0))
            elif status == "EXISTS":
                skipped += 1
            else:
                failed += 1
                print(f"  Failed: {card['id']} ({status})")

    print(f"\n=== Done! {args.name}: {found} found, {downloaded} downloaded, {skipped} existed, {failed} failed ===")

if __name__ == "__main__":
    main()
