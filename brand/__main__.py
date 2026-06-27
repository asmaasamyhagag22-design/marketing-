"""Brand Book CLI:  python -m brand <profile.json> [--out brandbook.json]

Builds the one-time, multimodal brand reference: a powerful model (Gemini, Vertex)
LOOKS at the brand's real scraped photos + reads the profile + deep web research, and
writes a structured BrandBook the poster/reel read from.

    python -m brand digilians_profile_real.json
    python -m brand profile.json --no-research        # skip web research
    python -m brand profile.json --static             # no LLM (profile-only book)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except Exception:
        pass

    from brand import build_brand_book, save_brand_book

    ap = argparse.ArgumentParser(prog="brand", description="Build a BrandBook from a profile.")
    ap.add_argument("profile", help="path to a BusinessProfile JSON")
    ap.add_argument("--out", default=None, help="output JSON (default: outputs/brandbooks/<name>.json)")
    ap.add_argument("--no-research", action="store_true", help="skip deep web research")
    ap.add_argument("--static", action="store_true", help="no LLM — profile-only book")
    ap.add_argument("--max-images", type=int, default=6, help="max real photos to show the model")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_file():
        print(f"!! profile not found: {profile_path}", file=sys.stderr)
        return 2
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    caller = None
    if not args.static:
        try:
            from business_profile.llm import default_caller
            caller = default_caller(strong=True)   # Gemini (Vertex) -> OpenAI fallback
        except Exception:
            caller = None

    print("[brand] building brand book"
          + (" (vision)" if caller is not None else " (profile-only)") + " ...", file=sys.stderr)
    book = build_brand_book(
        profile, caller=caller, with_research=not args.no_research, max_images=args.max_images,
    )

    out = Path(args.out) if args.out else Path("outputs/brandbooks") / f"{profile_path.stem}.json"
    save_brand_book(book, out)

    vi = book.visual_identity
    print(f"\n[ok] BrandBook -> {out.resolve()}")
    print(f"     brand: {book.business_name}  vision={book.used_vision}  images_seen={len(book.images_seen)}")
    print(f"     aesthetic: {vi.aesthetic[:90]}")
    print(f"     mood: {vi.mood[:80]}")
    print(f"     photography: {vi.photography_style[:80]}")
    print(f"     best background: {vi.best_background_image_url}  (text: {vi.recommended_text_color})")
    print(f"     voice: {book.voice[:80]}")
    print(f"     sourced facts: {len(book.sourced_facts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
