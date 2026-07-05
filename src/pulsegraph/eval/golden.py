"""Golden datasets for offline evaluation (ADR 0012).

A golden dataset is a list of labeled examples per source type: the
ground-truth answer to "should this item have been notified?". Seed sets
are curated by hand and live as JSONL next to this module; the set grows
over time from human review-queue verdicts (``golden_from_decisions``),
closing the review -> dataset half of the improvement loop.
"""

import json
import pathlib
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pulsegraph.db.models import Analysis, Evaluation, Item, ReviewDecision
from pulsegraph.domain.enums import ReviewDecision as Decision
from pulsegraph.domain.enums import SourceKind

GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"


@dataclass(frozen=True, slots=True)
class GoldenExample:
    """One labeled item: the human ground truth for notify-or-not."""

    source: SourceKind
    content: str
    should_notify: bool
    note: str = ""


def load_golden_file(path: pathlib.Path) -> list[GoldenExample]:
    """Parse one JSONL golden file into examples."""
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        examples.append(
            GoldenExample(
                source=SourceKind(row["source"]),
                content=row["content"],
                should_notify=bool(row["should_notify"]),
                note=row.get("note", ""),
            )
        )
    return examples


def load_all_golden(
    directory: pathlib.Path = GOLDEN_DIR,
) -> dict[SourceKind, list[GoldenExample]]:
    """Load every ``*.jsonl`` dataset, grouped by source type."""
    grouped: dict[SourceKind, list[GoldenExample]] = defaultdict(list)
    for path in sorted(directory.glob("*.jsonl")):
        for example in load_golden_file(path):
            grouped[example.source].append(example)
    return dict(grouped)


def _to_jsonl(example: GoldenExample) -> str:
    """Serialize one example to a single JSONL line."""
    return json.dumps(
        {
            "source": example.source.value,
            "content": example.content,
            "should_notify": example.should_notify,
            "note": example.note,
        }
    )


def dump_golden(examples: list[GoldenExample], path: pathlib.Path) -> None:
    """Write *examples* to *path* as JSONL (one example per line)."""
    lines = [_to_jsonl(example) for example in examples]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_golden(examples: list[GoldenExample], path: pathlib.Path) -> None:
    """Append *examples* to *path* as JSONL, creating it if needed.

    Unlike :func:`dump_golden` this leaves existing curated lines untouched,
    so growing a dataset from review verdicts (ADR 0012) produces a minimal,
    reviewable diff rather than rewriting the whole file.
    """
    if not examples:
        return
    with path.open("a", encoding="utf-8") as handle:
        for example in examples:
            handle.write(_to_jsonl(example) + "\n")


# A human verdict of approved/corrected means the item was worth
# notifying; rejected means it was not (ADR 0012).
_DECISION_TO_NOTIFY = {
    Decision.APPROVED: True,
    Decision.CORRECTED: True,
    Decision.REJECTED: False,
}


def _content_from_item(item: Item | None, analysis: Analysis) -> str:
    """Reconstruct example text from the item, falling back to the summary."""
    if item is not None and isinstance(item.raw_payload, dict):
        title = str(item.raw_payload.get("title", ""))
        body = str(item.raw_payload.get("body", ""))
        text = f"{title}\n\n{body}".strip()
        if text:
            return text
    return analysis.result


def grow_golden(
    db: Session,
    golden_dir: pathlib.Path = GOLDEN_DIR,
) -> dict[SourceKind, int]:
    """Append review-derived examples to the golden datasets (ADR 0012).

    Closes the review -> dataset half of the improvement flywheel: each
    review-queue verdict becomes a labeled example appended to its source's
    dataset, unless an example with identical content is already present.
    Returns the number of new examples added per source; idempotent across
    repeated runs.
    """
    existing = load_all_golden(golden_dir)
    seen_content = {
        source: {example.content for example in examples}
        for source, examples in existing.items()
    }

    new_by_source: dict[SourceKind, list[GoldenExample]] = defaultdict(list)
    for example in golden_from_decisions(db):
        seen = seen_content.setdefault(example.source, set())
        if example.content in seen:
            continue
        seen.add(example.content)
        new_by_source[example.source].append(example)

    for source, examples in new_by_source.items():
        append_golden(examples, golden_dir / f"{source.value}.jsonl")

    return {
        source: len(examples) for source, examples in new_by_source.items()
    }


def golden_from_decisions(db: Session) -> list[GoldenExample]:
    """Grow the dataset from persisted human review verdicts (ADR 0012).

    Walks each ``ReviewDecision`` back to its item for the example text
    and labels it from the human's verdict. The single most valuable
    signal the product makes is turned into regression test data.
    """
    examples = []
    for decision in db.query(ReviewDecision).all():
        should_notify = _DECISION_TO_NOTIFY.get(decision.decision)
        if should_notify is None:
            continue
        evaluation = db.get(Evaluation, decision.evaluation_id)
        if evaluation is None:
            continue
        analysis = db.get(Analysis, evaluation.analysis_id)
        if analysis is None:
            continue
        item = db.get(Item, analysis.item_id)
        examples.append(
            GoldenExample(
                source=item.source if item else SourceKind.JOBTECH,
                content=_content_from_item(item, analysis),
                should_notify=should_notify,
                note=f"from review {decision.id}",
            )
        )
    return examples
