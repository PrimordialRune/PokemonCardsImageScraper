"""CLI smoke tests."""

import re
from pathlib import Path

from typer.testing import CliRunner

from ptcg_art_scraper.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class TestCLIHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "scrape" in result.output
        assert "normalize" in result.output
        assert "verify" in result.output

    def test_scrape_help(self):
        result = runner.invoke(app, ["scrape", "--help"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "--out" in plain
        assert "--provider" in plain

    def test_normalize_help(self):
        result = runner.invoke(app, ["normalize", "--help"])
        assert result.exit_code == 0
        assert "--input" in _strip_ansi(result.output)

    def test_verify_help(self):
        result = runner.invoke(app, ["verify", "--help"])
        assert result.exit_code == 0
        assert "--input" in _strip_ansi(result.output)


class TestVerifyCommand:
    def test_verify_empty_dir(self, tmp_path: Path):
        result = runner.invoke(app, ["verify", "--input", str(tmp_path)])
        assert result.exit_code == 0
        assert "0 image(s)" in result.output

    def test_verify_nonexistent_dir(self):
        result = runner.invoke(app, ["verify", "--input", "/nonexistent/path"])
        assert result.exit_code == 1


class TestNormalizeCommand:
    def test_normalize_empty(self, tmp_path: Path):
        out = tmp_path / "out"
        result = runner.invoke(app, ["normalize", "--input", str(tmp_path), "--out", str(out)])
        assert result.exit_code == 0
        assert "Normalized 0 image(s)" in result.output

    def test_normalize_nonexistent(self, tmp_path: Path):
        result = runner.invoke(
            app, ["normalize", "--input", "/nonexistent", "--out", str(tmp_path / "out")]
        )
        assert result.exit_code == 1


class TestScrapeCommand:
    def test_scrape_no_args(self):
        result = runner.invoke(app, ["scrape", "--out", "/tmp/out"])
        assert result.exit_code == 1
