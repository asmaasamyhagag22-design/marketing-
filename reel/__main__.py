"""Reel Studio CLI:  python -m reel <profile.json> [--out reel.mp4]

    python -m reel digilians_profile.json --out reel.mp4
    python -m reel profile.json --no-video                 # offline stub (no Veo/creds)
    python -m reel profile.json --music track.mp3 --scale 0.5   # fast preview w/ music

Builds the verbatim, zero-hallucination storyboard from the profile, generates a
text-free clip per scene (Veo live in your GCP, or the offline stub), then overlays
the RTL/LTR text + logo (rendered by Chromium so Arabic shapes correctly) and muxes
optional music with ffmpeg.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except Exception:
        pass


def main() -> int:
    _load_env()
    import json

    from reel import build_reel_brief, build_storyboard
    from reel.compositor import render_reel
    from reel.video_provider import (
        KenBurnsProvider, StubVideoProvider, default_video_provider,
    )

    ap = argparse.ArgumentParser(description="profile.json -> marketing reel (.mp4)")
    ap.add_argument("profile", help="path to a BusinessProfile JSON")
    ap.add_argument("--out", default=None, help="output .mp4 (default: outputs/reels/<name>.mp4)")
    ap.add_argument("--no-video", action="store_true",
                    help="use the offline stub (brand gradients) instead of Veo")
    ap.add_argument("--real", action="store_true",
                    help="FAITHFUL OFFLINE mode: animate the business's REAL scraped "
                         "photos with Ken Burns (ffmpeg), no AI. Default (no flag) uses "
                         "Veo 3.1 to bring those same real photos to life (image-to-video).")
    ap.add_argument("--frames", type=int, default=10,
                    help="target number of scenes/shots (default 10), bounded by the "
                         "number of real photos the scrape found")
    ap.add_argument("--music", default=None, help="optional audio track to mux (mp3/m4a/wav)")
    ap.add_argument("--scale", type=float, default=1.0, help="resolution scale (0.5 = fast preview)")
    ap.add_argument("--max-seconds", type=float, default=28.0, help="cap total reel length")
    ap.add_argument("--no-logo", action="store_true", help="skip the logo overlay")
    ap.add_argument("--static-scene", action="store_true",
                    help="skip the LLM art-director; use deterministic per-category scenes")
    ap.add_argument("--no-select", action="store_true",
                    help="skip the vision photo-curator (use ALL scraped content images; "
                         "may include partner logos / QR codes / icons)")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.is_file():
        print(f"!! profile not found: {profile_path}", file=sys.stderr)
        return 2
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    # LLM art-director: the scene is derived from the brand persona. Falls back to
    # deterministic per-category templates when no OpenAI key / --static-scene / the
    # call fails (same discipline as the poster).
    caller = None
    if not args.static_scene:
        try:
            from business_profile.llm import OpenAICaller
            caller = OpenAICaller()
        except Exception:
            caller = None

    brief = build_reel_brief(profile)

    # VISION CURATION: show every scraped content image to a vision model with the
    # brand identity and keep ONLY real, on-brand PHOTOS — so partner/sponsor logos,
    # QR codes, icons, and stock graphics never become reel scenes. Off with
    # --no-select; honest-degrades to all images when no OpenAI key.
    selected = None
    if not args.no_select:
        from reel.image_select import select_brand_photos
        raw_photos = (profile.get("visual") or {}).get("content_images") or []
        if raw_photos:
            def _f(k):
                fld = profile.get(k)
                return fld.get("value") if isinstance(fld, dict) else fld
            selected = select_brand_photos(
                raw_photos, business_name=brief.business_name,
                category=str(brief.category or _f("category") or ""),
                description=str(_f("description") or ""),
                max_keep=max(2, args.frames),
            )
            print(f"   [curate] {len(selected)}/{len(raw_photos)} images are real on-brand photos",
                  file=sys.stderr)

    storyboard = build_storyboard(
        brief, profile=profile, caller=caller,
        max_total_s=args.max_seconds, target_scenes=max(2, args.frames),
        selected_images=selected,
    )

    if args.real:
        # FAITHFUL: animate the business's REAL on-page photos (logos excluded
        # upstream) so the reel comes from the actual place. Prefer the full content
        # set; fall back to the single hero, then to a brand gradient.
        real_imgs = list(storyboard.content_images)
        if not real_imgs and storyboard.reference_image_url:
            real_imgs = [storyboard.reference_image_url]
        if real_imgs:
            print(f"   [real] {len(real_imgs)} real photo(s) from the business",
                  file=sys.stderr)
        else:
            print("   warning: --real but the scrape surfaced no real business photo "
                  "(logo only); falling back to a brand gradient.", file=sys.stderr)
        provider = KenBurnsProvider(images=real_imgs, fallback_palette=storyboard.palette_hex)
    elif args.no_video:
        provider = StubVideoProvider()
    else:
        provider = default_video_provider()
    out = Path(args.out) if args.out else Path("outputs/reels") / f"{profile_path.stem}.mp4"

    print(f"[reel] {storyboard.business_name}  dir={storyboard.primary_dir}  "
          f"scenes={len(storyboard.scenes)}  total={storyboard.total_duration_s}s  "
          f"provider={provider.name}", file=sys.stderr)
    for w in storyboard.warnings:
        print(f"   warning: {w}", file=sys.stderr)

    result = render_reel(
        storyboard, provider=provider, out_path=out,
        scale=args.scale, music_path=args.music, include_logo=not args.no_logo,
    )

    print(f"\n[ok] reel -> {Path(result.reel_path).resolve()}")
    print(f"     {result.width}x{result.height}  {result.duration_s}s  "
          f"audio={result.has_audio}  provider={result.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
