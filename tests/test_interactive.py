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
    mocker.patch("config_genie.interactive.Prompt.ask", return_value="all")
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


def test_do_netbox_insecure_flag_disables_verification(mocker, monkeypatch):
    """netbox insecure should disable TLS verification on the pynetbox session."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = []
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("insecure")

    assert mock_api.http_session.verify is False


def test_do_netbox_verify_ssl_env_var(mocker, monkeypatch):
    """NETBOX_VERIFY_SSL=false should also disable TLS verification."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")
    monkeypatch.setenv("NETBOX_VERIFY_SSL", "false")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = []
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("")

    assert mock_api.http_session.verify is False


def test_do_netbox_defaults_to_switch_roles(mocker, monkeypatch):
    """Without an explicit role filter, only devices with 'switch' in their
    role name should be presented as candidates."""
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
    mocker.patch("config_genie.interactive.Prompt.ask", return_value="all")
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("")

    mock_api.dcim.devices.filter.assert_called_once_with(status="active")
    assert session.inventory.get_device("sw01") is not None
    assert session.inventory.get_device("rtr01") is None


def test_do_netbox_role_all_disables_switch_filter(mocker, monkeypatch):
    """role=all should bypass the default switch-only filtering."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = [
        {
            "name": "rtr01",
            "primary_ip4": {"address": "10.0.0.2/24"},
            "device_type": {"model": "ISR4451"},
            "site": {"name": "HQ"},
            "role": {"name": "Router"},
        },
    ]
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)
    mocker.patch("config_genie.interactive.Prompt.ask", return_value="all")
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("role=all")

    assert session.inventory.get_device("rtr01") is not None


def test_do_netbox_selection_imports_subset(mocker, monkeypatch):
    """Selecting a subset of candidates should only import chosen devices."""
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
    mocker.patch("config_genie.interactive.Prompt.ask", return_value="1")
    mocker.patch("rich.prompt.Confirm.ask", return_value=False)

    session = _make_session(mocker)
    session.do_netbox("")

    assert session.inventory.get_device("sw01") is not None
    assert session.inventory.get_device("sw02") is None


def test_load_inventory_allows_reload_without_duplicate_error(mocker, tmp_path):
    """Re-loading an inventory file (or the auto-loaded one) should replace
    devices instead of raising 'duplicate device name'."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))
    assert len(session.inventory.devices) == 1

    # Reload the same file again - should not raise or duplicate
    session._load_inventory(str(inventory_file))
    assert len(session.inventory.devices) == 1
    assert session.inventory.get_device("sw01") is not None


def test_load_inventory_keeps_previous_on_failure(mocker, tmp_path):
    """A failed reload should not wipe out the previously loaded inventory."""
    good_file = tmp_path / "good.yaml"
    good_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(
        "devices:\n"
        "  - name: bad\n"
        "    ip_address: not-an-ip!!!\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(good_file))
    assert len(session.inventory.devices) == 1

    session._load_inventory(str(bad_file))
    # Previous good inventory should still be intact
    assert len(session.inventory.devices) == 1
    assert session.inventory.get_device("sw01") is not None


def test_resolve_devices_single_device_by_name(mocker, tmp_path):
    """A bare device name should resolve to that single device, not fall
    through to 'Invalid selection' (previously only comma-separated names
    were recognized)."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: '256'\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: '400'\n"
        "    ip_address: 10.0.0.2\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    devices = session._resolve_devices_from_arg("256")
    assert [d.name for d in devices] == ["256"]


def test_resolve_devices_multiple_devices_by_name(mocker, tmp_path):
    """Comma-separated names should still resolve to multiple devices."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: '256'\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: '400'\n"
        "    ip_address: 10.0.0.2\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    devices = session._resolve_devices_from_arg("256,400")
    assert sorted(d.name for d in devices) == ["256", "400"]


def test_resolve_devices_unknown_name_reports_invalid(mocker, tmp_path, capsys):
    """A name that isn't a device and isn't a filter should report an error
    rather than silently resolving to nothing."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    devices = session._resolve_devices_from_arg("nonexistent")
    captured = capsys.readouterr()
    assert "Invalid selection" in captured.out
    assert devices is None


def test_do_connect_with_names_selects_and_connects(mocker, tmp_path):
    """'connect <names>' should select the named devices and connect to
    them directly, without requiring a prior 'select' call."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: '561'\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: '663'\n"
        "    ip_address: 10.0.0.2\n"
        "  - name: '400'\n"
        "    ip_address: 10.0.0.3\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    # Pretend a stale selection of a different device exists
    session.selected_devices = [session.inventory.get_device("400")]

    mocker.patch.object(session.connection_manager, "credentials", "fake-creds")
    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("561,663")

    assert sorted(d.name for d in session.selected_devices) == ["561", "663"]
    connected_names = sorted(call.args[0].name for call in mock_connect.call_args_list)
    assert connected_names == ["561", "663"]


def test_do_connect_without_arg_uses_existing_selection(mocker, tmp_path):
    """'connect' with no argument should fall back to the current selection
    (unchanged behavior)."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))
    session.selected_devices = [session.inventory.get_device("sw01")]

    mocker.patch.object(session.connection_manager, "credentials", "fake-creds")
    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("")

    mock_connect.assert_called_once()
    assert mock_connect.call_args[0][0].name == "sw01"


def test_do_connect_single_name_no_select_needed(mocker, tmp_path):
    """A single device name should also work directly with 'connect'."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: '561'\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))
    # No prior select call at all
    assert session.selected_devices == []

    mocker.patch.object(session.connection_manager, "credentials", "fake-creds")
    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("561")

    assert [d.name for d in session.selected_devices] == ["561"]
    mock_connect.assert_called_once()
    assert mock_connect.call_args[0][0].name == "561"
