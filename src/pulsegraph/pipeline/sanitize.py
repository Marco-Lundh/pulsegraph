"""Input hardening for untrusted source content (ADR 0013).

Fetched text is treated as untrusted data, never as instructions. It
is normalized before it reaches a model: control characters stripped
and length capped. Combined with instruction/data separation and
structured output in the Analyzer, this blunts prompt-injection.
"""

import re

# Control characters except tab (\t), newline (\n), carriage return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_MAX_LENGTH = 20_000


def sanitize_text(text: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip control characters and cap the length of ``text``."""
    cleaned = _CONTROL_CHARS.sub("", text)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned.strip()
