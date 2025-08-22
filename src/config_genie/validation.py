"""Configuration validation and safety checks module."""

import re
from typing import List, Dict, Set, Tuple, Optional, Any

from .inventory import Device


class ValidationResult:
    """Result of configuration validation."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.conflicts: List[str] = []
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return len(self.warnings) > 0
    
    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
    
    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)
    
    def add_info(self, message: str) -> None:
        """Add an info message."""
        self.info.append(message)
    
    def add_conflict(self, message: str) -> None:
        """Add a conflict message."""
        self.conflicts.append(message)


class CiscoCommandValidator:
    """Validator for Cisco IOS/IOS-XE configuration commands."""
    
    def __init__(self):
        # Risky commands that require extra confirmation
        self.risky_commands = {
            r'^reload\s*$': 'Device reload - will cause downtime',
            r'^shutdown\s*$': 'Interface shutdown',
            r'^no\s+ip\s+route': 'Removing IP routes',
            r'^no\s+vlan': 'Removing VLAN configuration',
            r'^erase\s+startup-config': 'Erasing startup configuration',
            r'^write\s+erase': 'Erasing startup configuration',
            r'^format\s+': 'Formatting storage device',
            r'^delete\s+': 'Deleting files',
            r'^rmdir\s+': 'Removing directories',
        }
        
        # Commands that should not be in config mode
        self.exec_only_commands = {
            'show', 'ping', 'traceroute', 'telnet', 'ssh', 'copy', 'reload',
            'write', 'erase', 'delete', 'format', 'archive', 'clear'
        }
        
        # Common configuration contexts
        self.config_contexts = {
            'interface': r'^interface\s+',
            'router': r'^router\s+',
            'line': r'^line\s+',
            'vlan': r'^vlan\s+',
            'class-map': r'^class-map\s+',
            'policy-map': r'^policy-map\s+',
        }
    
    def validate_commands(self, commands: List[str], device: Optional[Device] = None) -> ValidationResult:
        """Validate a list of configuration commands."""
        result = ValidationResult()
        
        if not commands:
            result.add_error("No commands provided for validation")
            return result
        
        # Parse commands and check for issues
        self._check_command_syntax(commands, result)
        self._check_risky_commands(commands, result)
        self._check_conflicts(commands, result)
        self._check_best_practices(commands, result)
        
        # Device-specific validation
        if device:
            self._check_device_compatibility(commands, device, result)
        
        return result
    
    def validate_against_running_config(
        self, 
        commands: List[str], 
        running_config: str,
        device: Optional[Device] = None
    ) -> ValidationResult:
        """Validate commands against current running configuration."""
        result = self.validate_commands(commands, device)
        
        # Parse running config for conflict detection
        config_lines = [line.strip() for line in running_config.split('\n') if line.strip()]
        
        self._check_config_conflicts(commands, config_lines, result)
        self._check_duplicate_configurations(commands, config_lines, result)
        
        return result
    
    def _check_command_syntax(self, commands: List[str], result: ValidationResult) -> None:
        """Check basic command syntax."""
        for i, command in enumerate(commands):
            command = command.strip()
            if not command:
                continue
            
            # Skip comments
            if command.startswith('!'):
                continue
            
            # Check for common syntax errors
            if command.startswith(' '):
                result.add_warning(f"Line {i+1}: Command starts with space: '{command}'")
            
            # Check for incomplete commands
            if command.endswith(','):
                result.add_error(f"Line {i+1}: Incomplete command: '{command}'")
            
            # Check for exec commands in config context
            first_word = command.split()[0].lower()
            if first_word in self.exec_only_commands:
                result.add_warning(f"Line {i+1}: '{first_word}' is typically an exec command, not config")
    
    def _check_risky_commands(self, commands: List[str], result: ValidationResult) -> None:
        """Check for risky commands that need confirmation."""
        for i, command in enumerate(commands):
            command = command.strip().lower()
            
            for pattern, description in self.risky_commands.items():
                if re.search(pattern, command, re.IGNORECASE):
                    result.add_warning(f"Line {i+1}: RISKY - {description}: '{command}'")
    
    def _check_conflicts(self, commands: List[str], result: ValidationResult) -> None:
        """Check for conflicts within the command set."""
        interfaces = {}
        vlans = {}
        
        for i, command in enumerate(commands):
            command = command.strip()
            
            # Track interface configurations
            interface_match = re.search(r'^interface\s+(\S+)', command, re.IGNORECASE)
            if interface_match:
                interface = interface_match.group(1).lower()
                if interface in interfaces:
                    result.add_conflict(f"Interface {interface} configured multiple times")
                interfaces[interface] = i + 1
            
            # Track VLAN configurations
            vlan_match = re.search(r'^vlan\s+(\d+)', command, re.IGNORECASE)
            if vlan_match:
                vlan_id = vlan_match.group(1)
                if vlan_id in vlans:
                    result.add_conflict(f"VLAN {vlan_id} configured multiple times")
                vlans[vlan_id] = i + 1
            
            # Check for conflicting switchport commands
            if 'switchport mode' in command.lower():
                # Look for other switchport mode commands for same interface
                current_interface = self._get_current_interface_context(commands, i)
                if current_interface:
                    for j, other_cmd in enumerate(commands):
                        if (j != i and 'switchport mode' in other_cmd.lower() and 
                            self._get_current_interface_context(commands, j) == current_interface):
                            result.add_conflict(f"Multiple switchport modes for {current_interface}")
    
    def _check_best_practices(self, commands: List[str], result: ValidationResult) -> None:
        """Check against Cisco best practices."""
        has_save = False
        interface_count = 0
        
        for command in commands:
            command = command.strip().lower()
            
            # Check for save command
            if 'copy running-config startup-config' in command or 'write memory' in command:
                has_save = True
            
            # Count interface configurations
            if command.startswith('interface '):
                interface_count += 1
        
        # Recommend saving if making changes
        config_changes = any(not cmd.strip().startswith(('show', '!', '')) 
                           for cmd in commands if cmd.strip())
        
        if config_changes and not has_save:
            result.add_info("Consider adding 'copy running-config startup-config' to save changes")
        
        # Warn about bulk interface changes
        if interface_count > 10:
            result.add_warning(f"Configuring {interface_count} interfaces - verify this is intentional")
    
    def _check_device_compatibility(self, commands: List[str], device: Device, result: ValidationResult) -> None:
        """Check command compatibility with device model."""
        if not device.model:
            return
        
        model = device.model.lower()
        
        # Model-specific command checks
        for command in commands:
            command_lower = command.lower()
            
            # Check for commands not supported on certain models
            if 'stack' in command_lower and model.startswith('2960'):
                if not model.endswith('x') and not model.endswith('xr'):
                    result.add_warning(f"Stack commands may not be supported on {device.model}")
            
            # Check for advanced features on basic switches
            if any(feature in command_lower for feature in ['qos', 'class-map', 'policy-map']):
                if model.startswith('2960') and not model.endswith(('x', 'xr')):
                    result.add_warning(f"Advanced QoS features may be limited on {device.model}")
    
    def _check_config_conflicts(self, commands: List[str], running_config: List[str], result: ValidationResult) -> None:
        """Check for conflicts with running configuration."""
        running_interfaces = set()
        running_vlans = set()
        
        # Parse running config for existing configurations
        for line in running_config:
            interface_match = re.search(r'^interface\s+(\S+)', line, re.IGNORECASE)
            if interface_match:
                running_interfaces.add(interface_match.group(1).lower())
            
            vlan_match = re.search(r'^vlan\s+(\d+)', line, re.IGNORECASE)
            if vlan_match:
                running_vlans.add(vlan_match.group(1))
        
        # Check if we're modifying existing configurations
        for command in commands:
            interface_match = re.search(r'^interface\s+(\S+)', command, re.IGNORECASE)
            if interface_match:
                interface = interface_match.group(1).lower()
                if interface in running_interfaces:
                    result.add_info(f"Modifying existing interface: {interface}")
            
            vlan_match = re.search(r'^vlan\s+(\d+)', command, re.IGNORECASE)
            if vlan_match:
                vlan_id = vlan_match.group(1)
                if vlan_id in running_vlans:
                    result.add_info(f"Modifying existing VLAN: {vlan_id}")
    
    def _check_duplicate_configurations(self, commands: List[str], running_config: List[str], result: ValidationResult) -> None:
        """Check for duplicate configurations already in running config."""
        running_set = set(line.strip().lower() for line in running_config)
        
        for i, command in enumerate(commands):
            command_clean = command.strip().lower()
            if command_clean and not command_clean.startswith('!'):
                if command_clean in running_set:
                    result.add_warning(f"Line {i+1}: Command may already exist in running config: '{command.strip()}'")
    
    def _get_current_interface_context(self, commands: List[str], current_index: int) -> Optional[str]:
        """Get the interface context for a command at given index."""
        # Look backwards for the most recent interface command
        for i in range(current_index, -1, -1):
            interface_match = re.search(r'^interface\s+(\S+)', commands[i], re.IGNORECASE)
            if interface_match:
                return interface_match.group(1).lower()
        return None


class SafetyChecker:
    """Additional safety checks for network operations."""
    
    def __init__(self):
        self.validator = CiscoCommandValidator()
    
    def check_multi_device_operation(
        self, 
        commands: List[str], 
        devices: List[Device],
        running_configs: Optional[Dict[str, str]] = None
    ) -> Dict[str, ValidationResult]:
        """Check safety of applying commands to multiple devices."""
        results = {}
        
        for device in devices:
            running_config = running_configs.get(device.name) if running_configs else None
            
            if running_config:
                result = self.validator.validate_against_running_config(commands, running_config, device)
            else:
                result = self.validator.validate_commands(commands, device)
            
            results[device.name] = result
        
        return results
    
    def check_rollback_feasibility(self, commands: List[str]) -> ValidationResult:
        """Check if commands can be easily rolled back."""
        result = ValidationResult()
        
        rollback_risky = []
        
        for command in commands:
            command = command.strip().lower()
            
            # Commands that are hard to rollback
            if any(pattern in command for pattern in [
                'erase', 'delete', 'format', 'reload',
                'write erase', 'no vlan', 'shutdown'
            ]):
                rollback_risky.append(command)
        
        if rollback_risky:
            result.add_warning(f"Commands may be difficult to rollback: {rollback_risky}")
        else:
            result.add_info("Commands appear to be safely rollbackable")
        
        return result