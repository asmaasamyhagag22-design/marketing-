"""Gate: a Next.js/React Server Components 'flight' payload is NOT meaningful content.

Regression origin (2026-07-05 audit): trafilatura's density gate passed serialized RSC
payloads (`1:"$Sreact.fragment" 2:I[56700,[],"default"] ...`) as prose, so 31 nahdi product
pages with ZERO real text blocks were flagged `has_meaningful_content=True` and their junk
was stored as `cleaned_main_text` — inflating the pages-with-text diagnostic and feeding
the readiness / pricing content signals. The junk must be rejected as no usable content.

Hermetic: pure detector, no network / no trafilatura.
"""
from scraper.extractors.content_quality import _looks_like_code_payload, extract_content_quality

# A real nahdi RSC 'flight' payload shape (as trafilatura returned it).
_RSC = ('1:"$Sreact.fragment" 2:I[56700,[],"default"] 3:I[15722,[],"default"] '
        '4:I[56700,[],"LoadingBoundaryProvider"] 6:I[44201,[],"OutletBoundary"] '
        '7:"$Sreact.suspense" 9:I[44201,[],"ViewportBoundary"] b:I[44201,[],"MetadataBoundary"]')

_PROSE = ("Founded in 2010, our clinic offers premium foot care in Cairo. We provide "
          "diabetic screening, nail surgery, and consultations from EGP 500 for patients "
          "across the city, with same-day appointments and experienced specialists.")


def test_rsc_flight_payload_is_detected():
    assert _looks_like_code_payload(_RSC)


def test_marker_only_payload_is_detected():
    assert _looks_like_code_payload('self.__next_f.push([1, "some serialized state"])')
    assert _looks_like_code_payload("window.__NEXT_DATA__ = {props: {...}}")


def test_real_prose_is_not_flagged():
    assert not _looks_like_code_payload(_PROSE)
    assert not _looks_like_code_payload("Best regards from our team. Visit us in Cairo.")


def test_empty_is_not_flagged():
    assert not _looks_like_code_payload("")
    assert not _looks_like_code_payload(None)


def test_extract_content_quality_rejects_an_rsc_page():
    # An HTML page whose only body text is an RSC payload -> (None, False), never meaningful.
    html = f"<html><body><script>self.__next_f.push([1])</script><p>{_RSC}</p></body></html>"
    cleaned, meaningful = extract_content_quality(html, "https://x.example/plp/sale")
    assert meaningful is False
    assert cleaned is None
