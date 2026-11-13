"""Compose reviewed campaign scenes with independent, evidence-bound type."""
from base64 import b64encode
from hashlib import sha256
from html import escape
from pathlib import Path
import re


SCENES = Path(__file__).with_name("campaign_scenes")
PALETTES = {
    "paper": ("#f5ebd7", "#351310", "#9a2e22", "#fff4dc"),
    "slate": ("#30181d", "#fff4dc", "#fec47c", "#30181d"),
}


def scene_bytes(art):
    checksum = art["scene"]["sha256"]
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid scene digest")
    data = (SCENES / f"{checksum}.jpg").read_bytes()
    if sha256(data).hexdigest() != checksum:
        raise ValueError("Scene bytes do not match review")
    return data


def scene_html(package, width, height, fonts):
    art = package["art"]
    bg, ink, accent, button = PALETTES[art["palette"]]
    copy = {field: escape(value) for field, value in package["copy"].items()}
    scene = b64encode(scene_bytes(art)).decode("ascii")
    subjects = "".join(
        f'<div class="subject"><bdi>{escape(item["name"])}</bdi>'
        f'<p>{escape(item["detail"])}</p></div>'
        for item in art["subjects"]
    )
    return f"""<!doctype html>
<html lang="{escape(package["language"])}" dir="{escape(package["direction"])}">
<meta charset="utf-8">
<style>
@font-face{{font-family:Campaign;src:url(data:font/ttf;base64,{fonts[0]});font-weight:400}}
@font-face{{font-family:Campaign;src:url(data:font/ttf;base64,{fonts[1]});font-weight:700}}
@font-face{{font-family:CampaignLatin;src:url(data:font/ttf;base64,{fonts[2]});font-weight:400}}
@font-face{{font-family:CampaignLatin;src:url(data:font/ttf;base64,{fonts[3]});font-weight:700}}
*{{box-sizing:border-box}}
body{{margin:0;background:{bg};color:{ink};font-family:Campaign,CampaignLatin,sans-serif}}
main{{height:{height}px;width:{width}px;display:grid;
 grid-template-rows:auto minmax(0,1fr) auto auto;overflow:hidden}}
header,.details,footer{{padding-inline:64px}}
header{{padding-block:{"47px 34px" if height > width else "25px 22px"};text-align:center}}
.brand{{font:700 27px/1.35 CampaignLatin,Campaign,sans-serif;letter-spacing:.13em;color:{accent}}}
h1,p{{margin:0}}
h1{{margin-top:{"20px" if height > width else "15px"};font-size:{"90px" if height > width else "80px"};
 font-weight:700;line-height:1.28;text-wrap:balance}}
.photo{{width:100%;height:100%;object-fit:cover;object-position:50% 52%;display:block}}
.details{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));padding-block:{"20px 24px" if height > width else "13px 14px"};
 border-bottom:1px solid {ink}3b}}
.subject{{text-align:center;min-width:0}}
.subject+ .subject{{border-inline-start:1px solid {ink}3b}}
.subject bdi{{display:block;font-size:47px;line-height:1.32;font-weight:700}}
.subject p{{font-size:35px;line-height:1.4}}
footer{{padding-block:{"24px 36px" if height > width else "16px 22px"};display:grid;
 grid-template-columns:1fr auto;align-items:center;column-gap:24px}}
.message{{font-size:37px;line-height:1.45}}
.disclosure{{font-size:29px;line-height:1.4;margin-top:4px}}
.cta{{font-size:37px;line-height:1.42;font-weight:700;padding:13px 24px;
 text-decoration:none;color:{button};background:{accent};white-space:nowrap}}
.cta span{{font-family:CampaignLatin,sans-serif}}
</style>
<main>
 <header><div class="brand" dir="auto">{escape(package["brand_name"].upper())}</div><h1>{copy["headline"]}</h1></header>
 <img class="photo" alt="" src="data:image/jpeg;base64,{scene}">
 <div class="details">{subjects}</div>
 <footer><div><p class="message">{copy["message"]}</p><p class="disclosure">{escape(art["disclosure"])}</p></div>
 <a class="cta" href="{escape(package["source_url"])}">{copy["cta"]} <span aria-hidden="true">{"←" if package["direction"] == "rtl" else "→"}</span></a></footer>
</main>
</html>"""


def measure_scene(page, width, height):
    boxes = page.locator(".brand, h1, .photo, .subject bdi, .subject p, .message, .disclosure, .cta").evaluate_all(
        """elements => elements.map(element => {
            const r = element.getBoundingClientRect();
            const css = getComputedStyle(element);
            return {field: element.className || element.tagName, x: r.x, y: r.y,
                right: r.right, bottom: r.bottom, size: parseFloat(css.fontSize),
                color: css.color, background: css.backgroundColor,
                overflow: element.scrollWidth > element.clientWidth + 1 ||
                    (element instanceof HTMLImageElement && !element.naturalWidth)};
        })"""
    )
    if any(box["x"] < 0 or box["right"] > width or box["y"] < 0 or box["bottom"] > height or
           box["overflow"] for box in boxes):
        raise ValueError("POSTER_CLIPPING")
    for index, a in enumerate(boxes):
        for b in boxes[index + 1:]:
            if (min(a["right"], b["right"]) - max(a["x"], b["x"]) > 1 and
                    min(a["bottom"], b["bottom"]) - max(a["y"], b["y"]) > 1):
                raise ValueError("POSTER_OVERLAP")
    return boxes
