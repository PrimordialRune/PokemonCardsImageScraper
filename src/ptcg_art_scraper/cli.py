"""Compatibility entry-point for the redesigned CLI."""

from ptcg_art_scraper.providers import get_provider as _get_provider
from ptcg_art_scraper.ui.cli.app import app

__all__ = ["app", "_get_provider"]
