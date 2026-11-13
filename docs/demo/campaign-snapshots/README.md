# Campaign source snapshots

These fixtures keep short publisher excerpts for engineering review. Each `manifest.json` records the source URL, capture time in UTC, the captured response hash, and the hash of the trimmed fixture used in replay. The replay verifies the fixture hash, labels evidence as `publisher_snapshot`, preserves capture dates, and uses a demo-only clock frozen at the latest capture.

| Fixture | Capture date | Retained evidence |
|---|---|---|
| Buffalo | 2026-11-13, 13:51 UTC | Page titles and the relevant menu item Open Graph descriptions. [Manifest](buffalo/manifest.json) |
| Five Guys | 2026-11-13, 14:12 UTC | The descriptions under Bacon Burger and Little Bacon Burger, with their headings. [Manifest](five-guys/manifest.json) |
| Nando’s | 2026-11-13, 14:12 UTC | Three menu item headings and their local paragraphs. [Manifest](nandos/manifest.json) |

Trimming removes scripts, trackers, publisher artwork, unrelated sections, and page furniture. Full HTML stays in local scratch. Replaying a fragment can change frequency-based ranking, so the Five Guys and Nando’s decisions were also checked against the full capture locally. The selected Nando’s subject agreed across the two versions and both forms. The chosen sentence differed between the full page and the fragment. [General planner results](../../campaigns/buffalo/review/README.md)

The snapshots are for the local engineering demo and review. See the [asset notes](../../../THIRD_PARTY_ASSETS.md).
