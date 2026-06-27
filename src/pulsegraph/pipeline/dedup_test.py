"""Tests for content hashing and deduplication."""

from pulsegraph.pipeline.dedup import (
    content_hash,
    is_duplicate,
    normalize,
)

# --- normalization ---


def test_normalize_collapses_whitespace_and_case() -> None:
    assert normalize("  AI   Engineer\n\nRole ") == "ai engineer role"


# --- hashing ---


def test_hash_is_stable_across_trivial_differences() -> None:
    a = content_hash("AI Engineer")
    b = content_hash("  ai   engineer ")

    assert a == b


def test_hash_differs_for_distinct_content() -> None:
    assert content_hash("AI Engineer") != content_hash("Data Engineer")


# --- duplicate detection ---


def test_is_duplicate_against_seen_set() -> None:
    digest = content_hash("AI Engineer")

    assert is_duplicate(digest, {digest}) is True
    assert is_duplicate(digest, set()) is False
