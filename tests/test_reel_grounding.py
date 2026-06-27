"""Reel copy grounding — Step 1 read-only audit (hermetic, no live LLM).

Proves the primitive APPLIES the Evidence Ledger to the reel's copy surfaces: a fabricated
falsifiable claim in an Opus `CreativeReel` (spoken voiceover / displayed caption) is flagged
UNSOURCED, grounded/paraphrase copy passes, and the DEFAULT verbatim-narration path is clean
(the deterministic floor — the gate must not false-positive on grounded reel copy).
"""
from __future__ import annotations

from reel.creative_director import CreativeReel, CreativeScene
from reel.grounding import audit_reel_copy, creative_reel_copy_fields, narration_copy_fields
from reel.schemas import ReelScene, Storyboard


def _ef(value, quote, url="https://brand.example/p", conf="high"):
    return {"value": value, "evidence": [{"block_id": "b", "page_url": url, "quote": quote,
            "extractor": "llm"}], "confidence": conf, "source_type": "extracted"}


# Arabic brand: evidence supports 'الرواد' (pioneer/first) + '5000', but NOTHING about a
# certification ('معتمد') or an 'الأكبر' (largest) / 'since 1850' claim.
_AR_GROUNDED = {
    "name": _ef("Digilians", "Digilians"),
    "languages": ["ar"],
    "tagline": _ef("الرواد الرقميون", "الرواد الرقميون"),
    "description": _ef("ندرّب 5000 شاب سنويًا في البرمجة", "ندرّب 5000 شاب سنويًا في البرمجة"),
    "offerings": [],
}


def _has_unsourced(profile, fields) -> bool:
    return audit_reel_copy(profile, fields).total_unsourced > 0


def test_copy_fields_collects_customer_facing_only():
    # Customer-facing copy is captured; internal production fields are NOT.
    reel = CreativeReel(
        concept="internal idea", hook="هوك", cta="سجّل", music_mood="upbeat",
        scenes=[CreativeScene(image_index=0, veo_prompt="INTERNAL camera dolly",
                              voiceover="سطر صوتي", on_screen_text="تعليق")],
    )
    fields = creative_reel_copy_fields(reel)
    assert fields["hook"] == "هوك" and fields["cta"] == "سجّل"
    assert fields["voiceover_0"] == "سطر صوتي" and fields["caption_0"] == "تعليق"
    assert "INTERNAL camera dolly" not in " ".join(fields.values())
    assert not any(k.startswith(("concept", "music", "veo")) for k in fields)


def test_fabricated_creative_copy_is_flagged_unsourced():
    # 'أكبر' (largest) + 'معتمد' (certified) + 'منذ 1850' are nowhere in the evidence.
    reel = CreativeReel(scenes=[
        CreativeScene(image_index=0, veo_prompt="p", voiceover="أكبر مركز تدريب معتمد في مصر"),
        CreativeScene(image_index=0, veo_prompt="p", on_screen_text="منذ 1850"),
    ])
    assert _has_unsourced(_AR_GROUNDED, creative_reel_copy_fields(reel))


def test_grounded_creative_copy_passes():
    # 'روّاد' resolves via tagline 'الرواد'; '5000' via description; the rest is paraphrase.
    reel = CreativeReel(hook="روّاد الرقمنة", scenes=[
        CreativeScene(image_index=0, veo_prompt="p", voiceover="ندرّب 5000 شاب"),
        CreativeScene(image_index=0, veo_prompt="p", on_screen_text="تدريب عملي"),
    ])
    assert not _has_unsourced(_AR_GROUNDED, creative_reel_copy_fields(reel))


def test_subjective_puffery_passes():
    # 'تجربة راقية' asserts nothing checkable -> allowed (copy stays alive).
    reel = CreativeReel(scenes=[CreativeScene(image_index=0, veo_prompt="p",
                                              voiceover="تجربة راقية تقربك أكتر")])
    assert not _has_unsourced(_AR_GROUNDED, creative_reel_copy_fields(reel))


def test_default_narration_floor_is_clean():
    # The verbatim narration path: every spoken line is real selected copy -> 0 unsourced.
    storyboard = Storyboard(business_name="Digilians", scenes=[
        ReelScene(kind="intro", duration_s=3.5, visual_prompt="p",
                  headline="الرواد الرقميون", source_field="headline"),
        ReelScene(kind="offering", duration_s=3.0, visual_prompt="p",
                  sublines=["تدريب عملي"], source_field="offerings"),
        ReelScene(kind="value_prop", duration_s=4.0, visual_prompt="p",
                  sublines=["ندرّب 5000 شاب"], source_field="subheadline"),
        ReelScene(kind="outro", duration_s=3.0, visual_prompt="p",
                  headline="Digilians", cta_text="سجّل الآن", source_field="name/cta"),
    ])
    fields = narration_copy_fields(storyboard)
    assert fields  # narration was produced
    assert audit_reel_copy(_AR_GROUNDED, fields).total_unsourced == 0
