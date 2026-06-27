"""Tests for the JobTech plugin parsing and validation."""

import pytest

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.errors import SchemaValidationError
from pulsegraph.sources.jobtech import JobTechPlugin

AD = {
    "id": 4242,
    "headline": "AI Engineer",
    "description": {"text": "Build agent systems."},
}


# --- validation ---


def test_valid_ad_passes_validation() -> None:
    JobTechPlugin().validate_schema(AD)


def test_missing_description_is_drift() -> None:
    record = {"id": 1, "headline": "AI Engineer"}

    with pytest.raises(SchemaValidationError):
        JobTechPlugin().validate_schema(record)


# --- parsing ---


def test_parse_builds_content_and_external_id() -> None:
    item = JobTechPlugin().parse(AD)

    assert item.source is SourceKind.JOBTECH
    assert item.external_id == "4242"
    assert "AI Engineer" in item.content
    assert "Build agent systems." in item.content
    assert item.raw is AD


def test_parse_tolerates_missing_description_text() -> None:
    item = JobTechPlugin().parse({"id": 7, "headline": "Role"})

    assert item.content == "Role"
