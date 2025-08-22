"""Tests for logging and session history functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from config_genie.logging import SessionLogger
from config_genie.inventory import Device


class TestSessionLogger:
    """Test SessionLogger functionality."""
    
    def test_logger_initialization(self):
        """Test logger initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            
            assert logger.log_dir == Path(temp_dir)
            assert logger.current_session_id.startswith('session-')
            assert len(logger.session_history) >= 0
            
            logger.close()
    
    def test_log_connection_attempt(self):
        """Test logging connection attempts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            
            # Test successful connection
            logger.log_connection_attempt(device, True)
            
            # Test failed connection
            logger.log_connection_attempt(device, False, "Connection timeout")
            
            # Check history
            history = logger.get_session_history(event_type='connection')
            assert len(history) == 2
            
            success_event = history[0]
            assert success_event['device_name'] == 'test-device'
            assert success_event['success'] is True
            
            failure_event = history[1]
            assert failure_event['success'] is False
            assert failure_event['error'] == 'Connection timeout'
            
            logger.close()
    
    def test_log_command_execution(self):
        """Test logging command execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            commands = ["show version", "show interfaces"]
            
            logger.log_command_execution(
                device=device,
                commands=commands,
                success=True,
                output="Command output here",
                execution_time=1.5,
                dry_run=False
            )
            
            history = logger.get_session_history(event_type='command_execution')
            assert len(history) == 1
            
            event = history[0]
            assert event['device_name'] == 'test-device'
            assert event['commands'] == commands
            assert event['success'] is True
            assert event['execution_time'] == 1.5
            assert event['dry_run'] is False
            
            logger.close()
    
    def test_log_template_usage(self):
        """Test logging template usage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            devices = [Device("sw1", "192.168.1.1"), Device("sw2", "192.168.1.2")]
            variables = {"interface": "GigabitEthernet0/1", "vlan": "10"}
            
            logger.log_template_usage(
                template_name="basic_interface_config",
                devices=devices,
                variables=variables,
                success=True
            )
            
            history = logger.get_session_history(event_type='template_usage')
            assert len(history) == 1
            
            event = history[0]
            assert event['template_name'] == 'basic_interface_config'
            assert event['devices'] == ['sw1', 'sw2']
            assert event['variables'] == variables
            assert event['success'] is True
            
            logger.close()
    
    def test_log_validation_result(self):
        """Test logging validation results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            commands = ["interface GigabitEthernet0/1", "no shutdown"]
            
            logger.log_validation_result(
                device=device,
                commands=commands,
                validation_errors=0,
                validation_warnings=1,
                validation_details="One warning found"
            )
            
            history = logger.get_session_history(event_type='validation')
            assert len(history) == 1
            
            event = history[0]
            assert event['device_name'] == 'test-device'
            assert event['commands_count'] == 2
            assert event['validation_errors'] == 0
            assert event['validation_warnings'] == 1
            
            logger.close()
    
    def test_log_rollback(self):
        """Test logging rollback operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            devices = [Device("sw1", "192.168.1.1")]
            rollback_commands = ["no interface GigabitEthernet0/1"]
            
            logger.log_rollback(
                devices=devices,
                rollback_commands=rollback_commands,
                success=True
            )
            
            history = logger.get_session_history(event_type='rollback')
            assert len(history) == 1
            
            event = history[0]
            assert event['devices'] == ['sw1']
            assert event['rollback_commands'] == rollback_commands
            assert event['success'] is True
            
            logger.close()
    
    def test_session_history_filtering(self):
        """Test session history filtering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device1 = Device("device1", "192.168.1.1")
            device2 = Device("device2", "192.168.1.2")
            
            # Log different types of events
            logger.log_connection_attempt(device1, True)
            logger.log_connection_attempt(device2, True)
            logger.log_command_execution(device1, ["show version"], True)
            
            # Test filtering by event type
            connections = logger.get_session_history(event_type='connection')
            assert len(connections) == 2
            
            commands = logger.get_session_history(event_type='command_execution')
            assert len(commands) == 1
            
            # Test filtering by device name
            device1_events = logger.get_session_history(device_name='device1')
            assert len(device1_events) == 2
            
            device2_events = logger.get_session_history(device_name='device2')
            assert len(device2_events) == 1
            
            # Test limit
            limited = logger.get_session_history(limit=2)
            assert len(limited) == 2
            
            logger.close()
    
    def test_session_statistics(self):
        """Test session statistics calculation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            
            # Add some events
            logger.log_connection_attempt(device, True)
            logger.log_command_execution(device, ["show version", "show interfaces"], True)
            logger.log_command_execution(device, ["configure terminal"], False, error="Failed")
            
            stats = logger.get_session_statistics()
            
            assert stats['total_events'] == 3
            assert 'connection' in stats['event_types']
            assert 'command_execution' in stats['event_types']
            assert stats['event_types']['command_execution'] == 2
            assert 'test-device' in stats['devices']
            assert stats['successful_operations'] == 2
            assert stats['failed_operations'] == 1
            assert stats['commands_executed'] == 3  # 2 + 1
            
            logger.close()
    
    def test_history_persistence(self):
        """Test that history is saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create logger and add some history
            logger1 = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            logger1.log_connection_attempt(device, True)
            logger1.close()
            
            # Create new logger instance and check if history is loaded
            logger2 = SessionLogger(log_dir=temp_dir)
            history = logger2.get_session_history()
            
            # Should have at least the connection event from logger1
            connection_events = [h for h in history if h.get('event_type') == 'connection']
            assert len(connection_events) >= 1
            
            logger2.close()
    
    def test_export_history(self):
        """Test history export functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            
            logger.log_connection_attempt(device, True)
            
            # Export history
            export_file = Path(temp_dir) / "exported_history.json"
            logger.export_history(str(export_file))
            
            # Verify export file
            assert export_file.exists()
            
            with open(export_file) as f:
                exported_data = json.load(f)
            
            assert len(exported_data) >= 1
            assert exported_data[0]['event_type'] == 'connection'
            
            logger.close()
    
    def test_clear_history(self):
        """Test history clearing functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(log_dir=temp_dir)
            device = Device("test-device", "192.168.1.1")
            
            # Add some history
            logger.log_connection_attempt(device, True)
            logger.log_connection_attempt(device, False)
            
            initial_count = len(logger.get_session_history())
            assert initial_count >= 2
            
            # Clear all history
            cleared_count = logger.clear_history()
            assert cleared_count == initial_count
            assert len(logger.get_session_history()) == 0
            
            logger.close()