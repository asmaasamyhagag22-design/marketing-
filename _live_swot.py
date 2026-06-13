"""TEMP (delete after): live SWOT on an ecommerce profile with Serper peers,
to prove Threats + Opportunities now populate for web-discovered competitors."""
import json, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(".env")
sys.stdout.reconfigure(encoding="utf-8")

from scraper import scrape
from competitor.router import route_discovery
from competitor.web_discovery import default_web_engine
from competitor.matrix import build_matrix
from competitor.swot import synthesize_swot

prof = json.loads(Path("scrapes/glamira_com_20260530_152013/business_profile.json").read_text(encoding="utf-8"))
res = route_discovery(prof, places_client=None, web_engine=default_web_engine())
print("web peers discovered:", len(res.competitors))

def scrape_fn(url):
    try:
        m, _ = scrape(url)
        return m
    except Exception as e:
        print("   peer scrape failed:", url, type(e).__name__)
        return None

matrix = build_matrix(prof, res.competitors, scrape_fn=scrape_fn, subject_name="GLAMIRA")
swot = synthesize_swot(matrix, themes=[])
print(f"mode={swot.mode} | S={len(swot.strengths)} W={len(swot.weaknesses)} "
      f"O={len(swot.opportunities)} T={len(swot.threats)}")
for t in swot.threats[:4]:
    print("  THREAT:", t.text[:90])
for o in swot.opportunities[:4]:
    print("  OPP:   ", o.text[:90])
