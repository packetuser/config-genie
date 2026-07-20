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


def test_inventory_load_subcommand(mocker, tmp_path):
    """'inventory load <path>' should load an inventory file."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session.do_inventory(f"load {inventory_file}")

    assert len(session.inventory.devices) == 1
    assert session.inventory.get_device("sw01") is not None


def test_inventory_bare_path_shorthand_still_loads(mocker, tmp_path):
    """'inventory <path>' (no 'load' keyword) should still work for
    backward compatibility."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session.do_inventory(str(inventory_file))

    assert len(session.inventory.devices) == 1


def test_inventory_list_subcommand_shows_devices(mocker, tmp_path, capsys):
    """'inventory list' should display the loaded devices."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
        "    model: 2960X\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    session.do_inventory("list")
    captured = capsys.readouterr()
    assert "sw01" in captured.out


def test_inventory_list_with_filter(mocker, tmp_path, capsys):
    """'inventory list model=<x>' should filter devices by model."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
        "    model: 2960X\n"
        "  - name: sw02\n"
        "    ip_address: 10.0.0.2\n"
        "    model: 3560\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    session.do_inventory("list model=2960X")
    captured = capsys.readouterr()
    assert "sw01" in captured.out
    assert "sw02" not in captured.out


def test_inventory_load_without_path_reports_usage(mocker, capsys):
    """'inventory load' with no path should print a usage error, not crash."""
    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()

    session.do_inventory("load")
    captured = capsys.readouterr()
    assert "Usage: inventory load" in captured.out


def test_inventory_list_shows_connected_status(mocker, tmp_path, capsys):
    """'inventory list' should show a Connected column reflecting actual
    connection state, not the removed 'selected' concept."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: sw02\n"
        "    ip_address: 10.0.0.2\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    fake_conn = mocker.Mock()
    fake_conn.connected = True
    session.connection_manager.connections["sw01"] = fake_conn

    session.do_inventory("list")
    captured = capsys.readouterr()
    assert "Connected" in captured.out
    assert "selected" not in captured.out.lower()


def test_do_connect_skips_already_connected_devices(mocker, tmp_path):
    """Re-running 'connect' (e.g. after a partial failure) should not
    reconnect devices that already have a live connection - it should only
    retry the ones that aren't connected yet."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: sw02\n"
        "    ip_address: 10.0.0.2\n"
    )

    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))
    session.selected_devices = [
        session.inventory.get_device("sw01"),
        session.inventory.get_device("sw02"),
    ]

    mocker.patch.object(session.connection_manager, "credentials", "fake-creds")

    fake_conn = mocker.Mock()
    fake_conn.connected = True
    session.connection_manager.connections["sw01"] = fake_conn

    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("")

    mock_connect.assert_called_once()
    assert mock_connect.call_args[0][0].name == "sw02"


def test_do_connect_all_already_connected_reports_status_without_reconnecting(mocker, tmp_path):
    """If every selected device is already connected, 'connect' should just
    report the status without calling connect_device at all."""
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

    fake_conn = mocker.Mock()
    fake_conn.connected = True
    session.connection_manager.connections["sw01"] = fake_conn

    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("")

    mock_connect.assert_not_called()


def _no_more_input():
    raise AssertionError("read_next should not be called without an escape sequence")


def test_picker_space_toggles_selection():
    cursor, picked, action = InteractiveSession._picker_handle_key(
        ' ', 0, set(), 3, _no_more_input
    )
    assert picked == {0}
    assert action is None
    cursor, picked, action = InteractiveSession._picker_handle_key(
        ' ', 0, picked, 3, _no_more_input
    )
    assert picked == set()
    assert action is None


def test_picker_arrow_down_moves_cursor_and_clamps():
    reads = iter(['[', 'B'])
    cursor, picked, action = InteractiveSession._picker_handle_key(
        '\x1b', 0, set(), 2, lambda: next(reads)
    )
    assert cursor == 1
    assert action is None
    # Already at last row: further Down should clamp, not wrap.
    reads = iter(['[', 'B'])
    cursor, picked, action = InteractiveSession._picker_handle_key(
        '\x1b', 1, set(), 2, lambda: next(reads)
    )
    assert cursor == 1


def test_picker_arrow_up_clamps_at_zero():
    reads = iter(['[', 'A'])
    cursor, picked, action = InteractiveSession._picker_handle_key(
        '\x1b', 0, set(), 3, lambda: next(reads)
    )
    assert cursor == 0


def test_picker_select_all_and_clear():
    cursor, picked, action = InteractiveSession._picker_handle_key(
        'a', 0, set(), 4, _no_more_input
    )
    assert picked == {0, 1, 2, 3}
    cursor, picked, action = InteractiveSession._picker_handle_key(
        'c', 0, picked, 4, _no_more_input
    )
    assert picked == set()


def test_picker_enter_confirms():
    cursor, picked, action = InteractiveSession._picker_handle_key(
        '\r', 0, {1}, 3, _no_more_input
    )
    assert action is True
    assert picked == {1}


def test_picker_q_and_ctrl_c_cancel():
    _, _, action = InteractiveSession._picker_handle_key('q', 0, set(), 3, _no_more_input)
    assert action is False
    _, _, action = InteractiveSession._picker_handle_key('\x03', 0, set(), 3, _no_more_input)
    assert action is False


def test_picker_bare_esc_cancels():
    # ESC not followed by '[' (e.g. read_next returns something else) cancels.
    reads = iter(['x'])
    _, _, action = InteractiveSession._picker_handle_key(
        '\x1b', 0, set(), 3, lambda: next(reads)
    )
    assert action is False


def test_picker_no_devices_does_nothing():
    cursor, picked, action = InteractiveSession._picker_handle_key(
        ' ', 0, set(), 0, _no_more_input
    )
    assert action is None
    assert picked == set()


def test_pick_devices_interactively_requires_tty(mocker, tmp_path):
    """Without a real terminal, the picker should bail out gracefully instead
    of attempting to enter raw mode."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )
    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    mocker.patch("sys.stdin.isatty", return_value=False)
    result = session._pick_devices_interactively()
    assert result is None


def test_do_connect_pick_uses_picker_result(mocker, tmp_path):
    """'connect pick' should set selected_devices from the picker and then
    proceed to connect exactly those devices."""
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
        "  - name: sw02\n"
        "    ip_address: 10.0.0.2\n"
    )
    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))

    sw02 = session.inventory.get_device("sw02")
    mocker.patch.object(session, "_pick_devices_interactively", return_value=[sw02])
    mocker.patch.object(session.connection_manager, "credentials", "fake-creds")
    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("pick")

    assert session.selected_devices == [sw02]
    mock_connect.assert_called_once_with(sw02)


def test_do_connect_pick_cancelled_leaves_selection_unchanged(mocker, tmp_path):
    inventory_file = tmp_path / "devices.yaml"
    inventory_file.write_text(
        "devices:\n"
        "  - name: sw01\n"
        "    ip_address: 10.0.0.1\n"
    )
    mocker.patch("os.path.exists", return_value=False)
    session = InteractiveSession()
    session._load_inventory(str(inventory_file))
    sw01 = session.inventory.get_device("sw01")
    session.selected_devices = [sw01]

    mocker.patch.object(session, "_pick_devices_interactively", return_value=None)
    mock_connect = mocker.patch.object(session.connection_manager, "connect_device")

    session.do_connect("pick")

    assert session.selected_devices == [sw01]
    mock_connect.assert_not_called()
