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
                    help="FAITHFUL mode: animate the business's REAL scraped photo "
                         "(Ken Burns), no AI-invented scenes. Falls back to a brand "
                         "gradient if the scrape found no real photo (only a logo).")
    ap.add_argument("--music", default=None, help="optional audio track to mux (mp3/m4a/wav)")
    ap.add_argument("--scale", type=float, default=1.0, help="resolution scale (0.5 = fast preview)")
    ap.add_argument("--max-seconds", type=float, default=20.0, help="cap total reel length")
    ap.add_argument("--no-logo", action="store_true", help="skip the logo overlay")
    ap.add_argument("--static-scene", action="store_true",
                    help="skip the LLM art-director; use deterministic per-category scenes")
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
    storyboard = build_storyboard(brief, profile=profile, caller=caller, max_total_s=args.max_seconds)

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
