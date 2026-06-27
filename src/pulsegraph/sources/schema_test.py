"""Tests for reusable schema validation."""

import pytest

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.errors import SchemaValidationError
from pulsegraph.sources.schema import validate_required_fields

REQUIRED = ("id", "headline")


# --- valid records ---


def test_passes_when_all_required_present() -> None:
    validate_required_fields(
        {"id": 1, "headline": "x"}, REQUIRED, SourceKind.JOBTECH
    )


def test_tolerates_extra_unknown_fields() -> None:
    # New fields must not be treated as drift (ADR 0010).
    record = {"id": 1, "headline": "x", "brand_new_field": "ok"}

    validate_required_fields(record, REQUIRED, SourceKind.JOBTECH)


# --- drift ---


def test_raises_when_required_field_missing() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_required_fields({"id": 1}, REQUIRED, SourceKind.JOBTECH)

    error = exc_info.value
    assert error.source is SourceKind.JOBTECH
    assert error.missing_fields == ["headline"]
    assert "jobtech" in str(error)
