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
    ap.add_argument("--creative", action="store_true",
                    help="CREATIVE mode: Claude Opus directs the reel (per-scene Veo 3.1 "
                         "prompts + voice-over) from the identity + real photos. Veo 3.1 "
                         "brings each real photo to life; OpenAI TTS narrates.")
    ap.add_argument("--no-voiceover", action="store_true",
                    help="skip the AI voice-over narration (default: Gemini TTS narrates "
                         "each scene's on-screen text; runs on GCP credits)")
    ap.add_argument("--headline", default=None,
                    help="override the reel headline (e.g. a planned content-calendar hook).")
    ap.add_argument("--from-plan", default=None,
                    help="a content_plan.json (from `python -m strategy`) to drive this reel.")
    ap.add_argument("--item", type=int, default=0,
                    help="with --from-plan: which calendar item index to render (default 0).")
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

    # Loop closure: a content-calendar item (from `python -m strategy`) can drive the
    # reel — its hook (else topic) becomes the headline. --headline overrides directly.
    headline_override = args.headline
    if args.from_plan and not headline_override:
        try:
            plan = json.loads(Path(args.from_plan).read_text(encoding="utf-8"))
            items = plan.get("items") or []
            if items:
                it = items[max(0, min(args.item, len(items) - 1))]
                headline_override = (it.get("hook") or it.get("topic") or "").strip() or None
                print(f"[plan] item {args.item}: {it.get('date')} {it.get('platform')} "
                      f"{it.get('content_type')} -> headline={headline_override!r}", file=sys.stderr)
        except Exception as exc:
            print(f"   (could not read --from-plan: {type(exc).__name__})", file=sys.stderr)

    brief = build_reel_brief(profile, headline_override=headline_override)

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

    out = Path(args.out) if args.out else Path("outputs/reels") / f"{profile_path.stem}.mp4"

    # CREATIVE MODE: Opus directs + Veo 3.1 executes + TTS narrates. Falls through to
    # the deterministic storyboard below if Opus can't design a reel (no key / no photos).
    if args.creative:
        from reel.creative import render_creative_reel
        photos = selected if selected is not None else \
            ((profile.get("visual") or {}).get("content_images") or [])
        provider = StubVideoProvider() if args.no_video else default_video_provider()
        print(f"[creative] Opus directing {args.frames} scenes from {len(photos)} real photos; "
              f"provider={provider.name}", file=sys.stderr)
        result, creative = render_creative_reel(
            profile, brief, photos, provider=provider, out_path=out,
            n_scenes=max(3, args.frames), scale=args.scale,
            include_logo=not args.no_logo, music_path=args.music,
            with_voiceover=not args.no_voiceover,
        )
        if result is not None:
            print(f"\n[ok] CREATIVE reel -> {Path(result.reel_path).resolve()}")
            print(f"     concept: {creative.concept[:90]}")
            print(f"     {result.width}x{result.height}  {result.duration_s}s  "
                  f"audio={result.has_audio}  provider={result.provider}")
            return 0
        print("   [creative] Opus could not design a reel; falling back to storyboard.",
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

    print(f"[reel] {storyboard.business_name}  dir={storyboard.primary_dir}  "
          f"scenes={len(storyboard.scenes)}  total={storyboard.total_duration_s}s  "
          f"provider={provider.name}", file=sys.stderr)
    for w in storyboard.warnings:
        print(f"   warning: {w}", file=sys.stderr)

    # Voice-over: narrate each scene's verbatim on-screen text (grounded). Defaults to
    # Gemini TTS (same GCP credits as Imagen/Veo); --no-voiceover renders silent.
    voiceover_path = None
    if not args.no_voiceover:
        from reel.voiceover import synth_voiceover, narration_lines
        nlines = narration_lines(storyboard)
        if any(nlines):
            print(f"[voiceover] synthesizing narration "
                  f"({sum(1 for l in nlines if l)} lines)...", file=sys.stderr)
            voiceover_path = synth_voiceover(
                nlines, [s.duration_s for s in storyboard.scenes],
                Path(out).with_suffix(".vo.m4a"),
            )
            print(f"   voiceover -> {voiceover_path}" if voiceover_path
                  else "   (voiceover unavailable; rendering silent)", file=sys.stderr)

    result = render_reel(
        storyboard, provider=provider, out_path=out,
        scale=args.scale, music_path=args.music, voiceover_path=voiceover_path,
        include_logo=not args.no_logo,
    )

    print(f"\n[ok] reel -> {Path(result.reel_path).resolve()}")
    print(f"     {result.width}x{result.height}  {result.duration_s}s  "
          f"audio={result.has_audio}  provider={result.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
