"""Tests for validation module."""

import pytest

from config_genie.validation import CiscoCommandValidator, ValidationResult, SafetyChecker
from config_genie.inventory import Device


class TestCiscoCommandValidator:
    """Test command validation functionality."""
    
    def test_validate_commands_empty(self):
        """Test validation with empty commands."""
        validator = CiscoCommandValidator()
        result = validator.validate_commands([])
        
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "No commands provided" in result.errors[0]
    
    def test_validate_basic_commands(self):
        """Test validation of basic valid commands."""
        validator = CiscoCommandValidator()
        commands = [
            "interface GigabitEthernet0/1",
            "description User Port", 
            "switchport mode access",
            "switchport access vlan 10",
            "no shutdown"
        ]
        
        result = validator.validate_commands(commands)
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_validate_risky_commands(self):
        """Test validation detects risky commands."""
        validator = CiscoCommandValidator()
        risky_commands = [
            "reload",
            "shutdown",
            "erase startup-config",
            "no vlan 10"
        ]
        
        result = validator.validate_commands(risky_commands)
        assert result.is_valid  # No syntax errors
        assert len(result.warnings) >= 4  # But should have warnings for risky commands
        
        # Check specific risky command warnings
        warning_text = " ".join(result.warnings)
        assert "reload" in warning_text.lower()
        assert "shutdown" in warning_text.lower()
        assert "erase" in warning_text.lower()
    
    def test_validate_syntax_errors(self):
        """Test validation catches syntax errors."""
        validator = CiscoCommandValidator()
        commands = [
            "interface GigabitEthernet0/1,",  # Trailing comma
            " switchport mode access",        # Leading space
            ""                               # Empty command
        ]
        
        result = validator.validate_commands(commands)
        assert not result.is_valid  # Should have errors
        assert len(result.errors) >= 1
        assert len(result.warnings) >= 1
    
    def test_validate_exec_commands_in_config(self):
        """Test detection of exec commands in config context."""
        validator = CiscoCommandValidator()
        commands = [
            "interface GigabitEthernet0/1",
            "show interfaces",  # Exec command in config context
            "switchport mode access"
        ]
        
        result = validator.validate_commands(commands)
        assert result.is_valid  # Not a fatal error
        assert len(result.warnings) >= 1
        assert "exec command" in " ".join(result.warnings).lower()
    
    def test_validate_device_compatibility(self):
        """Test device-specific validation."""
        validator = CiscoCommandValidator()
        
        # Test stack commands on non-stackable switch
        commands = ["switch 1 priority 15"]
        device = Device("sw01", "192.168.1.1", model="2960")  # Non-stackable
        
        result = validator.validate_commands(commands, device)
        assert len(result.warnings) >= 1
        assert "stack" in " ".join(result.warnings).lower()
        
        # Test advanced QoS on basic switch
        qos_commands = ["class-map match-all VOICE", "match ip dscp ef"]
        result = validator.validate_commands(qos_commands, device)
        assert len(result.warnings) >= 1
    
    def test_validate_against_running_config(self):
        """Test validation against running configuration."""
        validator = CiscoCommandValidator()
        
        commands = [
            "interface GigabitEthernet0/1",
            "switchport access vlan 20"
        ]
        
        running_config = """
        interface GigabitEthernet0/1
        switchport mode access
        switchport access vlan 10
        no shutdown
        !
        vlan 10
        name DATA_VLAN
        """
        
        result = validator.validate_against_running_config(commands, running_config)
        
        # Should detect that we're modifying existing interface
        assert len(result.info) >= 1
        info_text = " ".join(result.info)
        assert "existing interface" in info_text.lower()
    
    def test_validate_conflicts(self):
        """Test conflict detection within command set."""
        validator = CiscoCommandValidator()
        
        # Duplicate interface configuration
        commands = [
            "interface GigabitEthernet0/1",
            "switchport mode access",
            "interface GigabitEthernet0/1",  # Duplicate
            "switchport mode trunk"
        ]
        
        result = validator.validate_commands(commands)
        assert len(result.conflicts) >= 1
        conflict_text = " ".join(result.conflicts)
        assert "multiple times" in conflict_text.lower()
    
    def test_validate_best_practices(self):
        """Test best practice recommendations."""
        validator = CiscoCommandValidator()
        
        # Configuration changes without save
        commands = [
            "interface GigabitEthernet0/1",
            "switchport access vlan 10",
            "no shutdown"
        ]
        
        result = validator.validate_commands(commands)
        assert len(result.info) >= 1
        info_text = " ".join(result.info)
        assert "save" in info_text.lower() or "copy running-config" in info_text.lower()
        
        # Bulk interface changes
        bulk_commands = [f"interface GigabitEthernet0/{i}" for i in range(1, 15)]
        result = validator.validate_commands(bulk_commands)
        assert len(result.warnings) >= 1
        warning_text = " ".join(result.warnings)
        assert "interfaces" in warning_text.lower()


class TestSafetyChecker:
    """Test safety checker functionality."""
    
    def test_multi_device_safety_check(self):
        """Test safety checks for multi-device operations."""
        safety_checker = SafetyChecker()
        
        devices = [Device(f"sw{i:02d}", f"192.168.1.{i}") for i in range(1, 11)]
        commands = ["interface GigabitEthernet0/1", "no shutdown"]
        
        results = safety_checker.check_multi_device_operation(commands, devices)
        
        assert len(results) == 10
        for device_name, result in results.items():
            assert isinstance(result, ValidationResult)
    
    def test_rollback_feasibility(self):
        """Test rollback feasibility checking."""
        safety_checker = SafetyChecker()
        
        # Easy to rollback commands
        safe_commands = [
            "interface GigabitEthernet0/1",
            "description Test Port",
            "no shutdown"
        ]
        
        result = safety_checker.check_rollback_feasibility(safe_commands)
        assert len(result.info) >= 1
        assert "safely rollbackable" in " ".join(result.info).lower()
        
        # Hard to rollback commands
        risky_commands = [
            "erase startup-config",
            "reload",
            "no vlan 10"
        ]
        
        result = safety_checker.check_rollback_feasibility(risky_commands)
        assert len(result.warnings) >= 1
        assert "difficult to rollback" in " ".join(result.warnings).lower()