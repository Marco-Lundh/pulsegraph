#!/usr/bin/env python
"""Grow the golden datasets from human review verdicts (ADR 0012).

Thin CLI over :func:`pulsegraph.eval.golden.grow_golden`. Turns every
review-queue decision into a labeled golden example appended to its
source's dataset (skipping content already present), closing the
review -> dataset half of the improvement flywheel. New examples are
appended, not rewritten, so the result is a small diff a maintainer
reviews and commits.

    uv run python scripts/grow_golden.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.eval.golden import grow_golden


def main() -> int:
    """Grow the bundled datasets from the live review decisions."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        added = grow_golden(db)

    if not added:
        print("No new golden examples from review decisions.")
        return 0

    for source, count in sorted(added.items()):
        print(f"{source.value:10s} +{count}")
    total = sum(added.values())
    print(f"\nAdded {total} example(s). Review the diff and commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
