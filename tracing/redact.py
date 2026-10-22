"""PII redaction for span inputs and outputs.

Traces are only useful if people are willing to look at them, and nobody
should have to handle raw customer PII to debug an agent. Span summaries are
redacted before they are stored.

Pattern order matters — specific patterns run BEFORE generic digit runs:

1. Card-like 16-digit runs (``4111 1111 1111 1111``).
2. Phone numbers in common formats: ``(555) 123-4567``,
   ``+1 (555) 123-4567``, ``555.123.4567``, ``555-123-4567``, ``5551234567``.
   If the generic digit-run rule ran first it would chew a phone number into
   fragments and leave recognisable pieces behind.
3. US SSNs: ``123-45-6789`` (3-2-4 digit groups).
4. Any remaining run of 9+ consecutive digits (account numbers and similar).

Dates such as ``2026-10-22`` are NOT redacted: their longest digit run is 4,
and losing timestamps from summaries would make traces much harder to read.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_CARD_RE = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
# 15-digit 4-6-5 card layout (e.g. 3782 822463 10005): no group reaches the
# 9-digit fallback, so it needs its own rule.
_CARD15_RE = re.compile(r"\b\d{4}[ -]\d{6}[ -]\d{5}\b")
_PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?(?:\(\d{3}\)\s*|\d{3}[\s.-]?)\d{3}[\s.-]?\d{4}\b"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGITS_RE = re.compile(r"\d{9,}")


def redact_text(text: str) -> str:
    """Return ``text`` with phone numbers, SSNs and card-like runs removed."""
    if not text:
        return text
    out = _CARD_RE.sub(REDACTED, text)
    out = _CARD15_RE.sub(REDACTED, out)
    out = _PHONE_RE.sub(REDACTED, out)
    out = _SSN_RE.sub(REDACTED, out)
    out = _LONG_DIGITS_RE.sub(REDACTED, out)
    return out
