"""JobTech (Arbetsformedlingen) source plugin (ADR 0004).

Watches job ads from the open JobTech JobSearch API. Free text, so it
exercises the text path of the pipeline.
"""

import httpx

from pulsegraph.domain.enums import SourceKind
from pulsegraph.sources.base import FetchedItem, SourcePlugin
from pulsegraph.sources.schema import validate_required_fields

JOBTECH_SEARCH_URL = "https://jobsearch.api.jobtechdev.se/search"

# A required field that disappears is treated as drift (ADR 0010).
REQUIRED_FIELDS = ("id", "headline", "description")


class JobTechPlugin(SourcePlugin):
    """Fetch, validate, and parse JobTech job ads."""

    kind = SourceKind.JOBTECH

    def __init__(
        self, base_url: str = JOBTECH_SEARCH_URL, limit: int = 50
    ) -> None:
        self._base_url = base_url
        self._limit = limit

    def fetch(self, query: str) -> list[dict]:
        """Return raw job-ad records matching ``query``."""
        response = httpx.get(
            self._base_url,
            params={"q": query, "limit": self._limit},
            headers={"accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("hits", [])

    def validate_schema(self, record: dict) -> None:
        """Raise if a required JobTech field is missing (ADR 0010)."""
        validate_required_fields(record, REQUIRED_FIELDS, self.kind)

    def parse(self, record: dict) -> FetchedItem:
        """Normalize a job ad into a ``FetchedItem``."""
        description = record.get("description") or {}
        body = (
            description.get("text", "")
            if isinstance(description, dict)
            else ""
        )
        headline = record.get("headline", "")
        content = f"{headline}\n\n{body}".strip()
        return FetchedItem(
            source=self.kind,
            external_id=str(record["id"]),
            content=content,
            raw=record,
        )
