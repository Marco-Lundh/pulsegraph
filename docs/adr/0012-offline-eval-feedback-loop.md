# ADR 0012: Offline evaluation, golden datasets and the human-feedback loop

## Status
Accepted

## Context
ADR 0006 made eval a live pipeline step but deliberately deferred offline regression testing. A full product needs two more things: (a) a labeled golden dataset to catch quality regressions *before* they reach users, and (b) a way to grow that dataset over time. The review queue's human verdicts (ADR 0006) are exactly that signal, but they are currently not persisted — the highest-value data the system produces is thrown away.

## Decision
- Capture every human review-queue verdict in `review_decisions` (decision, an optional corrected label, the reviewer, a note). This is ground truth.
- Maintain golden datasets per source type, seeded from curated items and grown from `review_decisions`.
- An offline eval harness runs the datasets against the current pinned prompt/model versions (ADR 0011) and reports metrics per source type (relevance precision/recall, confidence calibration).
- The harness is a **CI release gate** (ADR 0019): a deploy is blocked if metrics regress beyond a configurable threshold.
- Confidence thresholds (ADR 0002/0006) are tuned empirically from this data, not guessed.

## Alternatives considered
- **Live eval only** — no pre-deploy safety net; a regression is discovered only after it has already affected users.
- **Manual spot-checking** — not repeatable and does not scale.
- **Discarding review verdicts** — wastes the single most valuable improvement signal the product generates.

## Consequences
- **Easier:** closes the improvement flywheel (review → dataset → thresholds/prompts → eval) and gives an objective release gate.
- **Harder:** dataset curation and maintenance, defining metrics per source type (a job ad, a motion, and a price series differ), and labeling effort.
- Builds on ADR 0006 (live eval), ADR 0011 (versioning for attribution), and feeds ADR 0019 (CI).
