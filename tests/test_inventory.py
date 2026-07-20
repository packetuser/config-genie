"""Tests for inventory module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from config_genie.inventory import Device, Inventory


def test_device_model():
    """Test Device model validation."""
    # Valid device
    device = Device(
        name="switch01",
        ip_address="192.168.1.1",
        model="2960X",
        site="HQ",
        role="access"
    )
    assert device.name == "switch01"
    assert device.ip_address == "192.168.1.1"
    
    # Invalid IP address
    with pytest.raises(ValueError):
        Device(name="switch01", ip_address="invalid-ip")


def test_inventory_yaml_loading():
    """Test loading devices from YAML file."""
    inventory_data = {
        'devices': [
            {
                'name': 'switch01',
                'ip_address': '192.168.1.1',
                'model': '2960X',
                'site': 'HQ',
                'role': 'access'
            },
            {
                'name': 'switch02',
                'ip_address': '192.168.1.2',
                'model': '9300',
                'site': 'Branch',
                'role': 'distribution'
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(inventory_data, f)
        yaml_file = f.name
    
    try:
        inventory = Inventory()
        inventory.load_yaml(yaml_file)
        
        assert len(inventory.devices) == 2
        assert 'switch01' in inventory.devices
        assert 'switch02' in inventory.devices
        
        device1 = inventory.get_device('switch01')
        assert device1.ip_address == '192.168.1.1'
        assert device1.model == '2960X'
    finally:
        Path(yaml_file).unlink()


def test_inventory_txt_loading():
    """Test loading devices from text file."""
    txt_content = """# This is a comment
192.168.1.1,switch01,2960X,HQ,access
192.168.1.2,switch02,9300,Branch,distribution
192.168.1.3
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(txt_content)
        txt_file = f.name
    
    try:
        inventory = Inventory()
        inventory.load_txt(txt_file)
        
        assert len(inventory.devices) == 3
        assert 'switch01' in inventory.devices
        assert '192.168.1.3' in inventory.devices
        
        device1 = inventory.get_device('switch01')
        assert device1.ip_address == '192.168.1.1'
        assert device1.model == '2960X'
        
        device3 = inventory.get_device('192.168.1.3')
        assert device3.ip_address == '192.168.1.3'
        assert device3.model is None
    finally:
        Path(txt_file).unlink()


def test_inventory_filtering():
    """Test device filtering."""
    inventory = Inventory()
    
    devices = [
        Device(name="sw01", ip_address="192.168.1.1", model="2960X", site="HQ", role="access"),
        Device(name="sw02", ip_address="192.168.1.2", model="9300", site="HQ", role="distribution"),
        Device(name="sw03", ip_address="192.168.1.3", model="2960X", site="Branch", role="access"),
    ]
    
    for device in devices:
        inventory.add_device(device)
    
    # Filter by model
    filtered = inventory.filter_devices(model="2960X")
    assert len(filtered) == 2
    assert all(d.model == "2960X" for d in filtered)
    
    # Filter by site
    filtered = inventory.filter_devices(site="HQ")
    assert len(filtered) == 2
    assert all(d.site == "HQ" for d in filtered)
    
    # Filter by name pattern
    filtered = inventory.filter_devices(name_pattern="sw0[13]")
    assert len(filtered) == 2
    assert "sw02" not in [d.name for d in filtered]


def test_inventory_unique_values():
    """Test getting unique values."""
    inventory = Inventory()
    
    devices = [
        Device(name="sw01", ip_address="192.168.1.1", model="2960X", site="HQ"),
        Device(name="sw02", ip_address="192.168.1.2", model="9300", site="HQ"),
        Device(name="sw03", ip_address="192.168.1.3", model="2960X", site="Branch"),
    ]
    
    for device in devices:
        inventory.add_device(device)
    
    models = inventory.get_unique_values('model')
    assert sorted(models) == ['2960X', '9300']
    
    sites = inventory.get_unique_values('site')
    assert sorted(sites) == ['Branch', 'HQ']


def test_inventory_duplicate_device():
    """Test duplicate device handling."""
    inventory = Inventory()
    
    device1 = Device(name="sw01", ip_address="192.168.1.1")
    device2 = Device(name="sw01", ip_address="192.168.1.2")
    
    inventory.add_device(device1)
    
    with pytest.raises(ValueError, match="already exists"):
        inventory.add_device(device2)

def test_inventory_netbox_missing_credentials():
    """Test that missing URL/token raises a clear error."""
    inventory = Inventory()

    with pytest.raises(ValueError, match="URL"):
        inventory.load_netbox(url=None, token="abc")

    with pytest.raises(ValueError, match="token"):
        inventory.load_netbox(url="https://netbox.example.com", token=None)


def test_inventory_netbox_loading(mocker):
    """Test loading devices from a mocked NetBox API response."""
    records = [
        {
            "name": "sw01",
            "primary_ip4": {"address": "10.0.0.1/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "access"},
        },
        {
            # Device without a primary IP should be skipped
            "name": "sw02",
            "primary_ip4": None,
        },
    ]

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = records
    mock_api_factory = mocker.patch(
        "config_genie.inventory.pynetbox.api", return_value=mock_api
    )

    inventory = Inventory()
    count = inventory.load_netbox(url="https://netbox.example.com", token="mytoken")

    assert count == 1
    device = inventory.get_device("sw01")
    assert device.ip_address == "10.0.0.1"
    assert device.model == "2960X"
    assert device.site == "HQ"
    assert device.role == "access"
    assert inventory.get_device("sw02") is None

    mock_api_factory.assert_called_once_with("https://netbox.example.com", token="mytoken")
    mock_api.dcim.devices.filter.assert_called_once_with(status="active")


def test_inventory_netbox_env_vars(mocker, monkeypatch):
    """Test that NETBOX_URL and NETBOX_TOKEN env vars are used as fallback."""
    monkeypatch.setenv("NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("NETBOX_TOKEN", "envtoken")

    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = []
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    inventory = Inventory()
    count = inventory.load_netbox()
    assert count == 0


def test_inventory_netbox_connection_error(mocker):
    """Test that connection errors are wrapped in a friendly message."""
    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.side_effect = ConnectionError("boom")
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    inventory = Inventory()
    with pytest.raises(ConnectionError, match="Failed to reach NetBox"):
        inventory.load_netbox(url="https://netbox.example.com", token="mytoken")


def test_inventory_netbox_verify_ssl_false(mocker):
    """Test that verify_ssl=False is applied to the pynetbox HTTP session."""
    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = []
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    inventory = Inventory()
    inventory.load_netbox(
        url="https://netbox.example.com", token="mytoken", verify_ssl=False
    )

    assert mock_api.http_session.verify is False


def test_parse_device_selection():
    """Test the shared selection-string parser used by CLI/interactive netbox import."""
    from config_genie.inventory import parse_device_selection

    candidates = [
        Device(name="sw01", ip_address="10.0.0.1"),
        Device(name="sw02", ip_address="10.0.0.2"),
        Device(name="300", ip_address="10.0.0.3"),
        Device(name="sw04", ip_address="10.0.0.4"),
        Device(name="sw05", ip_address="10.0.0.5"),
    ]

    assert parse_device_selection("all", candidates) == [0, 1, 2, 3, 4]
    assert parse_device_selection("", candidates) == [0, 1, 2, 3, 4]
    assert parse_device_selection("none", candidates) == []
    assert parse_device_selection("1,3", candidates) == [0, 2]
    assert parse_device_selection("2-4", candidates) == [1, 2, 3]
    assert parse_device_selection("1,3-4", candidates) == [0, 2, 3]

    # Selecting by device name, including a purely numeric name that isn't
    # a valid row number
    assert parse_device_selection("sw01", candidates) == [0]
    assert parse_device_selection("SW02", candidates) == [1]  # case-insensitive
    assert parse_device_selection("300", candidates) == [2]  # name, not row 300
    assert parse_device_selection("sw01,sw05", candidates) == [0, 4]

    with pytest.raises(ValueError):
        parse_device_selection("6", candidates)
    with pytest.raises(ValueError):
        parse_device_selection("0", candidates)
    with pytest.raises(ValueError):
        parse_device_selection("no-such-device", candidates)


def test_inventory_fetch_netbox_devices_role_contains(mocker):
    """Test client-side role_contains substring filtering."""
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

    inventory = Inventory()
    devices = inventory.fetch_netbox_devices(
        url="https://netbox.example.com", token="mytoken", role_contains="switch"
    )

    assert [d.name for d in devices] == ["sw01"]
    # fetch_netbox_devices should not mutate the inventory itself
    assert inventory.get_all_devices() == []


def test_inventory_load_netbox_commits_all_fetched(mocker):
    """load_netbox() should remain an all-or-nothing convenience wrapper."""
    mock_api = mocker.Mock()
    mock_api.dcim.devices.filter.return_value = [
        {
            "name": "sw01",
            "primary_ip4": {"address": "10.0.0.1/24"},
            "device_type": {"model": "2960X"},
            "site": {"name": "HQ"},
            "role": {"name": "access"},
        },
    ]
    mocker.patch("config_genie.inventory.pynetbox.api", return_value=mock_api)

    inventory = Inventory()
    count = inventory.load_netbox(url="https://netbox.example.com", token="mytoken")

    assert count == 1
    assert inventory.get_device("sw01") is not None


def test_get_device_by_ip_matches():
    inventory = Inventory()
    inventory.add_device(Device(name="sw01", ip_address="192.168.1.1"))
    inventory.add_device(Device(name="sw02", ip_address="192.168.1.2"))

    device = inventory.get_device_by_ip("192.168.1.2")
    assert device is not None
    assert device.name == "sw02"


def test_get_device_by_ip_no_match_returns_none():
    inventory = Inventory()
    inventory.add_device(Device(name="sw01", ip_address="192.168.1.1"))

    assert inventory.get_device_by_ip("10.0.0.99") is None


def test_is_ip_address():
    from config_genie.inventory import is_ip_address

    assert is_ip_address("192.168.1.1") is True
    assert is_ip_address("255.255.255.255") is True
    assert is_ip_address("sw01") is False
    assert is_ip_address("switch1.example.com") is False
    assert is_ip_address("256.1.1.1") is False
