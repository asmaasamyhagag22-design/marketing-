"""
check_places_403.py -- minimal connectivity test for Google Places API (New).

Answers ONE question: is the 403 gone or not?

Lives in competitor/. Run it any of these ways -- it finds .env on its own:

    python -m competitor.check_places_403          # from the project root
    python competitor/check_places_403.py          # from the project root
    python check_places_403.py                     # from inside competitor/

It does a single raw HTTP call (no wrapper, no scraper, no scoring) so the
HTTP status and Google's error reason come through untouched. Output is pure
ASCII on purpose -- avoids the cp1252 console crash on Windows.
"""
import json
import os
import sys
from pathlib import Path

import requests


def _read_key_from_env_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, val = line.partition("=")
                if name.strip() == "GOOGLE_MAPS_API_KEY":
                    return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def load_key():
    """GOOGLE_MAPS_API_KEY from env, else hunt for a .env upward from both the
    current directory and this file's directory -- so placement and run
    location don't matter."""
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    seen = set()
    for root in (Path.cwd(), Path(__file__).resolve().parent):
        for folder in (root, *root.parents):
            env_path = folder / ".env"
            if env_path in seen:
                continue
            seen.add(env_path)
            found = _read_key_from_env_file(env_path)
            if found:
                return found
    return None


def main():
    key = load_key()
    if not key:
        print("[FAIL] GOOGLE_MAPS_API_KEY not found (not in env, no .env up the tree).")
        print("       -> make sure the key is set in your project-root .env.")
        return 2

    print("[..]  key loaded (len=%d). hitting Places API (New) Text Search...\n" % len(key))

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.id,places.displayName",
    }
    body = {"textQuery": "coffee shop in Cairo"}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20)
    except requests.RequestException as e:
        print("[ERROR] network error (this is NOT a 403): %s" % e)
        return 3

    print("HTTP %s\n" % resp.status_code)

    if resp.status_code == 200:
        data = resp.json()
        places = data.get("places", []) or []
        first = "-"
        if places:
            first = places[0].get("displayName", {}).get("text", "-")
        print("[OK]  RESOLVED. Places API (New) is working. Got %d results (e.g. '%s')."
              % (len(places), first))
        print("      -> discovery will run live. Next: python -m competitor.live_test --debug")
        return 0

    if resp.status_code == 403:
        print("[BLOCKED] STILL 403. Google says:\n")
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=True))
        except ValueError:
            print(resp.text[:2000])
        print("\n      Usual causes (the JSON above tells you which one):")
        print("      * Places API (New) not ENABLED on the project -> enable it in Cloud Console")
        print("      * BILLING not enabled on the project -> turn billing on")
        print("      * API key RESTRICTED -> allow 'Places API (New)' on that key")
        return 1

    print("[WARN] unexpected status. Body:\n")
    print(resp.text[:2000])
    return 1


if __name__ == "__main__":
    sys.exit(main())