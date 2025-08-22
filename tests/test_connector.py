"""Tests for connector module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from config_genie.inventory import Device
from config_genie.connector import CiscoSSHConnector, ConnectionManager


class TestCiscoSSHConnector:
    """Test SSH connector functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device = Device(
            name="test-switch",
            ip_address="192.168.1.1",
            model="2960X"
        )
    
    @patch('config_genie.connector.paramiko.SSHClient')
    def test_connection_success(self, mock_ssh_client):
        """Test successful SSH connection."""
        # Mock SSH client and shell
        mock_client = Mock()
        mock_shell = Mock()
        mock_ssh_client.return_value = mock_client
        mock_client.invoke_shell.return_value = mock_shell
        mock_shell.recv_ready.return_value = False
        
        connector = CiscoSSHConnector(
            device=self.device,
            username="admin",
            password="password"
        )
        
        result = connector.connect()
        
        assert result is True
        assert connector.connected is True
        mock_client.connect.assert_called_once()
        mock_client.invoke_shell.assert_called_once()
    
    @patch('config_genie.connector.paramiko.SSHClient')
    def test_connection_failure(self, mock_ssh_client):
        """Test SSH connection failure."""
        mock_client = Mock()
        mock_ssh_client.return_value = mock_client
        mock_client.connect.side_effect = Exception("Connection failed")
        
        connector = CiscoSSHConnector(
            device=self.device,
            username="admin",
            password="password"
        )
        
        with pytest.raises(ConnectionError, match="Failed to connect"):
            connector.connect()
        
        assert connector.connected is False
    
    def test_send_command_not_connected(self):
        """Test sending command when not connected."""
        connector = CiscoSSHConnector(
            device=self.device,
            username="admin",
            password="password"
        )
        
        with pytest.raises(ConnectionError, match="Not connected"):
            connector.send_command("show version")
    
    @patch('config_genie.connector.paramiko.SSHClient')
    def test_clean_output(self, mock_ssh_client):
        """Test output cleaning functionality."""
        connector = CiscoSSHConnector(
            device=self.device,
            username="admin",
            password="password"
        )
        
        # Test removing ANSI escape sequences
        dirty_output = "show version\r\n\x1b[32mCisco IOS\x1b[0m\r\nSwitch#"
        clean_output = connector._clean_output(dirty_output)
        
        assert "\x1b" not in clean_output
        assert "\r" not in clean_output
        assert "Switch#" not in clean_output
        assert "Cisco IOS" in clean_output
    
    def test_has_config_error(self):
        """Test configuration error detection."""
        connector = CiscoSSHConnector(
            device=self.device,
            username="admin",
            password="password"
        )
        
        # Test valid output
        valid_output = "interface GigabitEthernet0/1\nswitchport mode access"
        assert not connector._has_config_error(valid_output)
        
        # Test error output
        error_output = "% Invalid input detected at '^' marker."
        assert connector._has_config_error(error_output)


class TestConnectionManager:
    """Test connection manager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.device = Device(
            name="test-switch",
            ip_address="192.168.1.1",
            model="2960X"
        )
        self.manager = ConnectionManager()
    
    def test_set_credentials(self):
        """Test setting credentials."""
        self.manager.set_credentials("admin", "password", "enable_pass")
        
        assert self.manager.credentials == ("admin", "password", "enable_pass")
    
    def test_connect_without_credentials(self):
        """Test connecting without setting credentials first."""
        with pytest.raises(ValueError, match="Credentials must be set"):
            self.manager.connect_device(self.device)
    
    @patch('config_genie.connector.CiscoSSHConnector')
    def test_connect_device_success(self, mock_connector_class):
        """Test successful device connection."""
        # Setup mock connector
        mock_connector = Mock()
        mock_connector_class.return_value = mock_connector
        mock_connector.connect.return_value = True
        
        # Set credentials and connect
        self.manager.set_credentials("admin", "password")
        result = self.manager.connect_device(self.device)
        
        assert result == mock_connector
        assert self.device.name in self.manager.connections
        mock_connector.connect.assert_called_once()
    
    @patch('config_genie.connector.CiscoSSHConnector')
    def test_connect_device_with_enable(self, mock_connector_class):
        """Test device connection with enable password."""
        mock_connector = Mock()
        mock_connector_class.return_value = mock_connector
        mock_connector.connect.return_value = True
        
        self.manager.set_credentials("admin", "password", "enable_pass")
        self.manager.connect_device(self.device)
        
        mock_connector.enter_enable_mode.assert_called_once()
    
    @patch('config_genie.connector.CiscoSSHConnector')
    @patch('config_genie.connector.time.sleep')
    def test_connect_device_retry(self, mock_sleep, mock_connector_class):
        """Test device connection with retry logic."""
        mock_connector = Mock()
        mock_connector_class.return_value = mock_connector
        # Fail twice, succeed on third attempt
        mock_connector.connect.side_effect = [
            Exception("Connection failed"),
            Exception("Connection failed"),
            True
        ]
        
        self.manager.set_credentials("admin", "password")
        result = self.manager.connect_device(self.device, retry_count=3)
        
        assert result == mock_connector
        assert mock_connector.connect.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep between retries
    
    def test_disconnect_device(self):
        """Test disconnecting from specific device."""
        # Add a mock connection
        mock_connector = Mock()
        self.manager.connections[self.device.name] = mock_connector
        
        self.manager.disconnect_device(self.device.name)
        
        assert self.device.name not in self.manager.connections
        mock_connector.disconnect.assert_called_once()
    
    def test_disconnect_all(self):
        """Test disconnecting from all devices."""
        # Add mock connections
        mock_connector1 = Mock()
        mock_connector2 = Mock()
        self.manager.connections["device1"] = mock_connector1
        self.manager.connections["device2"] = mock_connector2
        
        self.manager.disconnect_all()
        
        assert len(self.manager.connections) == 0
        mock_connector1.disconnect.assert_called_once()
        mock_connector2.disconnect.assert_called_once()
    
    def test_get_connection(self):
        """Test getting connection for device."""
        mock_connector = Mock()
        self.manager.connections[self.device.name] = mock_connector
        
        result = self.manager.get_connection(self.device.name)
        assert result == mock_connector
        
        # Test non-existent connection
        result = self.manager.get_connection("non-existent")
        assert result is None