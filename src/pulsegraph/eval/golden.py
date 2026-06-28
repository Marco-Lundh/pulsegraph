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


def dump_golden(examples: list[GoldenExample], path: pathlib.Path) -> None:
    """Write *examples* to *path* as JSONL (one example per line)."""
    lines = [
        json.dumps(
            {
                "source": example.source.value,
                "content": example.content,
                "should_notify": example.should_notify,
                "note": example.note,
            }
        )
        for example in examples
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
