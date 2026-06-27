"""Reusable schema validation for source plugins (ADR 0010)."""

from collections.abc import Iterable

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.errors import SchemaValidationError


def validate_required_fields(
    record: dict, required: Iterable[str], source: SourceKind
) -> None:
    """Ensure every required field is present in ``record``.

    A missing required field stops the run (ADR 0010). New, unexpected
    fields are deliberately tolerated — only absences of required
    fields are treated as drift.
    """
    missing = [field for field in required if field not in record]
    if missing:
        raise SchemaValidationError(source, missing)
