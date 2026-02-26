"""CLI smoke tests."""

import os
import tempfile

from typer.testing import CliRunner

from ptcg_art_scraper.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scrape" in result.output
    assert "normalize" in result.output
    assert "verify" in result.output


def test_scrape_no_args():
    result = runner.invoke(app, ["scrape"])
    # Should fail – missing --out
    assert result.exit_code != 0


def test_scrape_no_query():
    with tempfile.TemporaryDirectory() as td:
        result = runner.invoke(app, ["scrape", "--out", td])
        # Should fail – no --query or --input
        assert result.exit_code != 0


def test_verify_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        result = runner.invoke(app, ["verify", "--input", td])
        assert result.exit_code == 0


def test_normalize_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out")
        result = runner.invoke(app, ["normalize", "--input", td, "--out", out])
        assert result.exit_code == 0
