"""Errors raised by source plugins."""

from pulsegraph.domain.enums import SourceKind


class SchemaValidationError(Exception):
    """A source response did not match its expected schema.

    Raised by a plugin's ``validate_schema`` when a required field is
    missing (ADR 0010). The pipeline fails loud on this rather than
    processing malformed data silently.
    """

    def __init__(self, source: SourceKind, missing_fields: list[str]) -> None:
        self.source = source
        self.missing_fields = missing_fields
        joined = ", ".join(missing_fields)
        super().__init__(
            f"Source schema for {source.value} did not match the "
            f"expected format; missing required fields: {joined}"
        )
