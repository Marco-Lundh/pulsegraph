"""The shared interface every source plugin implements (ADR 0004)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pulsegraph.domain.enums import SourceKind


@dataclass(frozen=True, slots=True)
class FetchedItem:
    """A normalized unit of content produced by a plugin.

    ``content`` is the text the Embedder and Analyzer operate on;
    ``raw`` is the untouched source record, retained for provenance.
    """

    source: SourceKind
    external_id: str | None
    content: str
    raw: dict


class SourcePlugin(ABC):
    """A plugin that fetches, validates, and parses one source.

    Adding a new source means implementing this interface — never
    editing the Fetcher core (ADR 0004).
    """

    kind: SourceKind

    @abstractmethod
    def fetch(self, query: str) -> list[dict]:
        """Return raw records from the source for the given query."""

    @abstractmethod
    def validate_schema(self, record: dict) -> None:
        """Raise ``SchemaValidationError`` if the record drifted."""

    @abstractmethod
    def parse(self, record: dict) -> FetchedItem:
        """Normalize a validated raw record into a ``FetchedItem``."""
