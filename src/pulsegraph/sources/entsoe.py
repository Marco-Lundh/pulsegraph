"""ENTSO-E Transparency Platform source plugin (ADR 0004).

Watches day-ahead electricity prices from the ENTSO-E Transparency API.
That API speaks XML, so :meth:`EntsoePlugin.fetch` flattens the response
into one plain ``dict`` per price point; validation and parsing then work
on dicts exactly like the other plugins.
"""

import datetime
import xml.etree.ElementTree as ET

import httpx

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.base import FetchedItem, SourcePlugin
from pulsegraph.sources.schema import validate_required_fields

# A44 = day-ahead prices. A bidding zone if the watch gives no domain.
DAY_AHEAD_DOCUMENT_TYPE = "A44"
DEFAULT_DOMAIN = "10YSE-1--------K"  # Sweden (SE)

# Every price point carries its series id, position, and amount.
REQUIRED_FIELDS = ("mrid", "position", "price")


def _local(tag: str) -> str:
    """Strip any XML namespace from ``tag`` (``{ns}name`` -> ``name``)."""
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, name: str) -> ET.Element | None:
    """Return the first direct child of ``element`` named ``name``."""
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _text(element: ET.Element | None) -> str:
    """Return stripped text for ``element``, or ``""`` if absent."""
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def parse_price_points(xml_text: str) -> list[dict]:
    """Flatten an ENTSO-E day-ahead document into price-point dicts."""
    root = ET.fromstring(xml_text)
    points: list[dict] = []
    for series in root:
        if _local(series.tag) != "TimeSeries":
            continue
        mrid = _text(_find(series, "mRID"))
        currency = _text(_find(series, "currency_Unit.name"))
        period = _find(series, "Period")
        if period is None:
            continue
        interval = _find(period, "timeInterval")
        start = _text(_find(interval, "start")) if interval is not None else ""
        resolution = _text(_find(period, "resolution"))
        for point in period:
            if _local(point.tag) != "Point":
                continue
            points.append(
                {
                    "mrid": mrid,
                    "currency": currency,
                    "start": start,
                    "resolution": resolution,
                    "position": _text(_find(point, "position")),
                    "price": _text(_find(point, "price.amount")),
                }
            )
    return points


class EntsoePlugin(SourcePlugin):
    """Fetch, validate, and parse ENTSO-E day-ahead prices."""

    kind = SourceKind.ENTSOE

    def __init__(
        self,
        api_token: str,
        base_url: str = "https://web-api.tp.entsoe.eu/api",
    ) -> None:
        self._api_token = api_token
        self._base_url = base_url

    def fetch(self, query: str) -> list[dict]:
        """Return day-ahead price points for the bidding zone ``query``."""
        domain = query.strip() or DEFAULT_DOMAIN
        now = datetime.datetime.now(datetime.UTC)
        period_start = now.strftime("%Y%m%d2200")
        period_end = (now + datetime.timedelta(days=1)).strftime("%Y%m%d2200")
        response = httpx.get(
            self._base_url,
            params={
                "securityToken": self._api_token,
                "documentType": DAY_AHEAD_DOCUMENT_TYPE,
                "in_Domain": domain,
                "out_Domain": domain,
                "periodStart": period_start,
                "periodEnd": period_end,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return parse_price_points(response.text)

    def validate_schema(self, record: dict) -> None:
        """Raise if a required price-point field is missing (ADR 0010)."""
        validate_required_fields(record, REQUIRED_FIELDS, self.kind)

    def parse(self, record: dict) -> FetchedItem:
        """Normalize a price point into a ``FetchedItem``."""
        currency = record.get("currency", "")
        content = (
            f"Day-ahead price (position {record['position']}, "
            f"starting {record.get('start', '?')}): "
            f"{record['price']} {currency}/MWh"
        ).strip()
        return FetchedItem(
            source=self.kind,
            external_id=f"{record['mrid']}:{record['position']}",
            content=content,
            raw=record,
        )
