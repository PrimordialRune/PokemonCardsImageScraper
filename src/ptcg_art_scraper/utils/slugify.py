"""Filesystem-safe slug generation."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_length: int = 80) -> str:
    """Convert *text* to a filesystem-safe slug.

    * Unicode is normalized (NFKD) and non-ASCII stripped.
    * Whitespace / special chars become ``-``.
    * Consecutive dashes collapsed; leading/trailing dashes removed.
    * Truncated to *max_length* on a dash boundary when possible.
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-")
    if len(text) > max_length:
        truncated = text[:max_length]
        if "-" in truncated:
            truncated = truncated[: truncated.rfind("-")]
        text = truncated.strip("-")
    return text or "card"
