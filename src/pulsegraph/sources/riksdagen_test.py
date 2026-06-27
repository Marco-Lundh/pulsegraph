"""Tests for the Riksdagen plugin parsing and validation."""

import pytest

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.errors import SchemaValidationError
from pulsegraph.sources.riksdagen import RiksdagenPlugin

DOC = {
    "id": "HB01FiU1",
    "titel": "Utgiftsområde 2 Samhällsekonomi",
    "undertitel": "Betänkande",
    "summary": "Förslag om statens budget.",
}


def test_valid_document_passes_validation() -> None:
    RiksdagenPlugin().validate_schema(DOC)


def test_missing_title_is_drift() -> None:
    with pytest.raises(SchemaValidationError):
        RiksdagenPlugin().validate_schema({"id": "x"})


def test_parse_builds_content_and_external_id() -> None:
    item = RiksdagenPlugin().parse(DOC)

    assert item.source is SourceKind.RIKSDAGEN
    assert item.external_id == "HB01FiU1"
    assert "Utgiftsområde 2 Samhällsekonomi" in item.content
    assert "Betänkande" in item.content
    assert "Förslag om statens budget." in item.content
    assert item.raw is DOC


def test_parse_tolerates_missing_body() -> None:
    item = RiksdagenPlugin().parse({"id": "7", "titel": "Motion"})
    assert item.content == "Motion"
