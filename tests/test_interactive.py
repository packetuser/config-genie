"""Tests for the interactive session's NetBox integration."""

import config_genie.inventory as inventory_module
from config_genie.interactive import InteractiveSession


def _make_session(mocker):
    # Avoid auto-loading devices.yaml from the repo root during tests
    mocker.patch("os.path.exists", return_value=False)
    return InteractiveSession()


def test_do_netbox_uses_env_vars(mocker, monkeypatch, capsys):
    """netbox command should use NETBOX_URL/NETBOX_TOKEN env vars when set."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = [
        {
            "name": "sw01",
            "primary_ip4": {"address": "10.0.0.1/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "access"},
        }
    ]
    mock_api_factory = mocker.patch(
        "config_genie.inventory.pynetbox.api", return_value=mock_api
    )
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("site=hq role=access")

    mock_api_factory.assert_called_once_with(
        "https://netbox.example.com", token="envtoken"
    )
    mock_api.dcim.devices.filter.assert_called_once_with(
        status="active", site="hq", role="access"
    )
    assert session.inventory.get_device("sw01") is not None
    assert session.inventory_path == "netbox:https://netbox.example.com"


def test_do_netbox_prompts_for_missing_credentials(mocker, monkeypatch):
    """netbox command should prompt interactively if env vars are unset."""
    monkeypatch.delenv("NETBOX_URL", raising=False)
    monkeypatch.delenv("NETBOX_TOKEN", raising=False)

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = []
    mock_api_factory = mocker.patch(
        "config_genie.inventory.pynetbox.api", return_value=mock_api
    )
    mocker.patch(
        "config_genie.interactive.Prompt.ask", return_value="https://netbox.example.com"
    )
    mocker.patch("config_genie.interactive.getpass.getpass", return_value="mytoken")
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("")

    mock_api_factory.assert_called_once_with(
        "https://netbox.example.com", token="mytoken"
    )


def test_do_netbox_handles_connection_error(mocker, monkeypatch, capsys):
    """netbox command should surface connection errors without raising."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mocker.patch(
        "config_genie.inventory.pynetbox.api",
        side_effect=ConnectionError("boom"),
    )

    session = _make_session(mocker)
    # Should not raise
    session.do_netbox("")
    assert session.inventory.get_all_devices() == []
