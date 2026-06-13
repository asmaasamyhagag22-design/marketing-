"""Benchmark runner.

Reads benchmark/urls.txt and scrapes each URL, writing a summary
CSV of key signals so you can quickly eyeball coverage across your
benchmark set.

Usage:
    python -m benchmark.run --output-dir scrapes
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console

from scraper.crawler import scrape

app = typer.Typer(add_completion=False)
console = Console()


def _load_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


@app.command()
def main(
    urls_file: str = typer.Option("benchmark/urls.txt", "--urls", "-u"),
    output_dir: str = typer.Option("scrapes", "--output-dir", "-o"),
    summary_csv: str = typer.Option("benchmark/summary.csv", "--summary"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    urls = _load_urls(Path(urls_file))
    if not urls:
        console.print("[red]No URLs found.[/red] Add some to benchmark/urls.txt")
        sys.exit(1)

    rows = []
    for i, url in enumerate(urls, 1):
        console.print(f"[{i}/{len(urls)}] {url}")
        try:
            manifest, out_path = scrape(url, output_dir)
            row = {
                "url": url,
                "out_dir": str(out_path),
                "ready": manifest.readiness.ready_for_extraction,
                "pages_ok": manifest.scrape_meta.pages_succeeded,
                "pages_tried": manifest.scrape_meta.pages_attempted,
                "duration_ms": manifest.scrape_meta.duration_ms,
                "languages": "|".join(e.code for e in manifest.languages),
                "phones": len(manifest.contact.phones),
                "emails": len(manifest.contact.emails),
                "whatsapp": len(manifest.contact.whatsapp),
                "social": len(manifest.links.social),
                "ctas": len(manifest.links.cta_candidates),
                "internal_links": len(manifest.links.internal),
                "forms": sum(len(p.forms) for p in manifest.pages),
                "logo": manifest.visual.logo is not None,
                "palette_n": len(manifest.visual.color_palette),
                "failures": len(manifest.failures),
                "first_failure": manifest.failures[0].code.value if manifest.failures else "",
            }
            console.print(
                f"  -> ready={row['ready']}  pages={row['pages_ok']}/{row['pages_tried']}  "
                f"phones={row['phones']} emails={row['emails']} ctas={row['ctas']}"
            )
        except Exception as e:
            console.print(f"  [red]crashed[/red]: {type(e).__name__}: {e}")
            row = {"url": url, "ready": False, "first_failure": f"crash:{type(e).__name__}"}
        rows.append(row)

    # Write summary
    if rows:
        fieldnames = list(rows[0].keys())
        # Make sure all rows share the same keys
        for r in rows:
            for k in fieldnames:
                r.setdefault(k, "")
        Path(summary_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(summary_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        console.print(f"\n[green]Summary written:[/green] {summary_csv}")


if __name__ == "__main__":
    app()
