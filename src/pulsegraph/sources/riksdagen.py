"""Riksdagen (Swedish Parliament) source plugin (ADR 0004).

Watches documents — motions, propositions, written questions — from the
open Riksdagen document API. Free text, so it exercises the text path of
the pipeline like JobTech does.
"""

import httpx

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.base import FetchedItem, SourcePlugin
from pulsegraph.sources.schema import validate_required_fields

RIKSDAGEN_LIST_URL = "https://data.riksdagen.se/dokumentlista/"

# Every document carries an id and a title; their absence is drift.
REQUIRED_FIELDS = ("id", "titel")


class RiksdagenPlugin(SourcePlugin):
    """Fetch, validate, and parse Riksdagen documents."""

    kind = SourceKind.RIKSDAGEN

    def __init__(
        self, base_url: str = RIKSDAGEN_LIST_URL, limit: int = 50
    ) -> None:
        self._base_url = base_url
        self._limit = limit

    def fetch(self, query: str) -> list[dict]:
        """Return raw document records matching ``query``."""
        response = httpx.get(
            self._base_url,
            params={
                "sok": query,
                "utformat": "json",
                "sort": "datum",
                "sortorder": "desc",
                "p": 1,
            },
            headers={"accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        listing = response.json().get("dokumentlista", {})
        documents = listing.get("dokument", [])
        return documents[: self._limit]

    def validate_schema(self, record: dict) -> None:
        """Raise if a required Riksdagen field is missing (ADR 0010)."""
        validate_required_fields(record, REQUIRED_FIELDS, self.kind)

    def parse(self, record: dict) -> FetchedItem:
        """Normalize a document into a ``FetchedItem``."""
        title = str(record.get("titel", ""))
        subtitle = str(record.get("undertitel", ""))
        body = str(record.get("summary") or record.get("notis") or "")
        heading = " — ".join(part for part in (title, subtitle) if part)
        content = f"{heading}\n\n{body}".strip()
        return FetchedItem(
            source=self.kind,
            external_id=str(record["id"]),
            content=content,
            raw=record,
        )
