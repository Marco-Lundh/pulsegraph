"""Content hashing and deduplication (ADR 0003).

Dedup is per user: the same content seen through two of a user's
watches is stored once. The hash is computed from normalized text so
trivial whitespace or case differences do not defeat it.
"""

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lower-case and collapse runs of whitespace to a single space."""
    return _WHITESPACE.sub(" ", text).strip().lower()


def content_hash(text: str) -> str:
    """Return a stable SHA-256 hex digest of the normalized text."""
    normalized = normalize(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_duplicate(digest: str, seen: set[str]) -> bool:
    """Whether ``digest`` has already been seen by this user."""
    return digest in seen
