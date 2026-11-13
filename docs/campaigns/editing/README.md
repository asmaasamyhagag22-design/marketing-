# Campaign copy release

`campaign-copy@3` adds an evidence-bound CTA for reading a named section. With the same goal, publisher capture and CTA destination, the Five Guys example changes from “Read the explanation” to “Explore Bacon Burger”. Existing draft policies remain readable. Local replay reports eligibility for the candidate, and regular requests use the `stable` policy.

The 10-case replay produced 8 reviewable packages and 2 simulated acquisition failures per policy. Across 9 labelled critical adversarial edits, neither policy accepted an edit. The candidate accepted 7 of 8 labelled supported edits, compared with 1 of 8 on stable. The remaining conservative rejection was Buffalo's unregistered wording for the shared sauce. The runs measure support and wording outcomes. Human editing effort is pending. [Frozen protocol](PROTOCOL.md) · [Replay receipt](results/replay.json) · [Injected regression](results/regressed.json)

```bash
campaign_study=$(mktemp -d)
python -m workflows.campaign_eval --output "$campaign_study/replay.json"
python tools/review_campaign_editing.py "$campaign_study/packet"
```

The second command builds the blind review package with local Chromium, PostgreSQL and frozen publisher captures. It prints the location of the generated files. [Setup](../../../README.md) · [Run notes](EXECUTION.md)
