"""Build the Baseera brand-analysis dashboard as ONE self-contained HTML page.

Self-contained by design: inline CSS, inline SVG, base64 images, a system-font stack (elegant
serif display + clean sans body) — NO external CDN or web fonts — so it opens anywhere and can
be shared/published as-is. Reads whatever artifacts exist and degrades gracefully for the rest.
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# --- Baseera palette (from the design system) ------------------------------------------------
_C = {
    "bg": "#FAF5F1", "surface": "#FFFFFF", "surface2": "#FBF6F2", "ink": "#2A1A1F",
    "inkSoft": "#5C4A52", "muted": "#9B8A92", "line": "rgba(168,69,107,0.12)",
    "blush50": "#FBF0F3", "blush100": "#F6E0E7", "blush200": "#ECCBD6", "blush400": "#C97E96",
    "blush500": "#B85C7A", "blush600": "#9C4564", "blush700": "#7E3450",
    "sand": "#B89873", "sand100": "#F0E4D3", "sage": "#5E9479", "sage100": "#D9E8DF",
    "sage700": "#3F6E55", "teal": "#3F8F8C", "teal100": "#CFE5E2", "gold": "#C68A3C",
    "gold100": "#F5E6C8", "gold700": "#8A5E20", "ok": "#3F8F6B", "warn": "#C68A3C", "bad": "#B54848",
}


def _esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def _val(x: Any) -> Any:
    """Unwrap an EvidencedField-shaped {'value': ...} (possibly nested)."""
    if isinstance(x, dict) and "value" in x:
        return _val(x["value"])
    return x


def _load(path: Optional[str]) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _data_uri(path: Optional[str]) -> Optional[str]:
    if not path or not Path(path).is_file():
        return None
    try:
        mime = mimetypes.guess_type(path)[0] or "image/png"
        b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


# --- small view helpers ----------------------------------------------------------------------
def _kpi(icon: str, value: str, label: str, sub: str, accent: str) -> str:
    return f"""<div class="kpi" style="--a:{accent}">
      <div class="kpi-top"><span class="kpi-ic">{icon}</span></div>
      <div class="kpi-v">{_esc(value)}</div>
      <div class="kpi-l">{_esc(label)}</div>
      <div class="kpi-s">{_esc(sub)}</div>
    </div>"""


_STRENGTH_BADGE = {
    "validated": ("ok", "Validated"), "directional_not_validated": ("warn", "Directional"),
    "internally_supported": ("warn", "Internal"),
}


def _swot_item(it: dict) -> str:
    text = _esc(it.get("text") or it.get("evidence") or "")
    cites = it.get("citation") or []
    cite_html = " · ".join(_esc(c) for c in cites) if cites else "—"
    cls, lab = _STRENGTH_BADGE.get(str(it.get("claim_strength") or ""), ("neutral", str(it.get("claim_strength") or "")))
    badge = f'<span class="cs cs-{cls}">{_esc(lab)}</span>' if lab else ""
    return f"""<li class="swot-item"><div class="swot-t">{text} {badge}</div>
      <div class="swot-c">↳ {cite_html}</div></li>"""


def _swot_quad(title: str, icon: str, items: list, kind: str) -> str:
    body = "".join(_swot_item(it) for it in (items or [])) or '<li class="swot-empty">—</li>'
    return f"""<div class="quad quad-{kind}">
      <div class="quad-h"><span class="quad-ic">{icon}</span>{_esc(title)}
        <span class="quad-n">{len(items or [])}</span></div>
      <ul class="swot-list">{body}</ul></div>"""


def _competitor_card(comp: dict) -> str:
    sel = comp.get("selection") or {}
    cand = comp.get("candidate") or {}
    name = _esc(sel.get("name") or cand.get("name") or "—")
    site = sel.get("website") or cand.get("website") or ""
    site_h = f'<a href="{_esc(site)}" class="comp-site">{_esc(site.replace("https://", "").strip("/"))}</a>' if site else ""
    fit = sel.get("peer_fit_score")
    fit_pct = f"{round(float(fit) * 100)}%" if isinstance(fit, (int, float)) else "—"
    why = _esc(sel.get("why_selected") or "")
    tags = []
    if comp.get("is_local"):
        tags.append('<span class="tag tag-sage">local</span>')
    if comp.get("has_scrapable_site"):
        tags.append('<span class="tag tag-teal">site</span>')
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    return f"""<div class="comp">
      <div class="comp-logo">{_esc(initials)}</div>
      <div class="comp-body"><div class="comp-name">{name} {"".join(tags)}</div>
        {site_h}<div class="comp-why">{why}</div></div>
      <div class="comp-fit"><div class="comp-fit-v">{fit_pct}</div><div class="comp-fit-l">peer fit</div></div>
    </div>"""


_PLAT_ICON = {"instagram": "◎", "tiktok": "♪", "linkedin": "in", "facebook": "f", "youtube": "▶"}


def _calendar_row(it: dict) -> str:
    plat = str(it.get("platform") or "")
    ctype = str(it.get("content_type") or "").replace("_", " ")   # static_post -> static post
    topic = _esc(it.get("topic") or "")
    hook = _esc(it.get("hook") or it.get("angle") or "")
    raw_date = str(it.get("date") or "")
    try:                                              # 2026-07-05 -> Sun 05 Jul (raw on failure)
        date = _esc(datetime.strptime(raw_date, "%Y-%m-%d").strftime("%a %d %b"))
    except Exception:  # noqa: BLE001
        date = _esc(raw_date)
    ic = _PLAT_ICON.get(plat, "•")
    hook_html = f'<div class="cal-hook">“{hook}”</div>' if hook else ""   # no empty quotes
    return f"""<div class="cal-row">
      <div class="cal-date">{date}</div>
      <div class="cal-plat"><span class="cal-ic">{ic}</span>{_esc(plat)} · {_esc(ctype)}</div>
      <div class="cal-body"><div class="cal-topic">{topic}</div>{hook_html}</div>
    </div>"""


def _css() -> str:
    c = _C
    return f"""<style>
    :root{{color-scheme:light;}}
    .bsr *{{margin:0;padding:0;box-sizing:border-box;}}
    .bsr{{
      --serif:'Fraunces',Georgia,'Times New Roman',serif;
      --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
      font-family:var(--sans);color:{c['ink']};background:{c['bg']};
      background-image:
        radial-gradient(circle at 8% 4%,rgba(236,203,214,.35) 0%,transparent 26%),
        radial-gradient(circle at 94% 8%,rgba(240,228,211,.30) 0%,transparent 28%),
        radial-gradient(circle at 96% 96%,rgba(221,168,185,.22) 0%,transparent 30%),
        radial-gradient(circle at 4% 98%,rgba(246,224,231,.36) 0%,transparent 28%);
      -webkit-font-smoothing:antialiased;line-height:1.5;padding:26px clamp(14px,4vw,44px) 60px;
    }}
    .bsr a{{color:{c['blush600']};text-decoration:none;}}
    .wrap{{max-width:1180px;margin:0 auto;}}
    .serif{{font-family:var(--serif);}}
    /* topbar */
    .top{{display:flex;align-items:center;justify-content:space-between;gap:14px;
      background:rgba(255,255,255,.72);border:1px solid {c['line']};border-radius:16px;
      padding:14px 22px;margin-bottom:20px;box-shadow:0 2px 8px rgba(168,69,107,.05);flex-wrap:wrap;}}
    .brand{{display:flex;align-items:center;gap:12px;}}
    .brand-badge{{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;color:#fff;
      font-family:var(--serif);font-weight:600;font-size:20px;
      background:linear-gradient(135deg,{c['blush500']},{c['blush700']});box-shadow:0 5px 14px rgba(184,92,122,.34);}}
    .brand-name{{font-family:var(--serif);font-weight:600;font-size:20px;letter-spacing:-.2px;}}
    .brand-sub{{font-size:10.5px;color:{c['muted']};letter-spacing:1.6px;text-transform:uppercase;font-weight:700;margin-top:2px;}}
    .tagpill{{display:inline-flex;align-items:center;gap:7px;background:{c['blush50']};border:1px solid {c['blush200']};
      color:{c['blush600']};border-radius:999px;padding:6px 14px;font-size:11px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;}}
    .dot{{width:7px;height:7px;border-radius:50%;background:{c['blush500']};}}
    /* hero */
    .hero{{position:relative;overflow:hidden;background:{c['surface']};border:1px solid {c['line']};
      border-radius:22px;padding:32px 34px;margin-bottom:20px;box-shadow:0 6px 20px rgba(168,69,107,.07);}}
    .hero::before{{content:'';position:absolute;inset:0;pointer-events:none;
      background:radial-gradient(circle at 90% 6%,rgba(221,168,185,.18) 0%,transparent 42%),
                 radial-gradient(circle at 4% 96%,rgba(240,228,211,.24) 0%,transparent 48%);}}
    .hero-in{{position:relative;z-index:1;}}
    .hero h1{{font-family:var(--serif);font-weight:600;font-size:clamp(26px,4vw,40px);line-height:1.1;letter-spacing:-.5px;}}
    .hero h1 em{{font-style:italic;color:{c['blush600']};}}
    .hero p{{color:{c['inkSoft']};font-size:14.5px;margin-top:8px;max-width:640px;}}
    /* kpis */
    .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:22px;}}
    .kpi{{position:relative;overflow:hidden;background:{c['surface2']};border:1px solid {c['line']};
      border-radius:14px;padding:16px;--a:{c['blush500']};}}
    .kpi::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--a);}}
    .kpi-ic{{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font-size:17px;
      background:color-mix(in srgb,var(--a) 14%,#fff);color:var(--a);}}
    .kpi-v{{font-family:var(--serif);font-weight:600;font-size:30px;line-height:1;margin-top:12px;color:{c['ink']};}}
    .kpi-l{{font-size:12.5px;color:{c['inkSoft']};font-weight:600;margin-top:6px;}}
    .kpi-s{{font-size:10.5px;color:{c['muted']};margin-top:2px;}}
    /* section */
    .sec{{margin-top:26px;}}
    .sec-h{{display:flex;align-items:center;gap:10px;margin-bottom:14px;}}
    .sec-h h2{{font-family:var(--serif);font-weight:600;font-size:21px;letter-spacing:-.3px;}}
    .sec-h .bar{{width:5px;height:22px;border-radius:3px;background:linear-gradient(135deg,{c['blush500']},{c['blush700']});}}
    .sec-h .cnt{{font-size:11.5px;color:{c['muted']};font-weight:600;margin-left:auto;}}
    .card{{background:{c['surface']};border:1px solid {c['line']};border-radius:16px;padding:20px;
      box-shadow:0 2px 8px rgba(168,69,107,.05);}}
    /* SWOT */
    .swot{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
    .quad{{border-radius:16px;padding:18px;border:1px solid {c['line']};background:{c['surface']};}}
    .quad-s{{background:linear-gradient(180deg,{c['sage100']}55,#fff);}}
    .quad-w{{background:linear-gradient(180deg,#F6E0E755,#fff);}}
    .quad-o{{background:linear-gradient(180deg,{c['gold100']}55,#fff);}}
    .quad-t{{background:linear-gradient(180deg,#FDECEC,#fff);}}
    .quad-h{{display:flex;align-items:center;gap:9px;font-family:var(--serif);font-weight:600;font-size:15px;margin-bottom:12px;}}
    .quad-ic{{font-size:17px;}} .quad-n{{margin-left:auto;font-size:12px;color:{c['muted']};font-family:var(--sans);
      background:#fff;border:1px solid {c['line']};border-radius:999px;padding:1px 9px;font-weight:700;}}
    .swot-list{{list-style:none;display:flex;flex-direction:column;gap:10px;}}
    .swot-item{{border-bottom:1px dashed {c['line']};padding-bottom:10px;}}
    .swot-item:last-child{{border:0;padding-bottom:0;}}
    .swot-t{{font-size:13.5px;font-weight:600;color:{c['ink']};line-height:1.45;}}
    .swot-c{{font-size:11px;color:{c['muted']};margin-top:4px;font-family:var(--sans);}}
    .swot-empty{{color:{c['muted']};font-size:13px;list-style:none;}}
    .cs{{font-size:9px;font-weight:800;padding:2px 7px;border-radius:5px;letter-spacing:.4px;text-transform:uppercase;vertical-align:middle;}}
    .cs-ok{{background:rgba(63,143,107,.14);color:{c['ok']};}}
    .cs-warn{{background:rgba(198,138,60,.16);color:{c['warn']};}}
    .cs-neutral{{background:{c['blush50']};color:{c['blush600']};}}
    /* competitors */
    .comps{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;}}
    .comp{{display:flex;align-items:center;gap:13px;background:{c['surface']};border:1px solid {c['line']};
      border-radius:14px;padding:15px;}}
    .comp-logo{{width:42px;height:42px;border-radius:11px;display:grid;place-items:center;font-weight:800;font-size:14px;
      background:{c['blush100']};color:{c['blush700']};flex-shrink:0;font-family:var(--sans);}}
    .comp-body{{flex:1;min-width:0;}} .comp-name{{font-weight:700;font-size:14px;}}
    .comp-site{{font-size:11.5px;color:{c['teal']};font-weight:600;}}
    .comp-why{{font-size:11px;color:{c['muted']};margin-top:3px;line-height:1.4;}}
    .comp-fit{{text-align:center;flex-shrink:0;}}
    .comp-fit-v{{font-family:var(--serif);font-weight:600;font-size:20px;color:{c['blush600']};}}
    .comp-fit-l{{font-size:9.5px;color:{c['muted']};text-transform:uppercase;letter-spacing:.5px;}}
    .tag{{font-size:9px;font-weight:700;padding:1px 7px;border-radius:5px;text-transform:uppercase;letter-spacing:.4px;vertical-align:middle;}}
    .tag-sage{{background:{c['sage100']};color:{c['sage700']};}} .tag-teal{{background:{c['teal100']};color:{c['teal']};}}
    /* tows */
    .tows-row{{display:flex;gap:12px;padding:11px 0;border-bottom:1px dashed {c['line']};}}
    .tows-row:last-child{{border:0;}}
    .tows-k{{font-family:var(--sans);font-weight:800;font-size:10px;letter-spacing:.6px;color:#fff;
      border-radius:6px;padding:3px 9px;height:fit-content;white-space:nowrap;}}
    .tows-so{{background:{c['sage']};}} .tows-st{{background:{c['teal']};}}
    .tows-wo{{background:{c['gold']};}} .tows-wt{{background:{c['blush600']};}}
    .tows-txt{{font-size:13px;color:{c['ink']};line-height:1.5;}}
    .tows-desc{{font-size:11.5px;color:{c['inkSoft']};margin-top:3px;font-weight:400;line-height:1.5;}}
    .posture{{background:{c['blush50']};border:1px solid {c['blush200']};border-radius:12px;padding:13px 16px;
      margin-top:14px;font-size:13.5px;color:{c['blush700']};font-weight:600;}}
    /* calendar */
    .cal-row{{display:grid;grid-template-columns:96px 150px 1fr;gap:12px;align-items:start;padding:12px 0;border-bottom:1px dashed {c['line']};}}
    .cal-row:last-child{{border:0;}}
    .cal-date{{font-weight:700;font-size:12px;color:{c['blush600']};font-family:var(--sans);}}
    .cal-plat{{font-size:11.5px;color:{c['inkSoft']};font-weight:600;display:flex;align-items:center;gap:6px;}}
    .cal-ic{{width:22px;height:22px;border-radius:6px;display:grid;place-items:center;background:{c['blush50']};color:{c['blush600']};font-size:11px;}}
    .cal-topic{{font-weight:700;font-size:13.5px;}} .cal-hook{{font-size:12px;color:{c['inkSoft']};margin-top:2px;font-style:italic;}}
    /* creative */
    .creative{{display:grid;grid-template-columns:1fr 1.2fr;gap:16px;align-items:start;}}
    .media-col{{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start;}}
    .media{{flex:1 1 190px;min-width:0;}}
    .creative img,.creative video{{width:100%;border-radius:14px;border:1px solid {c['line']};
      display:block;background:#0b0b11;}}
    .reel-vid{{aspect-ratio:9/16;max-height:560px;object-fit:contain;}}
    .creative .cap{{font-size:11.5px;color:{c['muted']};margin-top:8px;text-align:center;}}
    .foot{{text-align:center;color:{c['muted']};font-size:11.5px;margin-top:34px;}}
    .foot b{{color:{c['blush600']};}}
    .voice-row{{display:flex;gap:10px;padding:10px 4px;border-bottom:1px solid {c['line']};align-items:flex-start;}}
    .voice-row:last-child{{border-bottom:none;}}
    .voice-k{{flex:0 0 auto;font-size:16px;line-height:1.2;padding:4px 8px;border-radius:10px;}}
    .voice-s{{background:{c['sage100']};}}
    .voice-w{{background:{c['gold100']};}}
    .voice-row b{{font-size:13.5px;color:{c['ink']};}}
    .voice-q{{font-size:12px;color:{c['inkSoft']};margin-top:4px;line-height:1.55;}}
    .mp-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px 18px;}}
    .mp-l{{display:block;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:{c['muted']};margin-bottom:2px;}}
    .mp-grid b{{font-size:13.5px;color:{c['ink']};}}
    .mp-ok{{font-size:12px;color:{c['ok']};font-weight:700;}}
    .mp-warn{{font-size:12px;color:{c['warn']};font-weight:700;}}
    .mp-r{{font-size:12.5px;color:{c['inkSoft']};margin-top:12px;line-height:1.6;}}
    .act-row{{display:flex;gap:12px;padding:10px 4px;border-bottom:1px solid {c['line']};align-items:flex-start;}}
    .act-row:last-child{{border-bottom:none;}}
    .act-n{{flex:0 0 26px;height:26px;border-radius:50%;background:{c['blush100']};color:{c['blush700']};
      font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center;}}
    .act-row b{{font-size:13.5px;color:{c['ink']};}}
    .act-h{{font-size:12px;color:{c['muted']};margin-top:2px;}}
    @media (max-width:760px){{.mp-grid{{grid-template-columns:1fr 1fr;}}}}
    @media (max-width:760px){{.swot,.creative{{grid-template-columns:1fr;}}.cal-row{{grid-template-columns:1fr;gap:3px;}}}}
    </style>"""


def build_dashboard_html(
    competitor_path: Optional[str] = None,
    *,
    profile_path: Optional[str] = None,
    plan_path: Optional[str] = None,
    poster_path: Optional[str] = None,
    reel_path: Optional[str] = None,
    media_plan_path: Optional[str] = None,
    include_media_plan: bool = True,
    standalone: bool = True,
    generated_at: Optional[str] = None,
) -> str:
    """Render the dashboard to an HTML string (the interactive studio embeds this body directly)."""
    comp = _load(competitor_path)
    profile = _load(profile_path)
    prof = profile.get("profile", profile) if profile else (comp.get("profile") or {})
    plan = _load(plan_path)

    name = _val(prof.get("name")) or plan.get("business_name") or comp.get("subject_url") or "Brand"
    category = _val(prof.get("category")) or comp.get("subject_category") or ""
    tagline = _val(prof.get("tagline")) or ""
    tone = _val(prof.get("tone_of_voice")) or ""
    offerings = prof.get("offerings") or []
    vprops = prof.get("value_propositions") or []
    swot = comp.get("swot") or {}
    competitors = comp.get("competitors") or []
    tows = comp.get("tows") or {}
    items = plan.get("items") or []

    n_swot = sum(len(swot.get(k) or []) for k in ("strengths", "weaknesses", "opportunities", "threats"))
    badge_letter = (name.strip()[:1] or "B").upper()

    # KPIs
    kpis = "".join([
        _kpi("◆", str(len(offerings)), "Offerings", "extracted & grounded", _C["blush500"]),
        _kpi("⚑", str(comp.get("competitor_count") or len(competitors)), "Competitors", "cited peers", _C["teal"]),
        _kpi("✳", str(n_swot), "SWOT items", "every one cited", _C["gold"]),
        _kpi("♥", str(len(vprops)), "Value props", "from the brand", _C["sage"]),
        _kpi("▤", str(len(items)), "Calendar posts", (f"{plan.get('days')}-day plan" if plan.get("days") else "content plan"), _C["blush700"]),
    ])

    swot_html = ""
    if n_swot:
        swot_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>SWOT — grounded in real evidence</h2><span class="cnt">{_esc(swot.get('mode') or '')} · every line cited</span></div>
          <div class="swot">
            {_swot_quad('Strengths', '💪', swot.get('strengths'), 's')}
            {_swot_quad('Weaknesses', '⚠', swot.get('weaknesses'), 'w')}
            {_swot_quad('Opportunities', '✦', swot.get('opportunities'), 'o')}
            {_swot_quad('Threats', '⚡', swot.get('threats'), 't')}
          </div></div>"""

    # CUSTOMER VOICE (owner directive 2026-07-12 — "the review work must SHOW"): the ABSA
    # own-brand themes already live INSIDE the SWOT quadrants; this section makes them
    # unmissable for a client demo — each theme with its verbatim «quotes» as the receipts.
    voice_items = []
    for quad in ("strengths", "weaknesses"):
        for it in (swot.get(quad) or []):
            if "customer voice" in str(it.get("evidence") or ""):
                voice_items.append((quad, it))
    voice_html = ""
    if voice_items:
        rows = ""
        for quad, it in voice_items[:8]:
            icon, klass = ("💬", "s") if quad == "strengths" else ("⚠", "w")
            quotes = "".join(f'<div class="voice-q">{_esc(c)}</div>'
                             for c in (it.get("citation") or [])[:3])
            rows += (f'<div class="voice-row"><span class="voice-k voice-{klass}">{icon}</span>'
                     f'<div><b>{_esc(it.get("text") or "")}</b>{quotes}</div></div>')
        voice_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Customer voice — صوت العملاء</h2><span class="cnt">{len(voice_items)} grounded themes · verbatim quotes</span></div>
          <div class="card">{rows}</div></div>"""

    # MEDIA PLAN (U1) — auto-discovered next to the result file, so the exported dashboard
    # carries the buying plan without any caller changes. Bilingual labels, never raw enums
    # (owner 2026-07-12: the plan section read as a raw dump). include_media_plan=False
    # suppresses it (the STUDIO embeds this report and has its own richer Arabic card —
    # the duplication was part of the mess).
    mp_html = ""
    _OBJ_L = {"OUTCOME_SALES": "مبيعات · Sales",
              "OUTCOME_LEADS": "عملاء محتملون · Leads",
              "OUTCOME_TRAFFIC": "زيارات · Traffic",
              "OUTCOME_AWARENESS": "وعي · Awareness",
              "OUTCOME_ENGAGEMENT": "تفاعل · Engagement",
              "OUTCOME_APP_PROMOTION": "تطبيق · App"}
    _DEST_L = {"online_store": "المتجر الإلكتروني",
               "lead_form": "نموذج تواصل",
               "whatsapp": "واتساب",
               "phone_call": "مكالمة هاتفية",
               "messenger": "ماسنجر",
               "app_store": "متجر التطبيقات",
               "website": "الموقع"}
    _FUN_L = {"tofu": "وعي · TOFU", "mofu": "تفكير · MOFU",
              "bofu": "تحويل · BOFU"}
    mp_path = media_plan_path
    if include_media_plan and not mp_path and competitor_path \
            and str(competitor_path).endswith("_result.json"):
        cand = Path(str(competitor_path).replace("_result.json", "_media_plan.json"))
        mp_path = str(cand) if cand.is_file() else None
    mp = _load(mp_path) if include_media_plan else {}
    obj = (mp.get("objectives") or [{}])[0] if mp else {}
    if obj.get("objective"):
        kpi = obj.get("kpi_target") or {}
        geo = mp.get("base_geo") or {}
        n_ev = sum(1 for e in (obj.get("evidence") or []) if e.get("resolved"))
        badge = ("<span class='mp-ok'>مؤكد بالأدلة ✓</span>" if n_ev
                 else "<span class='mp-warn'>للمراجعة ⚠</span>")
        geo_txt = str(geo.get("mode") or "")
        geo_txt = {"national": "قومي · National",
                   "radius": "نطاق محلي · Radius"}.get(geo_txt, geo_txt)
        if geo.get("center_address"):
            geo_txt += f" — {geo.get('center_address')} ({geo.get('radius_km')} km)"
        # evidenced persona axes from the same plan (only what the evidence supports)
        persona = mp.get("base_persona") or {}
        p_bits = []
        for axis, label in (("age_range", "العمر"), ("gender", "النوع")):
            val = persona.get(axis)
            if isinstance(val, dict):
                val = val.get("value") or val.get("claim")
            if val:
                p_bits.append(f"{label}: {val}")
        for itx in (persona.get("interests") or [])[:3]:
            c = itx.get("claim") if isinstance(itx, dict) else str(itx)
            if c:
                p_bits.append(str(c))
        persona_html = (f'<p class="mp-r"><b>الشريحة (بالأدلة):</b> '
                        f'{_esc(" · ".join(p_bits))}</p>' if p_bits else "")
        mp_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Media plan — خطة الشراء الإعلاني</h2><span class="cnt">deduced from evidence · U1</span></div>
          <div class="card"><div class="mp-grid">
            <div><span class="mp-l">Objective · الهدف</span><b>{_esc(_OBJ_L.get(str(obj.get('objective') or ''), str(obj.get('objective') or '')))}</b></div>
            <div><span class="mp-l">Destination · الوجهة</span><b>{_esc(_DEST_L.get(str(obj.get('destination') or ''), str(obj.get('destination') or '')))}</b></div>
            <div><span class="mp-l">Funnel · القمع</span><b>{_esc(_FUN_L.get(str(obj.get('funnel_stage') or ''), str(obj.get('funnel_stage') or '')))}</b></div>
            <div><span class="mp-l">KPI</span><b>{_esc(kpi.get('metric') or '')}</b></div>
            <div><span class="mp-l">Geo · الجغرافيا</span><b>{_esc(geo_txt)}</b></div>
            <div><span class="mp-l">Evidence · الأدلة</span>{badge}</div>
          </div>
          <p class="mp-r">{_esc(obj.get('rationale') or '')}</p>{persona_html}</div></div>"""

    # TOWS PRIORITY ACTIONS — already inside result.json, silently dropped before
    # (owner: everything must show). rank IS a real sequence, so numbering carries meaning.
    actions = (tows.get("priority_actions") or [])[:6]
    actions_html = ""
    if actions:
        rows = ""
        for a in actions:
            extra = f" — {_esc(a.get('rationale') or '')}" if a.get("rationale") else ""
            rows += (f'<div class="act-row"><span class="act-n">{int(a.get("rank") or 0)}</span>'
                     f'<div><b>{_esc(a.get("action") or "")}</b>'
                     f'<div class="act-h">{_esc(a.get("horizon") or "")}{extra[:170]}</div>'
                     f'</div></div>')
        actions_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Priority actions — أولويات التنفيذ</h2><span class="cnt">{len(actions)} ranked moves</span></div>
          <div class="card">{rows}</div></div>"""

    # SCRAPER QA STRIP — the same summary the studio shows, now on the export (the analysis
    # names its own coverage). Best-effort; silently absent without a scrape dir.
    qa_html = ""
    try:
        if competitor_path and str(competitor_path).endswith("_result.json"):
            _slug = Path(competitor_path).name[: -len("_result.json")]
            from dashboard.products import scrape_qa_for_slug
            qa = scrape_qa_for_slug(_slug)
            if qa:
                note = _esc((qa.get("key_notes") or [""])[0])
                note_html = f'<p class="mp-r">{note}</p>' if note else ''
                qa_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
                  <h2>Data coverage — تغطية البيانات</h2><span class="cnt">{'✓ ready' if qa.get('ready') else '⚠ partial'}</span></div>
                  <div class="card"><div class="mp-grid">
                    <div><span class="mp-l">Pages</span><b>{qa.get('pages_succeeded')}/{qa.get('pages_attempted')}</b></div>
                    <div><span class="mp-l">Products</span><b>{qa.get('products')}</b></div>
                    <div><span class="mp-l">Images</span><b>{qa.get('images')}</b></div>
                    <div><span class="mp-l">Text blocks</span><b>{qa.get('text_blocks')}</b></div>
                    <div><span class="mp-l">Duration</span><b>{int((qa.get('duration_ms') or 0)/1000)}s</b></div>
                    <div><span class="mp-l">Failures</span><b>{qa.get('failures')}</b></div>
                  </div>{note_html}</div></div>"""
    except Exception:  # noqa: BLE001 — the export never breaks on a missing scrape
        qa_html = ""

    comp_html = ""
    if competitors:
        comp_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Competitors — discovered & scored</h2><span class="cnt">{len(competitors)} peers</span></div>
          <div class="comps">{''.join(_competitor_card(x) for x in competitors)}</div></div>"""

    tows_html = ""
    strategies = tows.get("strategies") or []
    if strategies or tows.get("posture"):
        _tk = {"SO": "tows-so", "ST": "tows-st", "WO": "tows-wo", "WT": "tows-wt"}
        rows = ""
        for s in strategies[:8]:
            kind = str(s.get("type") or s.get("kind") or "SO").upper()[:2]
            title = _esc(s.get("title") or s.get("text") or s.get("strategy") or "")
            desc = _esc(s.get("description") or "")
            desc_h = f'<div class="tows-desc">{desc}</div>' if desc else ""
            rows += (f'<div class="tows-row"><span class="tows-k {_tk.get(kind, "tows-so")}">{_esc(kind)}</span>'
                     f'<div class="tows-txt"><b>{title}</b>{desc_h}</div></div>')
        posture = _esc(tows.get("posture") or "")
        posture_html = f'<div class="posture">◎ Strategic posture: {posture}</div>' if posture else ""
        tows_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>TOWS — strategies from the matrix</h2></div>
          <div class="card">{rows or '<div class="swot-empty">—</div>'}{posture_html}</div></div>"""

    cal_html = ""
    if items:
        cal_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Content calendar</h2><span class="cnt">{len(items)} posts · grounding-gated hooks</span></div>
          <div class="card">{''.join(_calendar_row(it) for it in items)}</div></div>"""

    poster_uri = _data_uri(poster_path)
    reel_uri = _data_uri(reel_path)
    creative_html = ""
    if poster_uri or reel_uri:
        media = ""
        if poster_uri:
            media += (f'<div class="media"><img src="{poster_uri}" alt="poster">'
                      f'<div class="cap">Poster · one-shot engine · logo composited crisp</div></div>')
        if reel_uri:
            # base64-inlined so the page stays self-contained (opens as a file AND serves the same);
            # the reel plays right in the dashboard — "everything shows in one place".
            media += (f'<div class="media"><video class="reel-vid" src="{reel_uri}" controls playsinline '
                      f'preload="metadata"></video>'
                      f'<div class="cap">Reel · Veo 3.1 · grounded story · branded end-card</div></div>')
        creative_html = f"""<div class="sec"><div class="sec-h"><span class="bar"></span>
          <h2>Creative — agency-grade, brand-safe</h2></div>
          <div class="card creative">
            <div class="media-col">{media}</div>
            <div><div class="swot-t" style="font-size:15px">Every hard claim traces to real evidence.</div>
              <p style="font-size:13px;color:{_C['inkSoft']};margin-top:8px;line-height:1.6">
              The headline and proof lines pass the Evidence Ledger before they render; the brand logo is
              the real asset composited deterministically (never re-drawn by the image model). The reel
              tells the same grounded story with continuous voice-over, refined typography and a branded
              end-card (the real logo on the brand colour).</p></div>
          </div></div>"""

    gen = generated_at or datetime.now().strftime("%Y-%m-%d")
    body = f"""<div class="bsr"><div class="wrap">
      <div class="top">
        <div class="brand"><div class="brand-badge">{_esc(badge_letter)}</div>
          <div><div class="brand-name">Baseera</div><div class="brand-sub">Marketing Intelligence</div></div></div>
        <div class="tagpill"><span class="dot"></span> Provable Brand Safety</div>
      </div>
      <div class="hero"><div class="hero-in">
        <h1 class="serif">{_esc(name)} — <em>a complete campaign, from one URL</em></h1>
        <p>{_esc(tagline or 'Grounded brand intelligence: profile, cited SWOT, real competitors, a content calendar and agency-grade creative — every claim traceable to a source.')}
        {(' · <b>' + _esc(category) + '</b>') if category else ''}{(' · tone: ' + _esc(tone)) if tone else ''}</p>
        <div class="kpis">{kpis}</div>
      </div></div>
      {swot_html}{voice_html}{mp_html}{comp_html}{tows_html}{actions_html}{cal_html}{creative_html}{qa_html}
      <div class="foot">Generated by <b>Baseera</b> · {_esc(gen)} · every factual line carries its source (the Evidence Ledger).</div>
    </div></div>"""

    content = _css() + body
    if standalone:
        content = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                   f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                   f"<title>Baseera · {_esc(name)}</title></head><body>{content}</body></html>")
    return content


def build_dashboard(
    competitor_path: Optional[str] = None,
    *,
    profile_path: Optional[str] = None,
    plan_path: Optional[str] = None,
    poster_path: Optional[str] = None,
    reel_path: Optional[str] = None,
    media_plan_path: Optional[str] = None,
    out_path: str = "outputs/dashboard.html",
    standalone: bool = True,
    generated_at: Optional[str] = None,
) -> Path:
    """Build the dashboard and write it to out_path (returns the Path)."""
    content = build_dashboard_html(
        competitor_path, profile_path=profile_path, plan_path=plan_path,
        poster_path=poster_path, reel_path=reel_path, media_plan_path=media_plan_path,
        standalone=standalone, generated_at=generated_at,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return out
