"""Records and ports the agent pipeline depends on (ADR 0001).

The six agents never import a concrete model client, embedder, or
source directly. They depend on the ``Protocol`` ports declared here,
so the same graph runs against local adapters (offline, deterministic)
or real services without changing a node.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pulsegraph.domain.enums import EvalStatus, ModelKind, SourceKind
from pulsegraph.sources.base import FetchedItem, SourcePlugin


class UnknownSourceError(LookupError):
    """Raised when no plugin is registered for a source kind."""


@dataclass(frozen=True, slots=True)
class WatchSpec:
    """What a single pipeline run is asked to watch."""

    user_id: str
    source: SourceKind
    query: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """The Analyzer's structured verdict on one item (ADR 0011).

    ``relevance`` is how notable the item is for the watch;
    ``confidence`` is the model's certainty in its own output and
    drives the cloud fallback decision (ADR 0002).
    """

    summary: str
    relevance: float
    confidence: float
    model: ModelKind
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """An analysis paired with the item and hash it describes."""

    item: FetchedItem
    content_hash: str
    result: AnalysisResult


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """The Evaluator's gate decision over one analysis (ADR 0006)."""

    analysis: AnalysisRecord
    status: EvalStatus
    reason: str


@dataclass(frozen=True, slots=True)
class NotificationDraft:
    """A notification the Notifier hands to a delivery sink (ADR 0016).

    ``dedup_key`` makes redelivery idempotent: the same item is never
    sent twice to the same user.
    """

    user_id: str
    title: str
    body: str
    dedup_key: str
    labels: tuple[str, ...] = field(default=())


@runtime_checkable
class SourceRegistry(Protocol):
    """Resolves a source kind to its plugin (ADR 0004)."""

    def get(self, kind: SourceKind) -> SourcePlugin:
        """Return the plugin for ``kind`` or raise UnknownSourceError."""


@runtime_checkable
class Embedder(Protocol):
    """Turns text into a vector (ADR 0014)."""

    model_name: str

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for ``text``."""


@runtime_checkable
class ModelClient(Protocol):
    """Runs an analysis on one model class (ADR 0002)."""

    def analyze(self, content: str, model: ModelKind) -> AnalysisResult:
        """Analyze ``content`` with the given model class."""


@runtime_checkable
class NotificationSink(Protocol):
    """Delivers a notification over one channel (ADR 0016)."""

    def send(self, draft: NotificationDraft) -> None:
        """Deliver ``draft``; raise on a delivery failure."""
