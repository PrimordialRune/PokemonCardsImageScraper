"""Typed exceptions for user-safe CLI behaviour."""

from __future__ import annotations


class ScraperError(Exception):
    """Base exception for expected scraper failures."""

    def __init__(self, user_message: str, *, debug_message: str | None = None) -> None:
        super().__init__(debug_message or user_message)
        self.user_message = user_message
        self.debug_message = debug_message or user_message


class ConfigurationError(ScraperError):
    """Raised when user input is invalid."""


class ResolutionError(ScraperError):
    """Raised when providers cannot resolve a card."""


class DownloadError(ScraperError):
    """Raised when an image cannot be downloaded."""


class InputFormatError(ScraperError):
    """Raised when a batch input file is invalid."""
