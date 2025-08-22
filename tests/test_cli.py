"""Tests for CLI module."""

from click.testing import CliRunner

from config_genie.cli import main


def test_main_command():
    """Test main CLI command runs successfully."""
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Welcome to Config-Genie!" in result.output