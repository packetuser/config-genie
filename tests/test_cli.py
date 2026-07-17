"""Tests for CLI module."""

from click.testing import CliRunner

from config_genie.cli import main


def test_main_command():
    """Test main CLI command runs successfully."""
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Welcome to Config-Genie!" in result.output

def test_netbox_command_select_flag_skips_prompt(mocker, monkeypatch):
    """--select should import a subset of NetBox devices without prompting."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = [
        {
            "name": "sw01",
            "primary_ip4": {"address": "10.0.0.1/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "Edge Switch"},
        },
        {
            "name": "sw02",
            "primary_ip4": {"address": "10.0.0.2/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "Access Switch"},
        },
    ]
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    runner = CliRunner()
    result = runner.invoke(main, ["netbox", "--select", "1"])

    assert result.exit_code == 0
    assert "Imported 1 of 2 devices" in result.output
    assert "sw01" in result.output


def test_netbox_command_defaults_to_switch_roles(mocker, monkeypatch):
    """Without --role, only devices with 'switch' in their role should show up."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = [
        {
            "name": "sw01",
            "primary_ip4": {"address": "10.0.0.1/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "Edge Switch"},
        },
        {
            "name": "rtr01",
            "primary_ip4": {"address": "10.0.0.2/24"},
            "device_type": {"model": "ISR4451"},
            "site": {"name": "HQ"},
            "role": {"name": "Router"},
        },
    ]
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    runner = CliRunner()
    result = runner.invoke(main, ["netbox", "--select", "all"])

    assert result.exit_code == 0
    assert "sw01" in result.output
    assert "rtr01" not in result.output
