"""Baseera dashboard — a self-contained HTML view of a full brand analysis.

`build_dashboard()` reads the analysis artifacts a run produces (business profile, the
competitor + SWOT + TOWS result, the content calendar, and the rendered poster) and emits ONE
beautiful, self-contained HTML page in the Baseera design language — no server, no external
CDN/fonts (so it opens anywhere and can be shared as-is). It "prints everything": the brand
profile, the cited SWOT, the discovered competitors, the TOWS strategies, the content calendar,
and the creative. Every SWOT/strategy line carries its citation — the moat, on screen.

CLI:  python -m dashboard <competitor_result.json> [--profile p.json] [--plan plan.json]
                          [--poster poster.png] [--out dashboard.html]
"""
from .build import build_dashboard

__all__ = ["build_dashboard"]
