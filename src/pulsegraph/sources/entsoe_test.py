"""Tests for the ENTSO-E plugin XML flattening, parsing, and validation."""

import pytest

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.entsoe import EntsoePlugin, parse_price_points
from pulsegraph.sources.errors import SchemaValidationError

# Day-ahead document with a namespace (any ns is stripped) and two
# price points.
SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:entsoe:publicationdocument:7:3">
  <mRID>doc-1</mRID>
  <TimeSeries>
    <mRID>1</mRID>
    <currency_Unit.name>EUR</currency_Unit.name>
    <Period>
      <timeInterval>
        <start>2026-06-27T22:00Z</start>
        <end>2026-06-28T22:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <price.amount>23.86</price.amount>
      </Point>
      <Point>
        <position>2</position>
        <price.amount>19.50</price.amount>
      </Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


def test_parse_price_points_flattens_xml() -> None:
    points = parse_price_points(SAMPLE_XML)

    assert len(points) == 2
    first = points[0]
    assert first["mrid"] == "1"
    assert first["currency"] == "EUR"
    assert first["position"] == "1"
    assert first["price"] == "23.86"
    assert first["start"] == "2026-06-27T22:00Z"
    assert first["resolution"] == "PT60M"


def test_parse_price_points_ignores_documents_without_series() -> None:
    empty = (
        '<Publication_MarketDocument xmlns="urn:x">'
        "<mRID>d</mRID></Publication_MarketDocument>"
    )
    assert parse_price_points(empty) == []


def _plugin() -> EntsoePlugin:
    return EntsoePlugin(api_token="token")


def test_valid_point_passes_validation() -> None:
    _plugin().validate_schema(parse_price_points(SAMPLE_XML)[0])


def test_missing_price_is_drift() -> None:
    with pytest.raises(SchemaValidationError):
        _plugin().validate_schema({"mrid": "1", "position": "1"})


def test_parse_builds_content_and_external_id() -> None:
    point = parse_price_points(SAMPLE_XML)[0]
    item = _plugin().parse(point)

    assert item.source is SourceKind.ENTSOE
    assert item.external_id == "1:1"
    assert "23.86 EUR/MWh" in item.content
    assert item.raw is point
