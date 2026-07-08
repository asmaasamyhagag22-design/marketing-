"""Gemini 2.5 Pro creative director (reel.creative_director).

The Gemini vision call needs creds + network; these tests cover the deterministic
parts: identity-block assembly, JSON parsing, and honest-degrade. The "designs a
real creative reel" behaviour is shown by the live elkbabgi run.
"""
from __future__ import annotations

from reel.creative_director import (
    _identity_block, _safe_json_object, _system_prompt, _vertical_mode, design_creative_reel,
)


def _no_gemini_creds(monkeypatch):
    for k in ("GOOGLE_CLOUD_PROJECT", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def _profile():
    return {
        "name": {"value": "Qasr Elkbabgi"},
        "category": {"value": "restaurant"},
        "description": {"value": "An Egyptian grill."},
        "offerings": [{"name": "grilled dishes"}],
        "languages": ["ar", "en"],
    }


def test_identity_block_has_core_fields():
    b = _identity_block(_profile())
    assert "Qasr Elkbabgi" in b
    assert "grilled dishes" in b


def test_safe_json_object_strips_fences_and_handles_garbage():
    assert _safe_json_object('```json\n{"scenes":[]}\n```') == {"scenes": []}
    assert _safe_json_object("not json") is None


def test_no_caller_degrades_to_none(monkeypatch):
    # No Gemini caller (bare env) -> honest None even with valid photo URLs.
    _no_gemini_creds(monkeypatch)
    assert design_creative_reel(_profile(), ["https://x.com/a.jpg"]) is None


def test_no_photos_returns_none():
    # The no-photos guard fires before any caller is consulted.
    assert design_creative_reel(_profile(), []) is None


def test_injected_caller_builds_a_reel_from_scenes(monkeypatch):
    # A fake caller + a fake image fetch exercise the full parse path hermetically (no network).
    import reel.creative_director as cd
    from reel.creative_director import CreativeScene, _ReelResponse
    from business_profile.llm.caller import Usage

    monkeypatch.setattr(cd, "_image_parts",
                        lambda urls, *, max_images, max_side=640: ([(b"IMG", "image/jpeg")], list(urls)[:1]))

    captured = {}
    def caller(system, user, response_model, group_name="", images=None):
        captured["images"] = images
        captured["group"] = group_name
        return (_ReelResponse(concept="c", hook="h", cta="Book now", language="en",
                              scenes=[CreativeScene(image_index=9, veo_prompt="a person uses it",
                                                    voiceover="vo", on_screen_text="Book now", duration_s=3.0)]),
                Usage(model="gemini-2.5-pro"))
    reel = design_creative_reel(_profile(), ["https://x.com/a.jpg"], caller=caller)
    assert reel is not None and reel.model == "gemini-2.5-pro" and reel.cta == "Book now"
    assert reel.scenes[0].image_index == 0            # clamped into range (was 9, only 1 photo)
    assert captured["images"] == [(b"IMG", "image/jpeg")]   # photos passed as Gemini image parts
    assert captured["group"] == "creative_director"


# ---------------------------------------------------------------------
# Tone/vertical-aware direction (item 5: "show the jewelry WORN + elegance,
# tell the real story, minimal text"). The old prompt hard-coded FOOD dynamics
# into every reel.
# ---------------------------------------------------------------------

def test_vertical_mode_maps_brand_to_mode():
    assert _vertical_mode({"category": {"value": "restaurant"}}) == "food"
    assert _vertical_mode({"category": {"value": "jewelry"}}) == "elegant"
    assert _vertical_mode({"category": {"value": "fashion"}}) == "elegant"
    # a luxury TONE makes a NON-beauty vertical elegant (e.g. a jeweller tagged generic 'ecommerce')
    assert _vertical_mode({"category": {"value": "ecommerce"},
                           "tone_of_voice": {"value": "luxury"}}) == "elegant"
    assert _vertical_mode({"category": {"value": "clinic"}}) == "generic"
    # a haircare/skincare brand (often just 'ecommerce') is detected as BEAUTY from its offerings
    assert _vertical_mode({"category": {"value": "ecommerce"},
                           "offerings": [{"name": "Hair Care"}, {"name": "Face Care"},
                                         {"name": "Lip Care"}]}) == "beauty"


def test_elegant_prompt_shows_the_piece_worn_alive_not_food():
    p = _system_prompt(5, "ar", "elegant")
    assert "WEARS" in p and ("ALIVE" in p or "alive" in p)     # worn + real movement, not a still
    assert "sizzling" not in p.lower() and "steam" not in p.lower()
    assert "CAPTION-DRIVEN" in p
    assert "AD SPINE" in p and "never invent history" in p and "invent NO facts" in p


def test_food_prompt_keeps_appetising_motion():
    p = _system_prompt(5, "en", "food")
    assert "steam" in p.lower() or "sizzling" in p.lower()
    assert "CAPTION-DRIVEN" in p


def test_every_mode_demands_people_action_and_is_grounded():
    # engineer/owner: the reel was a slow zoom on one still, no people. Every mode must now direct a
    # real PERSON using the product with energy, while the PRODUCT stays exactly as shown (grounded).
    for mode in ("beauty", "elegant", "food", "generic"):
        p = _system_prompt(5, "en", mode)
        assert "PERSON" in p                                   # a human in frame
        assert "NOT a slow zoom" in p                          # the exact defect, forbidden
        assert "stay exactly as shown" in p                    # product grounding preserved
    beauty = _system_prompt(5, "en", "beauty")
    assert "TikTok" in beauty and ("applies" in beauty or "sprays" in beauty)
    # the global directives: distinct photo per scene + a people self-check
    assert "DISTINCT photo" in beauty
    assert "PERSON using/reacting to the product" in beauty


def test_prompt_requires_an_ad_arc_so_the_reel_says_what_it_advertises():
    # Slice 3 (engineer: "I can't tell what it advertises"): the reel MUST name the brand + product
    # + benefit + CTA, be self-explanatory fast, and never drift into a store-kiosk montage.
    p = _system_prompt(5, "en", "generic")
    for beat in ("HOOK", "WHAT IT IS", "BENEFIT", "CTA"):
        assert beat in p, beat
    assert "by scene 2" in p                                  # self-explanatory in the first seconds
    assert "do NOT narrate store" in p and "kiosks" in p      # no vague brand/location montage
    assert "SELF-CHECK" in p and "NAMES the brand" in p       # closing verification


def test_prompt_composes_vertical_first_so_the_product_is_not_cropped():
    # Owner: "الصورة كأنها مقصوصة ... صمم الفريم في الأصل على ريل مش تصغرها". Every reel must be
    # composed for the 9:16 frame from the start so the product is never cut off.
    p = _system_prompt(5, "en", "generic")
    assert "1080x1920" in p and "vertical-first" in p.lower()
    assert "keep the product WHOLE" in p and "ACCIDENTALLY crop" in p
    # an INTENTIONAL macro crop for the hook is distinguished from an accidental one (audit fix)
    assert "DELIBERATE macro crop" in p


def test_prompt_demands_physically_logical_use_not_impossible_actions():
    # Owner: "يكون منطقي مش يضغط والغطا مقفول". Never an impossible action (pressing a sealed pump).
    p = _system_prompt(5, "en", "beauty")
    assert "REMOVES or FLIPS" in p                            # opens the cap/lid BEFORE dispensing
    assert "sealed pump" in p or "closed bottle" in p         # the forbidden impossible action


def test_prompt_uses_craft_bar_brand_register_and_agency_formula():
    # Batch 4: the "15-years-TikTok" persona is replaced by the shared CRAFT BAR + a brand-derived
    # register (so a luxury house and a clinic don't converge on hype pacing); the realism obsession
    # and the SUBJECT+STYLE+CAMERA+LIGHTING+MOTION agency formula are KEPT.
    p = _system_prompt(5, "en", "generic")
    assert "CRAFT BAR" in p                                      # de-primed: the shared bar, not a persona
    assert "SENIOR CREATIVE DIRECTOR" not in p and "15 years" not in p
    assert "REGISTER must MATCH THIS BRAND" in p                 # register derived from the brand
    assert "Do NOT default every brand to high-energy TikTok pacing" in p
    assert "OBSESSED with realism" in p                          # realism emphasis kept
    assert "SUBJECT + STYLE + CAMERA + LIGHTING + MOTION" in p
    assert "Macro close-up" in p or "tracking shot" in p        # explicit camera moves
    assert "soft natural light" in p or "diffused" in p          # explicit lighting
    # a concrete-subject example, not "a person"
    assert "never just 'a person'" in p


def test_prompt_bans_the_dead_agency_words():
    # Owner: replace "Slow zoom"/"Refined"/"Dreamy" with dynamic, real-usage language.
    p = _system_prompt(5, "en", "beauty")
    assert "BANNED WORDS" in p
    for dead in ("slow zoom", "refined", "dreamy"):
        assert dead in p                                         # named so the model avoids them
    assert "dynamic motion" in p or "real-life usage" in p


def test_prompt_engineers_the_hook_and_unifies_the_cta():
    # Hook = first 2s on a proven hook TYPE + a reacting FACE + an intentional MACRO detail (audit
    # resolved the close-up-vs-fully-visible contradiction). CTA = caption AND voiceover say the SAME
    # short action line; product shown mid-use, not at-rest.
    p = _system_prompt(5, "en", "generic")
    assert "FIRST 2 SECONDS" in p and "hook TYPE" in p          # a proven hook type, not just a label
    assert "FACE reacting" in p and "MACRO detail" in p         # face + deliberate macro, not a vague close-up
    assert "SAME short action line" in p                        # caption == voiceover CTA line
    assert "mid-use in a real routine" in p                     # product-in-action, not resting on a shelf


def test_prompt_is_veo_safe_and_grounds_social_proof_and_cta_copy():
    # Audit fixes applied in a Veo-safe way: on-screen text + the brand logo are composited in POST
    # (caption overlay + auto end-card), so the veo_prompt must render NEITHER; social proof only if
    # grounded; the CTA line is written copy but its factual claims stay grounded; and the product's
    # identity survives even while a hand operates it.
    p = _system_prompt(5, "en", "generic")
    assert "AUTO-APPENDS a branded end-card" in p and "Veo renders none" in p
    assert "social proof" in p and "NEVER fabricate ratings" in p
    assert "CTA line is COPY you WRITE" in p and "without inventing fake scarcity" in p
    assert "only its position/pose may change" in p            # identity preserved as the hand operates it


def test_reel_says_what_the_brand_does_varies_scenes_and_paces_captions():
    # Owner's reel feedback, closing the "say what the brand does" point on the reel too:
    # (1) name what the brand DOES + the specific service (works for a service brand, not just a
    # product); (2) the background must CHANGE per scene (not persist behind the person); (3) captions
    # went by too fast + needed MEASURED feeling (not flat, not over-the-top).
    p = _system_prompt(5, "en", "generic")
    # (1) stranger test + services
    assert "STRANGER TEST" in p and "WHAT IT DOES" in p
    assert "PRODUCT OR SERVICE" in p                          # the reel advertises a service, not only a product
    assert "SERVICE being delivered" in p                     # the benefit is shown in the service's real setting
    # (2) per-scene background variety
    assert "SCENE VARIETY" in p and "frozen wallpaper" in p
    # (3) readable pacing + measured feeling
    assert "LONG ENOUGH TO READ" in p and "needs >=3s" in p
    assert "MEASURED" in p and "over-acted" in p


def test_prompt_has_a_physics_logic_check_and_fast_cut_pacing():
    # Owner's "Logic Check": the director must verify every scene is physically possible before
    # returning, and cut at a TikTok pace (2-4s), not linger.
    p = _system_prompt(5, "en", "generic")
    assert "PHYSICALLY POSSIBLE" in p
    assert "do NOT cram" in p                                    # one clear action per scene
    assert "2-4" in p and "FAST TikTok cut" in p


def test_featured_product_makes_the_whole_reel_one_product():
    # Owner: "أنا هعملّ ريل على منتج بعينه مش ميت منتج". When one product is featured, EVERY scene is
    # the SAME product (real photo index 0), varied by shot/action — not a mixed montage.
    p = _system_prompt(5, "en", "generic", featured="Rosemary Hair Oil")
    assert "Rosemary Hair Oil" in p
    assert "SAME product" in p
    assert "ALWAYS 0" in p                                    # every scene reuses the one seed photo
    # the whole-brand default still varies the photo per scene
    montage = _system_prompt(5, "en", "generic")
    assert "DISTINCT photo" in montage and "ALWAYS 0" not in montage
