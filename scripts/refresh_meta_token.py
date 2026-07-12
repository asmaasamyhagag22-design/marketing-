"""Exchange a short-lived Meta token for a LONG-LIVED one (~60 days) and write it back
to .env as IG_ACCESS_TOKEN. Official fb_exchange_token flow — needs the app's own id+secret.

.env inputs:  META_APP_ID, META_APP_SECRET, IG_ACCESS_TOKEN (the fresh short-lived one)
Usage:        python -m scripts.refresh_meta_token
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(".env")
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")
    short = os.environ.get("IG_ACCESS_TOKEN")
    missing = [k for k, v in (("META_APP_ID", app_id), ("META_APP_SECRET", app_secret),
                              ("IG_ACCESS_TOKEN", short)) if not v]
    if missing:
        print("missing in .env:", ", ".join(missing))
        return 2

    params = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": short,
    })
    url = f"https://graph.facebook.com/v21.0/oauth/access_token?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode("utf-8")).get("error", {})
        print("exchange failed:", err.get("message", "")[:200])
        print("(most common cause: the short-lived token itself already expired — "
              "generate a fresh one and run this again right away)")
        return 1

    long_tok = data.get("access_token")
    if not long_tok:
        print("no token in the response")
        return 1
    env = Path(".env")
    text = env.read_text(encoding="utf-8")
    if re.search(r"^IG_ACCESS_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^IG_ACCESS_TOKEN=.*$", f"IG_ACCESS_TOKEN={long_tok}", text, flags=re.M)
    else:
        text += f"\nIG_ACCESS_TOKEN={long_tok}\n"
    env.write_text(text, encoding="utf-8")
    print(f"long-lived token saved to .env (expires_in={data.get('expires_in', '?')}s ≈ 60 days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
