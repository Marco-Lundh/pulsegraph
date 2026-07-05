"""Input hardening for untrusted source content (ADR 0013).

Fetched text is treated as untrusted data, never as instructions. It is
normalized before it reaches a model: control characters stripped, known
prompt-control markers neutralized, and length capped. Combined with the
instruction/data separation (the analyzer sends the item as a distinct
user turn, never concatenated into the instruction) and structured
output in the Analyzer, this blunts prompt-injection.
"""

import re

# Control characters except tab (\t), newline (\n), carriage return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Model chat/instruction control tokens. Legitimate source data never
# carries these; left in place, they could forge a system/turn boundary
# inside a role-tagged prompt and hijack the instruction (ADR 0013). We
# defang the structural markers (not natural-language phrases, which would
# cause false positives on real content); the instruction/data separation
# is the primary defense, this is belt-and-braces.
_INJECTION_MARKERS = re.compile(
    r"<\|[^|]*\|>"  # ChatML: <|im_start|>, <|system|>, <|endoftext|>
    r"|\[/?INST\]"  # Llama instruction tokens: [INST] / [/INST]
    r"|<</?SYS>>"  # Llama system markers: <<SYS>> / <</SYS>>
    r"|</?s>",  # BOS/EOS sentinels: <s> / </s>
    re.IGNORECASE,
)

DEFAULT_MAX_LENGTH = 20_000


def sanitize_text(text: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip control chars, neutralize prompt markers, cap the length."""
    cleaned = _CONTROL_CHARS.sub("", text)
    # Replace with a space so neutralizing a marker never fuses two words.
    cleaned = _INJECTION_MARKERS.sub(" ", cleaned)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned.strip()
