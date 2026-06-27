"""Deterministic, offline adapters for the pipeline ports (ADR 0017).

These let the whole graph run on a laptop with no Ollama, no network,
and no cloud key — the local-first default. They are intentionally
simple stand-ins: real deployments swap in Ollama/Claude clients and an
Ollama embedder behind the same ports. The embedder still records its
model name so vectors from different models are never mixed (ADR 0014).
"""

import hashlib
import struct
from dataclasses import dataclass, field

from pulsegraph.domain.enums import ModelKind, SourceKind
from pulsegraph.pipeline.contracts import (
    AnalysisResult,
    NotificationDraft,
    UnknownSourceError,
)
from pulsegraph.sources.base import FetchedItem, SourcePlugin
from pulsegraph.sources.schema import validate_required_fields

EMBEDDING_DIM = 768


class HashingEmbedder:
    """A deterministic hashing embedder for offline development.

    The same text always maps to the same unit-norm vector, which is
    enough to exercise the storage and similarity paths without a model
    download. It is not semantically meaningful — production uses an
    Ollama embedding model behind this same port (ADR 0014).
    """

    model_name = "hashing-768-v1"

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        """Return a deterministic unit-norm vector for ``text``."""
        raw = bytearray()
        counter = 0
        seed = text.encode("utf-8")
        while len(raw) < self._dim * 4:
            block = hashlib.sha256(seed + counter.to_bytes(4)).digest()
            raw.extend(block)
            counter += 1
        floats = [
            struct.unpack("<i", raw[i : i + 4])[0] / 2_147_483_648.0
            for i in range(0, self._dim * 4, 4)
        ]
        norm = sum(value * value for value in floats) ** 0.5 or 1.0
        return [value / norm for value in floats]


class KeywordModelClient:
    """A deterministic analyzer used for offline runs and tests.

    Relevance grows with content length; local confidence is lower for
    short items, which lets the cloud fallback path (ADR 0002) be
    exercised. Labels flag any configured keyword found in the text.
    """

    def __init__(self, keywords: tuple[str, ...] = ()) -> None:
        self._keywords = tuple(keyword.lower() for keyword in keywords)

    def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
        """Analyze ``content`` deterministically with ``model``."""
        first = content.strip().split(". ", 1)[0][:200]
        summary = first or "(empty)"
        relevance = min(1.0, len(content) / 600.0)
        lower = content.lower()
        labels = tuple(kw for kw in self._keywords if kw in lower)
        if model is ModelKind.CLAUDE:
            confidence = 0.95
        else:
            confidence = 0.8 if len(content) >= 80 else 0.4
        return AnalysisResult(
            summary=summary,
            relevance=relevance,
            confidence=confidence,
            model=model,
            labels=labels,
        )


@dataclass(slots=True)
class InMemorySink:
    """Collects delivered notifications in memory (dashboard channel)."""

    delivered: list[NotificationDraft] = field(default_factory=list)

    def send(self, draft: NotificationDraft) -> None:
        """Record ``draft`` as delivered."""
        self.delivered.append(draft)


@dataclass(slots=True)
class DictSourceRegistry:
    """An in-memory source registry backed by a plugin mapping."""

    plugins: dict[SourceKind, SourcePlugin] = field(default_factory=dict)

    def register(self, plugin: SourcePlugin) -> None:
        """Add or replace the plugin for ``plugin.kind``."""
        self.plugins[plugin.kind] = plugin

    def get(self, kind: SourceKind) -> SourcePlugin:
        """Return the plugin for ``kind`` or raise UnknownSourceError."""
        try:
            return self.plugins[kind]
        except KeyError as exc:
            raise UnknownSourceError(str(kind)) from exc


class StaticSourcePlugin(SourcePlugin):
    """A source plugin that returns preloaded records (fixtures).

    Lets the pipeline run end to end without a live API, backing the
    recorded-fixtures mode (ADR 0019).
    """

    def __init__(
        self,
        kind: SourceKind,
        records: list[dict],
        required_fields: tuple[str, ...] = ("id", "title", "body"),
    ) -> None:
        self.kind = kind
        self._records = records
        self._required = required_fields

    def fetch(self, query: str) -> list[dict]:
        """Return the preloaded records, ignoring ``query``."""
        return list(self._records)

    def validate_schema(self, record: dict) -> None:
        """Raise if a required field is missing (ADR 0010)."""
        validate_required_fields(record, self._required, self.kind)

    def parse(self, record: dict) -> FetchedItem:
        """Normalize a record into a ``FetchedItem``."""
        title = str(record.get("title", ""))
        body = str(record.get("body", ""))
        content = f"{title}\n\n{body}".strip()
        return FetchedItem(
            source=self.kind,
            external_id=str(record["id"]),
            content=content,
            raw=record,
        )
