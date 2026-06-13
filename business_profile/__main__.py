"""CLI for the business profile builder.

Usage:
    python -m business_profile path/to/manifest.json
    python -m business_profile path/to/manifest.json --no-llm
    python -m business_profile path/to/manifest.json -o profile.json --verbose
"""
from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()

import logging
import sys
from pathlib import Path

# 2026-06 (PR-encoding-fix): force UTF-8 on stdout/stderr before rich
# initializes. Without this, running this CLI as a subprocess with a
# captured pipe on Windows defaults the streams to cp1252, and rich
# crashes with UnicodeEncodeError when printing Arabic taglines, curly
# quotes, or box-drawing chars in the profile-summary table. The
# benchmark runner invokes this module as a subprocess, so the crash
# only surfaced there (a direct console run worked because the console
# was already UTF-8 capable). reconfigure() overrides the stream
# encoding regardless of locale or PYTHONIOENCODING, which is more
# robust than setting the env var alone.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.table import Table

from .build import (
    BuildResult, build_profile, build_profile_no_llm, write_profile,
)
from .llm.caller import OpenAICaller

app = typer.Typer(add_completion=False,
                   help="Build a business_profile.json from a scrape manifest.")
console = Console()


@app.command()
def main(
    manifest: str = typer.Argument(..., help="Path to manifest.json"),
    output: str = typer.Option(
        None, "--output", "-o",
        help="Output path. Default: <manifest_dir>/business_profile.json",
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm",
        help="Skip the LLM step; use rules-only extractors.",
    ),
    model: str = typer.Option(
        "gpt-4o-mini", "--model", help="OpenAI model name.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Build a business_profile.json from a manifest."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    manifest_path = Path(manifest)
    if not manifest_path.exists():
        console.print(f"[red]Manifest not found:[/red] {manifest_path}")
        raise typer.Exit(2)

    out_path = Path(output) if output \
        else manifest_path.parent / "business_profile.json"

    if no_llm:
        console.print(f"[cyan]Building (rules only)[/cyan] {manifest_path}")
        profile = build_profile_no_llm(manifest_path)
        llm_summary = "skipped"
        pack_summary = "n/a"
        diag_summary = "n/a"
    else:
        console.print(f"[cyan]Building (rules + LLM)[/cyan] {manifest_path}")
        caller = OpenAICaller(model=model)
        result: BuildResult = build_profile(
            manifest_path, caller=caller, return_details=True,
        )
        profile = result.profile
        llm_summary = (
            f"{result.llm_result.total_calls}/4 calls, "
            f"${result.llm_result.total_cost_usd:.4f}, "
            f"in={result.llm_result.total_input_tokens} "
            f"out={result.llm_result.total_output_tokens}"
        )
        pack_summary = (
            f"{result.pack.block_count} blocks "
            f"(from {result.pack.blocks_total_in_manifest} in manifest)"
        )
        diag_summary = (
            f"rejections={result.payload.diagnostics.total_rejections}, "
            f"fields_dropped={len(result.payload.diagnostics.fields_dropped)}, "
            f"items_dropped={result.payload.diagnostics.total_items_dropped}"
        )

    write_profile(profile, out_path)

    # Summary table
    q = profile.quality
    table = Table(title="Profile Summary", show_header=True, header_style="bold magenta")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Output", str(out_path))
    table.add_row("Source URL", profile.source_url)
    table.add_row("Name",
                  f"{profile.name.value or '-'} ({profile.name.source_type.value})")
    table.add_row("Category",
                  f"{profile.category.value.value if profile.category.value else '-'} "
                  f"({profile.category.source_type.value})")
    table.add_row("Tagline",
                  (profile.tagline.value or "-")[:80])
    table.add_row("Offerings", str(len(profile.offerings)))
    table.add_row("Audience type",
                  profile.audience_type.value.value if profile.audience_type.value else "-")
    table.add_row("Tone of voice",
                  profile.tone_of_voice.value.value if profile.tone_of_voice.value else "-")
    table.add_row("Value props", str(len(profile.value_propositions)))
    table.add_row("Trust signals", str(len(profile.trust_signals)))
    table.add_row("Service areas", str(len(profile.service_areas)))
    table.add_row("Contact channels",
                  f"phones={len(profile.contact_channels.phones)} "
                  f"emails={len(profile.contact_channels.emails)} "
                  f"wa={len(profile.contact_channels.whatsapp_numbers)} "
                  f"form={profile.contact_channels.has_contact_form}")
    table.add_row("Visual",
                  f"palette={len(profile.visual.palette_hex)} "
                  f"logo={profile.visual.logo_url is not None} "
                  f"primary={profile.visual.primary_color or '-'}")
    table.add_row("Languages", ", ".join(profile.languages) or "-")
    table.add_row("---", "---")
    table.add_row("Fields extracted", str(q.fields_extracted))
    table.add_row("Fields inferred", str(q.fields_inferred))
    table.add_row("Fields missing", str(q.fields_missing))
    table.add_row("Major missing", ", ".join(q.major_missing) or "-")
    table.add_row("Ready for strategy",
                  "[green]YES[/green]" if q.ready_for_strategy else "[red]NO[/red]")
    table.add_row("---", "---")
    table.add_row("Pack", pack_summary)
    table.add_row("LLM", llm_summary)
    table.add_row("Validator", diag_summary)
    console.print(table)

    if profile.quality.ready_for_strategy:
        raise typer.Exit(0)
    raise typer.Exit(2)


if __name__ == "__main__":
    app()