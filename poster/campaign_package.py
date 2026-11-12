"""Offline review exports for the evidence-bound campaign workflow."""
from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from poster.render_playwright import render_html_to_png


SIZES = {"portrait": (1080, 1350), "square": (1080, 1080)}
THEMES = {
    "ember": ("#321517", "#fff4dc", "#ffbb5e", "#8d3834", "#fc8057"),
    "cobalt": ("#130d36", "#fff7ef", "#ffc983", "#5829a5", "#bc91ff"),
    "forest": ("#112d28", "#fff9e9", "#e7ed86", "#216655", "#78c8a2"),
}


class PosterLayoutError(ValueError):
    pass


@lru_cache(maxsize=4)
def font_data(name):
    return b64encode((Path(__file__).parent / "fonts" / name).read_bytes()).decode()


def poster_html(package, width, height):
    bg, ink, accent, shape, light = THEMES[package["theme"]]
    regular = font_data("NotoSansArabic-Regular.ttf")
    bold = font_data("NotoSansArabic-Bold.ttf")
    latin_regular = font_data("NotoSans-Regular.ttf")
    latin_bold = font_data("NotoSans-Bold.ttf")
    text = {key: escape(value) for key, value in package["copy"].items()}
    brand = escape(package["brand_name"])
    lang, direction = escape(package["language"]), escape(package["direction"])
    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<meta charset="utf-8">
<style>
@font-face{{font-family:Campaign;src:url(data:font/ttf;base64,{regular});font-weight:400}}
@font-face{{font-family:Campaign;src:url(data:font/ttf;base64,{bold});font-weight:700}}
@font-face{{font-family:CampaignLatin;src:url(data:font/ttf;base64,{latin_regular});font-weight:400}}
@font-face{{font-family:CampaignLatin;src:url(data:font/ttf;base64,{latin_bold});font-weight:700}}
*{{box-sizing:border-box}}
body{{margin:0;color:{ink};background:{bg};font-family:Campaign,CampaignLatin,sans-serif}}
main{{width:{width}px;height:{height}px;padding:64px 76px;display:grid;
 grid-template-rows:auto minmax(140px,1fr) auto;gap:30px;overflow:hidden;
 background:radial-gradient(ellipse at 30% 25%,{shape} 0,transparent 64%),{bg};}}
.brand{{border-block-end:2px solid {accent};padding-block-end:16px;
 font-size:40px;font-weight:700;line-height:1.35;overflow-wrap:anywhere}}
.motif{{position:relative;isolation:isolate;overflow:hidden;min-height:140px;
 background-image:radial-gradient({light}45 1.5px,transparent 2px);
 background-size:30px 30px;mask-image:linear-gradient(90deg,transparent,#000 24%,#000 76%,transparent)}}
.motif i{{position:absolute;inset-block-start:50%;inset-inline-start:50%;
 width:42%;height:82%;border-radius:50%;border:5px solid {light};translate:-50% -50%;
 transform:rotate(-28deg);background:linear-gradient(150deg,{light}55,{shape}44);
 box-shadow:0 0 70px {light}33,inset 0 0 70px {light}55}}
[dir=rtl] .motif i{{translate:50% -50%}}
.motif i:nth-child(2){{transform:rotate(28deg);width:58%;height:59%;border-color:{accent}}}
.motif i:nth-child(3){{transform:rotate(70deg);width:32%;height:93%;border-color:{ink}99}}
main[data-theme=ember] .motif i{{height:34%;width:59%;border-radius:46%;
 transform:translateY(-68%) rotate(-7deg);background:linear-gradient(172deg,{accent}aa,{shape}33)}}
main[data-theme=ember] .motif i:nth-child(2){{transform:rotate(7deg);width:74%}}
main[data-theme=ember] .motif i:nth-child(3){{transform:translateY(68%) rotate(-7deg);width:55%}}
main[data-theme=forest] .motif i{{border-radius:16%;width:24%;height:64%;
 transform:translateX(52%) rotate(-24deg);background:linear-gradient(40deg,{accent}77,{shape})}}
main[data-theme=forest] .motif i:nth-child(2){{transform:rotate(12deg)}}
main[data-theme=forest] .motif i:nth-child(3){{transform:translateX(-51%) rotate(-9deg)}}
.copy{{display:grid;gap:18px;min-width:0}}
h1,p{{margin:0;overflow-wrap:anywhere}}
h1{{font-weight:700;font-size:88px;line-height:1.26;letter-spacing:-.012em;text-wrap:balance}}
.message{{font-size:44px;line-height:1.46}}
.cta{{justify-self:start;padding:12px 26px;border-radius:12px;background:{accent};color:{bg};
 font-size:37px;line-height:1.45;font-weight:700}}
</style>
<main data-theme="{escape(package["theme"])}">
 <header class="brand" dir="auto">{brand}</header>
 <div class="motif" aria-hidden="true"><i></i><i></i><i></i></div>
 <section class="copy"><h1>{text["headline"]}</h1><p class="message">{text["message"]}</p>
 <p class="cta">{text["cta"]}</p></section>
</main>
</html>"""


def measure_poster(page):
    boxes = page.locator(".brand, .motif, h1, .message, .cta").evaluate_all(
        """elements => elements.map(element => {
            const r = element.getBoundingClientRect();
            const css = getComputedStyle(element);
            return {field: element.className || element.tagName, x: r.x, y: r.y,
                right: r.right, bottom: r.bottom, size: parseFloat(css.fontSize),
                color: css.color, background: css.backgroundColor,
                overflow: element.scrollWidth > element.clientWidth + 1};
        })"""
    )
    return boxes


def layout_poster(page, width, height):
    boxes = measure_poster(page)
    for headline, message, cta in ((76, 42, 36), (67, 40, 35), (60, 39, 34), (56, 37, 32)):
        if boxes[-1]["bottom"] <= height - 60:
            break
        page.add_style_tag(content=f"h1{{font-size:{headline}px}}.message{{font-size:{message}px}}.cta{{font-size:{cta}px}}")
        boxes = measure_poster(page)
    if any(box["x"] < 63 or box["right"] > width - 63 or box["y"] < 60 or
           box["bottom"] > height - 60 or box["overflow"] for box in boxes):
        raise PosterLayoutError("POSTER_CLIPPING")
    if any(a["bottom"] > b["y"] for a, b in zip(boxes, boxes[1:])):
        raise PosterLayoutError("POSTER_OVERLAP")
    return boxes


def render_poster(package, label, path):
    if package["poster_layout"] != "source-campaign@1":
        raise PosterLayoutError("POSTER_LAYOUT_UNAVAILABLE")
    width, height = SIZES[label]
    geometry = []
    render_html_to_png(
        poster_html(package, width, height), path, width=width, height=height, scale=1, offline=True,
        validate=lambda page: geometry.extend(layout_poster(page, width, height)),
    )
    image = path.read_bytes()
    return image, {"width": width, "height": height, "sha256": sha256(image).hexdigest(),
                   "geometry": geometry}


def read_poster(path):
    try:
        with ZipFile(path) as asset:
            image = asset.read("poster.png")
            measurements = json.loads(asset.read("measurements.json"))
        if sha256(image).hexdigest() != measurements["sha256"]:
            raise ValueError("Poster checksum mismatch")
    except (BadZipFile, ValueError, KeyError, TypeError) as exc:
        raise PosterLayoutError("POSTER_ARTIFACT_CORRUPT") from exc
    return image, measurements


def stored_poster(view, size, root):
    result = view["proposal"]
    directory = root / view["run_id"] / result["sha256"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{size}.zip"
    try:
        return read_poster(path)
    except FileNotFoundError:
        pass
    with TemporaryDirectory(prefix="render-", dir=directory) as work:
        work = Path(work)
        image, measurements = render_poster(result["package"], size, work / "poster.png")
        candidate = work / "asset.zip"
        with ZipFile(candidate, "w") as asset:
            asset.writestr("poster.png", image)
            asset.writestr("measurements.json", json.dumps(measurements, sort_keys=True))
        # Publish a complete artifact once, even when independent processes render the same run.
        try:
            os.link(candidate, path)
        except FileExistsError:
            return read_poster(path)
    return image, measurements


def preview_poster(view, size, root):
    image, _ = stored_poster(view, size, root)
    return image


def export_package(view, root):
    result = view["proposal"]
    archive = BytesIO()
    report = {}
    with ZipFile(archive, "w") as zip_file:
        for label in SIZES:
            image, report[label] = stored_poster(view, label, root)
            zip_file.writestr(ZipInfo(f"poster-{label}.png"), image)
        zip_file.writestr(ZipInfo("campaign.json"), json.dumps(
            {"run_id": view["run_id"], "approval_id": view["approval_id"],
             "profile_snapshot_id": view["profile_snapshot_id"], "proposal": result,
             "poster_measurements": report, "review_status": "LOCAL_REVIEW",
             "video": "SCRIPT_AND_STORYBOARD_ONLY"},
            indent=2, ensure_ascii=False, sort_keys=True,
        ), compress_type=ZIP_DEFLATED)
    return archive.getvalue()
