"""Safety checks and confirmation prompts for network operations."""

import re
from typing import Dict, List, Optional, Set, Tuple, Any

try:
    from rich.console import Console
    from rich.prompt import Confirm, Prompt
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    Console = None
    Confirm = None

from .inventory import Device
from .validation import ValidationResult, CiscoCommandValidator


class SafetyLevel:
    """Safety levels for operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyCheck:
    """Individual safety check result."""
    
    def __init__(
        self,
        check_type: str,
        level: str,
        message: str,
        recommendation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.check_type = check_type
        self.level = level
        self.message = message
        self.recommendation = recommendation
        self.details = details or {}
    
    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.check_type}: {self.message}"


class SafetyManager:
    """Manages safety checks and confirmation prompts."""
    
    def __init__(self, console: Optional['Console'] = None, auto_confirm: bool = False):
        self.console = console or (Console() if Console else None)
        self.auto_confirm = auto_confirm
        self.validator = CiscoCommandValidator()
        
        # Define risky command patterns and their safety levels
        self.risky_patterns = {
            # Critical - Can cause outages
            r'^reload\s*$': (SafetyLevel.CRITICAL, "Device reload will cause downtime"),
            r'^shutdown\s*$': (SafetyLevel.CRITICAL, "Interface shutdown will disconnect users"),
            r'^erase\s+startup-config': (SafetyLevel.CRITICAL, "Erasing startup config is irreversible"),
            r'^write\s+erase': (SafetyLevel.CRITICAL, "Write erase removes all configuration"),
            r'^format\s+': (SafetyLevel.CRITICAL, "Formatting storage will destroy data"),
            r'^delete\s+flash:': (SafetyLevel.CRITICAL, "Deleting files from flash"),
            
            # High - Can cause significant issues
            r'^no\s+vlan\s+\d+': (SafetyLevel.HIGH, "Removing VLAN configuration"),
            r'^no\s+ip\s+route': (SafetyLevel.HIGH, "Removing IP routes"),
            r'^no\s+spanning-tree': (SafetyLevel.HIGH, "Disabling spanning-tree"),
            r'^spanning-tree\s+portfast\s+bpduguard\s+default': (SafetyLevel.HIGH, "Enabling BPDU guard globally"),
            
            # Medium - Should be reviewed
            r'^vtp\s+mode\s+server': (SafetyLevel.MEDIUM, "Changing VTP mode to server"),
            r'^ip\s+routing': (SafetyLevel.MEDIUM, "Enabling IP routing"),
            r'^no\s+switchport': (SafetyLevel.MEDIUM, "Converting switchport to routed port"),
            
            # Low - Minor risk
            r'^logging\s+': (SafetyLevel.LOW, "Modifying logging configuration"),
            r'^snmp-server\s+': (SafetyLevel.LOW, "Modifying SNMP configuration"),
        }
    
    def perform_safety_checks(
        self,
        commands: List[str],
        devices: List[Device],
        context: Optional[Dict[str, Any]] = None
    ) -> List[SafetyCheck]:
        """Perform comprehensive safety checks on commands and devices."""
        checks = []
        
        # Check individual commands
        for command in commands:
            checks.extend(self._check_command_safety(command))
        
        # Check multi-device operation safety
        if len(devices) > 1:
            checks.extend(self._check_multi_device_safety(commands, devices))
        
        # Check device-specific safety
        for device in devices:
            checks.extend(self._check_device_specific_safety(commands, device))
        
        # Check bulk operations
        checks.extend(self._check_bulk_operation_safety(commands, devices))
        
        # Check time-based safety (business hours, etc.)
        if context:
            checks.extend(self._check_time_based_safety(commands, context))
        
        return checks
    
    def _check_command_safety(self, command: str) -> List[SafetyCheck]:
        """Check safety of individual command."""
        checks = []
        command_lower = command.strip().lower()
        
        # Check against risky patterns
        for pattern, (level, message) in self.risky_patterns.items():
            if re.search(pattern, command_lower):
                checks.append(SafetyCheck(
                    check_type="risky_command",
                    level=level,
                    message=f"{message}: '{command.strip()}'",
                    recommendation=self._get_command_recommendation(command, level)
                ))
        
        # Check for password/secret commands
        if any(keyword in command_lower for keyword in ['password', 'secret', 'key']):
            if not any(hashed in command_lower for hashed in ['$1$', '$5$', '$8$', '$9$']):
                checks.append(SafetyCheck(
                    check_type="plaintext_credential",
                    level=SafetyLevel.HIGH,
                    message=f"Plaintext credential detected: '{command.strip()}'",
                    recommendation="Use encrypted passwords or service password-encryption"
                ))
        
        # Check for management interface modifications
        if re.search(r'interface.*(management|mgmt|vlan\s*1)\b', command_lower):
            checks.append(SafetyCheck(
                check_type="management_interface",
                level=SafetyLevel.HIGH,
                message=f"Modifying management interface: '{command.strip()}'",
                recommendation="Ensure management connectivity is maintained"
            ))
        
        return checks
    
    def _check_multi_device_safety(self, commands: List[str], devices: List[Device]) -> List[SafetyCheck]:
        """Check safety of operations across multiple devices."""
        checks = []
        
        device_count = len(devices)
        config_commands = [cmd for cmd in commands if not cmd.strip().lower().startswith(('show', '!', ''))]
        
        # Warn about bulk configuration changes
        if device_count >= 10 and config_commands:
            checks.append(SafetyCheck(
                check_type="bulk_configuration",
                level=SafetyLevel.HIGH,
                message=f"Applying configuration changes to {device_count} devices simultaneously",
                recommendation="Consider testing on a subset first or using staged deployment"
            ))
        elif device_count >= 5 and config_commands:
            checks.append(SafetyCheck(
                check_type="multi_device_config",
                level=SafetyLevel.MEDIUM,
                message=f"Applying configuration changes to {device_count} devices",
                recommendation="Verify changes on each device type before proceeding"
            ))
        
        # Check for mixed device models
        models = set(device.model for device in devices if device.model)
        if len(models) > 1:
            checks.append(SafetyCheck(
                check_type="mixed_device_models",
                level=SafetyLevel.MEDIUM,
                message=f"Operating on mixed device models: {', '.join(models)}",
                recommendation="Verify command compatibility across all device models",
                details={"models": list(models), "device_count": device_count}
            ))
        
        return checks
    
    def _check_device_specific_safety(self, commands: List[str], device: Device) -> List[SafetyCheck]:
        """Check device-specific safety concerns."""
        checks = []
        
        if not device.model:
            return checks
        
        model = device.model.lower()
        
        # Check for stack-related commands on non-stackable switches
        stack_commands = [cmd for cmd in commands if 'stack' in cmd.lower()]
        if stack_commands and model.startswith('2960') and not model.endswith(('x', 'xr')):
            checks.append(SafetyCheck(
                check_type="unsupported_feature",
                level=SafetyLevel.MEDIUM,
                message=f"Stack commands may not be supported on {device.model}",
                recommendation="Verify feature support for your device model"
            ))
        
        # Check for advanced QoS on basic switches
        qos_commands = [cmd for cmd in commands if any(qos_term in cmd.lower() 
                       for qos_term in ['class-map', 'policy-map', 'service-policy'])]
        if qos_commands and model.startswith('2960') and not model.endswith(('x', 'xr')):
            checks.append(SafetyCheck(
                check_type="feature_limitation",
                level=SafetyLevel.LOW,
                message=f"Advanced QoS features may be limited on {device.model}",
                recommendation="Check device capabilities and consider basic QoS alternatives"
            ))
        
        return checks
    
    def _check_bulk_operation_safety(self, commands: List[str], devices: List[Device]) -> List[SafetyCheck]:
        """Check safety of bulk operations."""
        checks = []
        
        # Count interface configurations
        interface_commands = len([cmd for cmd in commands if cmd.strip().lower().startswith('interface ')])
        if interface_commands > 20:
            checks.append(SafetyCheck(
                check_type="bulk_interface_config",
                level=SafetyLevel.MEDIUM,
                message=f"Configuring {interface_commands} interfaces",
                recommendation="Verify interface names and configurations are correct"
            ))
        
        # Count VLAN operations
        vlan_commands = len([cmd for cmd in commands if cmd.strip().lower().startswith('vlan ')])
        if vlan_commands > 10:
            checks.append(SafetyCheck(
                check_type="bulk_vlan_config",
                level=SafetyLevel.MEDIUM,
                message=f"Creating/modifying {vlan_commands} VLANs",
                recommendation="Ensure VLAN IDs don't conflict with existing configuration"
            ))
        
        return checks
    
    def _check_time_based_safety(self, commands: List[str], context: Dict[str, Any]) -> List[SafetyCheck]:
        """Check time-based safety (business hours, maintenance windows)."""
        checks = []
        
        # This would integrate with business hour checking
        # For now, just check if it's a disruptive operation
        disruptive_commands = [cmd for cmd in commands 
                             if any(pattern in cmd.lower() 
                                   for pattern in ['reload', 'shutdown', 'erase'])]
        
        if disruptive_commands:
            checks.append(SafetyCheck(
                check_type="maintenance_window",
                level=SafetyLevel.HIGH,
                message="Disruptive commands detected - verify maintenance window",
                recommendation="Ensure changes are scheduled during approved maintenance window"
            ))
        
        return checks
    
    def _get_command_recommendation(self, command: str, safety_level: str) -> str:
        """Get recommendation for risky command."""
        command_lower = command.lower()
        
        if 'reload' in command_lower:
            return "Schedule reload during maintenance window and verify configuration is saved"
        elif 'shutdown' in command_lower:
            return "Verify interface is not critical for network connectivity"
        elif 'erase' in command_lower:
            return "Backup current configuration before erasing"
        elif 'no vlan' in command_lower:
            return "Verify VLAN is not in use before removal"
        elif 'no ip route' in command_lower:
            return "Verify route removal won't impact reachability"
        else:
            return "Review command impact and test in lab environment if possible"
    
    def require_confirmation(
        self,
        operation_type: str,
        details: str,
        safety_level: str = SafetyLevel.MEDIUM,
        additional_info: Optional[List[str]] = None
    ) -> bool:
        """Require user confirmation for operations."""
        if self.auto_confirm:
            return True
        
        if not self.console or not Confirm:
            # Fallback to basic input if rich is not available
            try:
                response = input(f"Confirm {operation_type}: {details} [y/N]: ").lower()
                return response in ['y', 'yes']
            except (EOFError, KeyboardInterrupt):
                return False
        
        # Use rich for better presentation
        level_colors = {
            SafetyLevel.LOW: "blue",
            SafetyLevel.MEDIUM: "yellow", 
            SafetyLevel.HIGH: "red",
            SafetyLevel.CRITICAL: "bold red"
        }
        
        color = level_colors.get(safety_level, "yellow")
        
        # Create confirmation panel
        panel_content = f"[{color}]{operation_type.upper()}[/{color}]\n\n{details}"
        
        if additional_info:
            panel_content += "\n\nAdditional Information:"
            for info in additional_info:
                panel_content += f"\n• {info}"
        
        panel_content += f"\n\n[dim]Safety Level: {safety_level.upper()}[/dim]"
        
        self.console.print(Panel(
            panel_content,
            title="Confirmation Required",
            border_style=color
        ))
        
        return Confirm.ask("Proceed with this operation?", default=False)
    
    def display_safety_summary(self, checks: List[SafetyCheck]) -> None:
        """Display safety check summary."""
        if not self.console:
            # Fallback display
            for check in checks:
                print(f"{check}")
            return
        
        if not checks:
            self.console.print("[green]✓ No safety concerns detected[/green]")
            return
        
        # Count checks by level
        level_counts = {}
        for check in checks:
            level_counts[check.level] = level_counts.get(check.level, 0) + 1
        
        # Create summary table
        table = Table(title="Safety Check Summary")
        table.add_column("Level", style="bold")
        table.add_column("Type")
        table.add_column("Message")
        table.add_column("Recommendation", max_width=40)
        
        level_styles = {
            SafetyLevel.LOW: "blue",
            SafetyLevel.MEDIUM: "yellow",
            SafetyLevel.HIGH: "red", 
            SafetyLevel.CRITICAL: "bold red"
        }
        
        for check in sorted(checks, key=lambda x: ['low', 'medium', 'high', 'critical'].index(x.level)):
            style = level_styles.get(check.level, "")
            table.add_row(
                f"[{style}]{check.level.upper()}[/{style}]",
                check.check_type.replace('_', ' ').title(),
                check.message,
                check.recommendation or "-"
            )
        
        self.console.print(table)
        
        # Show summary counts
        summary = ", ".join(f"{count} {level}" for level, count in level_counts.items())
        self.console.print(f"\n[bold]Total: {len(checks)} safety concerns ({summary})[/bold]")
    
    def should_proceed_with_checks(self, checks: List[SafetyCheck]) -> bool:
        """Determine if operation should proceed based on safety checks."""
        if not checks:
            return True
        
        # Count critical and high-level issues
        critical_count = len([c for c in checks if c.level == SafetyLevel.CRITICAL])
        high_count = len([c for c in checks if c.level == SafetyLevel.HIGH])
        
        if critical_count > 0:
            return self.require_confirmation(
                "CRITICAL OPERATION",
                f"Operation has {critical_count} critical safety concern(s)",
                SafetyLevel.CRITICAL,
                [c.message for c in checks if c.level == SafetyLevel.CRITICAL][:3]
            )
        elif high_count > 0:
            return self.require_confirmation(
                "HIGH RISK OPERATION", 
                f"Operation has {high_count} high-risk safety concern(s)",
                SafetyLevel.HIGH,
                [c.message for c in checks if c.level == SafetyLevel.HIGH][:3]
            )
        elif len(checks) > 5:
            return self.require_confirmation(
                "MULTIPLE SAFETY CONCERNS",
                f"Operation has {len(checks)} safety concerns",
                SafetyLevel.MEDIUM
            )
        else:
            return True  # Proceed with low/medium issues without confirmation