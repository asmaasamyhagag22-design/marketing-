"""H5 gate: CTA detection covers the major expansion-market languages, not just EN/AR.

Regression origin (2026-07-05 audit): CTA_VERBS held only English + Arabic, so the one
French site in the corpus (elietop.com) scored cta_candidates=0 across 310 internal links
despite obvious CTAs ("Nous contacter", "En savoir plus", "Panier", "Connectez-vous",
"Continuer les achats") — a universality violation for an "any language" product.

The expansion is MEASURED: it adds CTAs only on the French site and inflates ZERO of the
100+ EN/AR corpus scrapes. The Italian "registrati" was deliberately excluded because it
is a prefix of the English word "Registration" (the startswith rule would false-match).

Hermetic: pure function, no network.
"""
from scraper.extractors.links import _is_cta_anchor


def test_french_ctas_detected():
    for a in ["Nous contacter", "En savoir plus", "Panier", "Connectez-vous",
              "Continuer les achats", "Acheter", "Découvrir",
              "En savoir plus sur la collection Twist"]:
        assert _is_cta_anchor(a), a


def test_other_major_language_ctas_detected():
    for a in ["Comprar ahora", "Contáctanos", "Añadir al carrito",   # es
              "Jetzt kaufen", "Mehr erfahren", "Warenkorb",           # de
              "Acquista ora", "Scopri di più", "Carrello",            # it
              "Saiba mais", "Fale conosco",                           # pt
              "Satın al", "Sepete ekle", "iletişim"]:                 # tr
        assert _is_cta_anchor(a), a


def test_english_registration_not_false_matched_as_italian_cta():
    # "registrati" (it) was excluded because it prefixes "Registration".
    assert not _is_cta_anchor("Registration")
    assert not _is_cta_anchor("Registration for New Learners")


def test_ordinary_content_anchors_still_not_ctas():
    # No false positives on plain nav/content anchors (incl. the French site's nav).
    for a in ["La Marque", "Actualités", "Collections", "About Us", "Our Story",
              "Bagues", "Colliers"]:
        assert not _is_cta_anchor(a), a
