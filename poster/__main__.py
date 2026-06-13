"""Step 1 CLI: a BusinessProfile JSON -> a viewable poster PNG.

    python -m poster <business_profile.json> --out poster.png
    python -m poster <business_profile.json> --out poster.png --no-image

Pipeline: load .env (Vertex project/location) -> build the brief from the profile
-> generate a TEXT-FREE Imagen background -> render the final poster via headless
Chromium (Playwright). No Pillow. --no-image swaps Imagen for a palette gradient
so you can iterate on layout without spending on image generation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except Exception:
        pass


def main() -> int:
    _load_env()

    ap = argparse.ArgumentParser(
        prog="poster", description="Generate a poster from a BusinessProfile JSON."
    )
    ap.add_argument("profile", help="path to a business_profile.json")
    ap.add_argument("--out", default="outputs/posters/poster.png", help="output PNG path")
    ap.add_argument(
        "--no-image", action="store_true",
        help="skip Imagen; use a brand-palette gradient background (fast/free).",
    )
    ap.add_argument(
        "--static-concept", action="store_true",
        help="skip the LLM art-director; use the static creative concept prompt.",
    )
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_file():
        print(f"!! profile not found: {profile_path}", file=sys.stderr)
        return 2

    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    from poster.from_profile import build_poster_brief
    from poster.template import render_poster_html
    from poster.render_playwright import render_html_to_png

    print("[1/3] building brief from profile...")
    brief = build_poster_brief(profile)

    print("[2/3] generating background...")
    # Swappable ImageProvider: stub (offline, no credits) vs real Vertex/Imagen.
    if args.no_image:
        from poster.imagen_provider import StubImageProvider

        provider = StubImageProvider()
        bg_path = str(provider.generate(""))           # prompt ignored by the stub
    else:
        from poster.art_director import build_llm_concept_prompt
        from poster.imagen_provider import VertexImagenProvider

        # LLM art-director invents a unique, text-free concept (falls back to the
        # static creative prompt if no OpenAI key / --static-concept).
        caller = None
        if not args.static_concept:
            try:
                from business_profile.llm import OpenAICaller
                caller = OpenAICaller()
            except Exception:
                caller = None
        prompt = build_llm_concept_prompt(brief, caller, profile=profile)
        provider = VertexImagenProvider()
        bg_path = str(provider.generate(prompt))
    print(f"      provider={provider.name} -> {bg_path}")

    print("[3/3] rendering poster (Playwright -> PNG)...")
    html = render_poster_html(brief, bg_path)
    out = render_html_to_png(html, args.out)
    print("DONE ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
