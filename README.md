![Buffalo Burger — كلاسيك ولا هالبينو؟ An independent portfolio concept rendered in Adzy.](docs/campaigns/buffalo/portfolio/poster-portrait-390.png)

# ADZY · Buffalo Burger

[Portrait 1080 × 1350](docs/campaigns/buffalo/portfolio/poster-portrait.png) · [Square 1080 × 1080](docs/campaigns/buffalo/portfolio/poster-square.png) · [Campaign ZIP](docs/campaigns/buffalo/portfolio/campaign.zip) · [Before and after](docs/campaigns/buffalo/portfolio/comparison.jpg)

## Replay from a clean checkout

Use Linux, Python 3.12, Docker, and Playwright Chromium. The demo starts disposable PostgreSQL on loopback, uses frozen publisher evidence and stored scenes, and makes zero paid calls.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-app.txt
python -m playwright install chromium
docker pull postgres:16-alpine

demo_dir=$(mktemp -d)/demo
python -m workflows.public_campaign_demo init --directory "$demo_dir"
ADZY_CAMPAIGN_EDITIONS_FILE="$PWD/docs/campaigns/buffalo/portfolio/edition.json" \
  python -m workflows.public_campaign_demo serve --directory "$demo_dir" \
  --snapshot docs/demo/campaign-snapshots/buffalo --port 8020
```

Open [the running app](http://127.0.0.1:8020/app) and sign in using the credentials from `init`. Choose **Campaign**, enter `https://buffaloburger.com`, set the objective to **تشجيع المستخدم على تصفّح المنيو واختيار برجر يناسبه**, and select Arabic. Review the publisher quotes and the two directions. Use **تعديل نص الاتجاه** to try the reviewed message **الاتنين فيهم صوص بافالو.** Save the brief, preview both sizes, approve the current version, and download the ZIP. **شوف المنيو** opens the official menu from the app. The exported PNG carries the visible label and the JSON receipt carries its URL.

To check restart recovery, stop the server, run the same `serve` command with the same directory, and download again. After closing the demo, run `python -m workflows.public_campaign_demo cleanup --directory "$demo_dir"`. If Chromium needs system libraries, use `python -m playwright install-deps chromium`.

## Verify the release

```bash
check_dir=$(mktemp -d)
ADZY_CAMPAIGN_EDITIONS_FILE="$PWD/docs/campaigns/buffalo/portfolio/edition.json" \
  python tools/verify_public_campaign_browser.py --directory "$check_dir/demo" \
  --evidence-dir "$check_dir/browser" \
  --snapshot docs/demo/campaign-snapshots/buffalo \
  --planner-cases docs/campaigns/buffalo/portfolio/case.json
python -m workflows.campaign_eval --output "$check_dir/replay.json"
```

Omit `--snapshot` for current source retrieval. Use `--check-destination` to open the live menu in Chromium. The verifier exercises the wrong-product edit, both preview sizes, approval, stale export, and an identical ZIP after restart. A new campaign produces new review identifiers. The renderer reproduces the PNG bytes in the checked environment.

ADZY connects a publisher URL, objective, and language to a brief and export. The Buffalo edition uses editor-reviewed fields and an AI-generated illustrative scene. It binds each scene and the editable headline, message, and CTA to the reviewed brief. This showcase is an independent portfolio study. The package uses the brand and product names as identifiers and generated artwork with the project’s Noto fonts. [Review and provenance](docs/campaigns/buffalo/portfolio/REVIEW.md) · [Evidence and export receipt](docs/campaigns/buffalo/portfolio/campaign.json) · [Engineering walkthrough](docs/campaigns/INTERVIEW.md) · [Asset notes](THIRD_PARTY_ASSETS.md)
