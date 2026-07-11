"""Product-first ranking of content_images (business_profile/rules/from_visual.py).

Root cause the analysis found: `_content_images` sorted by file extension (.jpg/.webp first, .png
last), so a brand whose STORE-LOCATION photos are webp/jpg (Mall of Arabia, City Stars, pharmacy)
and whose real PRODUCT mockups are .png ended up with content_images = mostly store fronts. The reel
then animated kiosks while the voice-over sold products = incoherent. Now content_images are ranked
PRODUCT-first (store/stockist/banner tokens demoted). Hermetic: no network.
"""
from __future__ import annotations

from types import SimpleNamespace

from business_profile.rules.from_visual import _content_images, _content_rank
from scraper.schemas import ImageRole


def test_rank_demotes_stores_and_banners_promotes_products():
    assert _content_rank("https://b/cdn/Mall_of_Arabia.webp", "Mall of Arabia") == 2
    assert _content_rank("https://b/cdn/El-Ezaby-Pharmacy.webp", "") == 2
    assert _content_rank("https://b/cdn/web_banner_2.webp", "slide 1") == 2
    assert _content_rank("https://b/cdn/IMG_0502.png", "Floral Blast Hair Mist") == 0   # product alt
    assert _content_rank("https://b/products/hair-mist.jpg", "") == 0                   # product page
    assert _content_rank("https://b/cdn/misc.png", "") == 1                             # neutral


def _im(src, alt=""):
    return SimpleNamespace(role=ImageRole.CONTENT, src=src, alt=alt)


def test_content_images_lists_products_before_store_photos():
    manifest = SimpleNamespace(visual=None, images_of_interest=[
        _im("https://b/cdn/Mall_of_Arabia.webp", "Mall of Arabia"),      # store
        _im("https://b/cdn/floral-blast.png", "Floral Blast Hair Mist"), # product
        _im("https://b/cdn/City_stars.webp", "City Stars branch"),       # store
        _im("https://b/cdn/face-wash.png", "Face Wash"),                 # product
    ])
    out = _content_images(manifest)
    # both products rank ahead of both store photos
    assert out.index("https://b/cdn/floral-blast.png") < out.index("https://b/cdn/Mall_of_Arabia.webp")
    assert out.index("https://b/cdn/face-wash.png") < out.index("https://b/cdn/City_stars.webp")
    assert out[0] in ("https://b/cdn/floral-blast.png", "https://b/cdn/face-wash.png")


def test_cap_keeps_products_when_stores_would_overflow():
    # 12 store photos + 2 products: the 2 products must survive the limit=12 cap (they rank first).
    imgs = [_im(f"https://b/cdn/mall_{i}.webp", "mall branch") for i in range(12)]
    imgs += [_im("https://b/cdn/prod-a.png", "Hair Mist"), _im("https://b/cdn/prod-b.png", "Face Wash")]
    out = _content_images(SimpleNamespace(visual=None, images_of_interest=imgs), )
    assert "https://b/cdn/prod-a.png" in out and "https://b/cdn/prod-b.png" in out


def test_ui_and_partner_alts_no_longer_lead():
    # FIX-B (nti regression): 'ANY non-empty alt -> rank 0' let a help screenshot, a partners
    # logo-wall and a 3-char alt LEAD content_images. A rank-0 alt must read like an item NAME.
    assert _content_rank("https://b/img/help.png", "Create User Profile") == 1
    assert _content_rank("https://b/img/partners-6m-1.png", "Industry Partners") == 1
    assert _content_rank("https://b/img/eme1.jpg", "eme") == 1                # too short
    assert _content_rank("https://b/img/oil.png", "Hair Growth Oil") == 0     # real name still leads


def test_unknown_logo_candidates_survive_as_content_photos():
    # FIX-B (nti regression): real facility photos sat in visual.logo_candidates as low-score
    # 'unknown_candidate' entries and were silently dropped from content_images. Only candidates
    # CLASSIFIED as logos are excluded now.
    visual = SimpleNamespace(
        primary_logo=SimpleNamespace(src="https://b/images/logo.png"),
        logo=None, partner_logos=[], authority_logos=[],
        logo_candidates=[
            SimpleNamespace(src="https://b/images/about/acadmy.jpg",
                            classification="unknown_candidate", score=20.0),
            SimpleNamespace(src="https://b/images/logo-alt.png",
                            classification="primary_brand_logo", score=90.0),
        ],
    )
    manifest = SimpleNamespace(visual=visual, images_of_interest=[
        _im("https://b/images/about/acadmy.jpg", "students in the academy lab"),
        _im("https://b/images/logo-alt.png", "brand logo"),
        _im("https://b/images/logo.png", ""),
    ])
    out = _content_images(manifest)
    assert "https://b/images/about/acadmy.jpg" in out          # the real photo SURVIVES
    assert "https://b/images/logo-alt.png" not in out          # classified logo excluded
    assert "https://b/images/logo.png" not in out              # primary logo excluded
