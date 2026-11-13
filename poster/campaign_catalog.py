"""Responsive catalog artwork made with text and original CSS illustrations."""
from html import escape


PALETTES = {"classic", "pepper", "mushroom"}


def catalog_cards(art):
    subjects = art["subjects"]
    return "".join(
        f'''<article class="catalog-item {item["palette"] if item["palette"] in PALETTES else "classic"}">
          <div class="food-drawing" aria-hidden="true">
            <i class="bun"></i><i class="filling"></i><i class="cheese"></i><i class="patty"></i><i class="heel"></i>
          </div>
          <div class="item-name" dir="auto">{escape(item["name"])}</div>
          <div class="item-detail" dir="auto">{escape(item["detail"])}</div>
        </article>'''
        for item in subjects
    )


CATALOG_CSS = """
main.catalog {
  background: #ffb44f; color: #261814; padding: 68px 76px;
  grid-template-rows: auto auto minmax(280px,1fr) auto; gap: 28px;
}
.catalog .brand {border-color:#261814; font-size:34px; padding-bottom:15px}
.catalog h1 {font-size:93px; line-height:1.27; max-width:100%; letter-spacing:-.025em}
.catalog .copy {gap:14px}
.catalog .message {font-size:39px; color:#261814}
.catalog .cta {font-size:36px; background:#261814; color:#fff2d9; border-radius:6px; padding:9px 30px}
.catalog .motif {mask-image:none; background:none; display:grid; grid-auto-flow:column;
  grid-auto-columns:minmax(0,1fr); gap:22px; min-height:280px}
.catalog-item {position:relative; min-width:0; overflow:hidden; border:3px solid #261814;
  border-radius:24px; padding:20px 14px 24px; text-align:center; display:grid;
  grid-template-rows:minmax(0,1fr) auto auto; row-gap: 4px; align-items:center;
  background:#fff0d6; color:#261814; container-type:size}
.catalog-item.pepper {background:#5b1d21; color:#fff0d6}
.catalog-item.mushroom {background:#433024; color:#fff0d6}
.catalog .item-name {font-size:48px; font-weight:700; line-height:1.35; overflow-wrap:anywhere}
.catalog .item-detail {font-size:36px; line-height:1.4; overflow-wrap:anywhere}
.food-drawing {width:min(85%, 410px, max(110px, calc((100cqh - 139px) * 1.45))); aspect-ratio:1.45; position:relative; margin:auto;
  align-self:center; isolation:isolate; translate:0 0}
.catalog .food-drawing i {position:absolute; inset:auto; translate:none; transform:none;
  width:auto; height:auto; box-shadow:none; border:none; border-radius:0}
.catalog .food-drawing::after {content:''; position:absolute; inset:89% 0 0; z-index:-1;
  background:#28120f; opacity:.18; border-radius:50%; filter:blur(6px)}
.catalog .food-drawing .bun {inset:3% 5% 46%; border:3px solid #401e16;
  border-radius:56% 56% 17% 17% / 83% 83% 19% 19%;
  background:radial-gradient(ellipse at 39% 35%,#ffe1a3 0 2.5%,transparent 3%),
    radial-gradient(ellipse at 58% 25%,#ffe1a3 0 2.3%,transparent 2.9%),
    radial-gradient(ellipse at 67% 43%,#ffe1a3 0 2.2%,transparent 2.9%),
    radial-gradient(ellipse at 26% 49%,#ffe1a3 0 2.1%,transparent 2.8%),
    radial-gradient(ellipse at 51% 51%,#ffe1a3 0 2.1%,transparent 2.8%),
    linear-gradient(#ffbe58 3%,#e77b32 65%,#b14e26); z-index:5}
.catalog .food-drawing .filling {inset:49% 4% 33%; z-index:4; border-radius:30% 30% 42% 42%;
  background:#ae4029; border:3px solid #401e16}
.catalog .pepper .food-drawing .filling {background:repeating-linear-gradient(105deg,#daa24b 0 12%,#b47335 12% 15%,#6d7c38 15% 20%);}
.catalog .mushroom .food-drawing .filling {background:repeating-linear-gradient(110deg,#b17b57 0 15%,#78442b 15% 18%,#d7964c 18% 23%)}
.catalog .food-drawing .cheese {inset:59% 7% 22%; z-index:3; background:#ffcf55;
  clip-path:polygon(0 3%,100% 0,96% 45%,78% 50%,65% 100%,43% 51%,15% 66%,2% 36%)}
.catalog .food-drawing .patty {inset:63% 6% 16%; z-index:2; border-radius:34% 29% 38% 36%;
  background:repeating-linear-gradient(11deg,#61321d 0 4px,#743c21 5px 9px); border:3px solid #401e16}
.catalog .food-drawing .heel {inset:74% 9% 7%; border-radius:10% 10% 42% 42%;
  background:linear-gradient(#cb602e,#f1a450 80%); border:3px solid #401e16}
.catalog .illustration-note {font-size:24px; text-align:center; color:#261814; margin-block-start:-8px}
.catalog .catalog-action {display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap}
"""
