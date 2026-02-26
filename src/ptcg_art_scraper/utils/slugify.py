"""Filesystem-safe slug generation."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_length: int = 80) -> str:
    """Convert *text* to a lowercase, filesystem-safe slug.

    * Unicode → ASCII (NFD + strip combining marks)
    * Replace non-alphanumeric characters with ``-``
    * Collapse consecutive ``-`` and strip leading/trailing ``-``
    * Truncate to *max_length*
    """
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    # collapse repeated dashes
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_length]
