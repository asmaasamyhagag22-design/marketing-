# Buffalo Burger · static portfolio review

The target action is a click to browse the official menu and choose between Old School and Rastafari. The current publisher pages returned both item descriptions and a menu title. The browser followed the real **شوف المنيو** link and checked that both product names were visible. The review receipt binds the exact item quotes and menu page to the current run. [Old School](https://buffaloburger.com/menu/old-school) · [Rastafari](https://buffaloburger.com/menu/the-rastafari) · [Menu](https://buffaloburger.com/menu) · [Browser receipt](browser-result.json) · [Export receipt](campaign.json)

## Visual comparison

[Portrait and square across five stages](comparison.jpg)

| Stage | Observed on the render |
|---|---|
| Previous release | Ingredient artwork communicates the comparison. The sandwiches are absent, so the eye lands on the individual toppings in bordered cards. |
| Dark studio | Raking light gives convincing toasted texture and strong separation between fillings. Both burgers run off the edges, most visibly in the portrait. The close framing sacrifices the full silhouettes. |
| Daylight, first render | The diagonal surface frames both products and leaves a clear gap. Both edges are intact. The open bite exposes green jalapeño pieces at phone size. Gloss and the hanging sauce give the first take a more stylized presentation. |
| Daylight, first retouch | The edit softens the sauce and preserves the silhouettes. Argon caught that Old School’s sauce still read below its patty, and that the Rastafari bite leaned forward at an implausible angle. |
| Daylight, selected | The last edit moves the sauce above Old School’s patty and seats the cut bite flatter under the Rastafari bun. The cheddar sheet and embedded green pieces remain visible in both formats. |

Codex visual review (AI) inspected both final PNGs at their native 1080 × 1350 and 1080 × 1080 sizes, at 390-pixel raster width, and in a 390-pixel mobile viewport. Rastafari on the left has breading and green pieces inside the sliced bite. Old School on the right shows a continuous orange cheddar layer. The Arabic headline reads first, followed by the burgers, labels, and CTA. The sauce line contributes a separate detail. The disclosure remains the smallest text. The scene illustrates the publisher's named ingredients. Portions and exact presentation are artistic choices. The image uses no official photography or logo. [Portrait](poster-portrait.png) · [Square](poster-square.png) · [Phone portrait](poster-portrait-390.png) · [Phone square](poster-square-390.png) · [App portrait](app-portrait-mobile.png) · [App square](app-square-mobile.png)

## Provenance and spend

The two initial directions use Gemini 4 Argon for art direction and copy suggestions. The final brief adapts its first headline with common Egyptian Arabic spelling and retains the previously reviewed sauce sentence for the message. The second headline suggestion repeated the product labels on the poster, so the two directions share a single comparison headline. Gemini 3 Pro Image generated both scenes and edited the selected one twice. Adzy composites the scene with the Noto title, subject labels, disclosure, message and CTA. A recorded Vertex request created each scene. The runtime uses the approved bytes and renders locally. [Edition](edition.json) · [Request prompts](prompts/) · [Usage and rate calculation](pricing.json) · [Argon](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-argon) · [Image model](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-pro-image) · [Google Cloud prices](https://cloud.google.com/model-garden/pricing)

Gemini 4 Argon visual critique (AI) identified Old School and Rastafari in both sizes. The first review called out the position of the sauce and the apparently unsupported bite. The second review compared the retouches and confirmed that the sauce above the patty and the flatter filled bite are visible after the edit. These reviews provide judgments of the rendered pixels. The quote and field bindings establish the ingredient descriptions. [First AI critique](gemini-critique.md) · [Final AI critique](gemini-final-critique.md)

Vertex accepted all seven calls on `global`. The token-based estimate is **$0.646144** before credits, across three Argon calls and four image calls. The budget ledger reserved prior to dispatch and used the reported token usage on receipt. Billing settlement is unavailable. Preview, render, export, and replay inside Adzy used zero paid calls. [Per-attempt accounting](pricing.json)

## Export verification

Adzy's live Campaign run captured three publisher fields, rejected the wrong-product headline with HTTP 409, saved the reviewed wording, previewed and exported both PNGs, rejected a stale download with HTTP 409, and recovered an identical ZIP after restarting the app. The clean source checkout replayed the journey with frozen evidence. Its two PNGs matched the live export byte for byte. Each run recovered its own ZIP byte for byte, with a distinct approval and evidence record per run. [Live browser](browser-result.json) · [Clean checkout replay](replay-result.json) · [Rejected copy](rejected.json)

The disclosure is 29 px on the 1080 px canvas, about 10.5 px at 390 px image width. The live result is an automated local approval for downloading this campaign, with no external audience or human visual test. No Vodafone or Orange concept artwork turned up in the project source, worktrees, or tracked asset paths used for this review.
