#!/usr/bin/env python3
"""Demo script showcasing Config-Genie functionality."""

import sys
from pathlib import Path
import tempfile

# Add source directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config_genie.inventory import Device, Inventory
from config_genie.templates import Template, TemplateManager
from config_genie.validation import CiscoCommandValidator
from config_genie.execution import ExecutionManager
from config_genie.connector import ConnectionManager
from config_genie.logging import SessionLogger
from config_genie.safety import SafetyManager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
except ImportError:
    console = None

def print_section(title):
    """Print section header."""
    if console:
        console.print(f"\n[bold blue]{title}[/bold blue]")
    else:
        print(f"\n{title}")
        print("=" * len(title))

def main():
    """Run Config-Genie demo."""
    
    if console:
        console.print(Panel.fit(
            "[bold green]Config-Genie Demo[/bold green]\n"
            "Comprehensive network automation tool for Cisco devices",
            title="Welcome"
        ))
    else:
        print("Config-Genie Demo")
        print("================")
    
    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as temp_dir:
        
        # 1. Inventory Management Demo
        print_section("1. Inventory Management")
        
        inventory = Inventory()
        
        # Add sample devices
        devices = [
            Device("sw01-hq", "192.168.1.10", model="2960X", site="HQ", role="access"),
            Device("sw02-hq", "192.168.1.11", model="9300", site="HQ", role="distribution"), 
            Device("sw01-branch", "192.168.2.10", model="2960X", site="Branch", role="access")
        ]
        
        for device in devices:
            inventory.add_device(device)
        
        print(f"Loaded {len(inventory.devices)} devices into inventory")
        
        # Filter devices
        hq_devices = inventory.filter_devices(site="HQ")
        access_devices = inventory.filter_devices(role="access")
        
        print(f"HQ devices: {[d.name for d in hq_devices]}")
        print(f"Access devices: {[d.name for d in access_devices]}")
        
        # 2. Template Management Demo
        print_section("2. Template Management")
        
        template_manager = TemplateManager(temp_dir)
        builtin_templates = template_manager.list_templates()
        print(f"Available built-in templates: {len(builtin_templates)}")
        
        # Create custom template
        custom_template = Template(
            name="port_security_config",
            description="Basic port security configuration",
            commands=[
                "interface ${interface}",
                "switchport mode access",
                "switchport access vlan ${vlan}",
                "switchport port-security",
                "switchport port-security maximum 2",
                "switchport port-security violation restrict",
                "no shutdown"
            ],
            variables={
                "interface": "GigabitEthernet0/1",
                "vlan": "10"
            }
        )
        
        template_manager.save_template(custom_template)
        print(f"Created custom template: {custom_template.name}")
        
        # Render template
        rendered_commands = custom_template.render({
            "interface": "GigabitEthernet0/5",
            "vlan": "20"
        })
        print(f"Rendered commands: {rendered_commands[:2]}...")
        
        # 3. Validation Demo
        print_section("3. Command Validation")
        
        validator = CiscoCommandValidator()
        
        # Validate safe commands
        safe_commands = [
            "interface GigabitEthernet0/1",
            "description User Port",
            "switchport mode access",
            "no shutdown"
        ]
        
        safe_result = validator.validate_commands(safe_commands, devices[0])
        print(f"Safe commands validation - Valid: {safe_result.is_valid}, Warnings: {len(safe_result.warnings)}")
        
        # Validate risky commands
        risky_commands = ["reload", "erase startup-config", "shutdown"]
        risky_result = validator.validate_commands(risky_commands, devices[0])
        print(f"Risky commands validation - Valid: {risky_result.is_valid}, Warnings: {len(risky_result.warnings)}")
        
        # 4. Safety Checks Demo
        print_section("4. Safety Checks")
        
        safety_manager = SafetyManager(console=console, auto_confirm=True)
        
        # Check multi-device operation safety
        safety_checks = safety_manager.perform_safety_checks(rendered_commands, devices)
        print(f"Safety checks found {len(safety_checks)} concerns")
        
        for check in safety_checks:
            print(f"  - [{check.level.upper()}] {check.check_type}: {check.message[:50]}...")
        
        # 5. Execution Planning Demo  
        print_section("5. Execution Planning")
        
        connection_manager = ConnectionManager()
        execution_manager = ExecutionManager(connection_manager)
        
        # Create execution plan
        plan = execution_manager.create_execution_plan(
            devices=devices[:2],  # First 2 devices
            commands=rendered_commands,
            dry_run=True,
            validate=True
        )
        
        print(f"Created execution plan for {len(plan.devices)} devices")
        print(f"Dry run mode: {plan.dry_run}")
        print(f"Validation results: {len(plan.validation_results)} devices validated")
        
        # Execute plan (dry run)
        results = execution_manager.execute_plan(plan)
        
        successful = sum(1 for r in results.values() if r.status.value == "success")
        print(f"Execution results: {successful}/{len(results)} devices successful")
        
        # 6. Logging Demo
        print_section("6. Session Logging")
        
        logger = SessionLogger(temp_dir)
        
        # Log various activities
        logger.log_connection_attempt(devices[0], True)
        logger.log_validation_result(devices[0], safe_commands, 0, 0)
        logger.log_template_usage(custom_template.name, devices[:2], {"interface": "Gi0/5", "vlan": "20"})
        
        for device_name, result in results.items():
            device = next(d for d in devices if d.name == device_name)
            logger.log_command_execution(
                device, rendered_commands, 
                result.status.value == "success",
                result.output, result.execution_time, 
                dry_run=True
            )
        
        # Show session statistics
        stats = logger.get_session_statistics()
        print(f"Session statistics:")
        print(f"  Total events: {stats['total_events']}")
        print(f"  Successful operations: {stats['successful_operations']}")
        print(f"  Devices involved: {len(stats['devices'])}")
        print(f"  Commands executed: {stats['commands_executed']}")
        
        # Show recent history
        history = logger.get_session_history(limit=3)
        print(f"Recent history ({len(history)} events):")
        for event in history:
            print(f"  - {event['event_type']}: {event.get('device_name', 'N/A')}")
        
        logger.close()
        
        # 7. CLI Integration Demo
        print_section("7. CLI Integration")
        
        print("Config-Genie provides several CLI commands:")
        print("  config-genie validate <inventory_file>  - Validate inventory")
        print("  config-genie templates                  - List available templates")
        print("  config-genie execute <command>          - Execute single command")
        print("  config-genie                            - Interactive mode")
        
        print("\nExample usage:")
        print("  config-genie validate sample_inventory.yml")
        print("  config-genie templates")
        print("  config-genie execute 'show version' -i inventory.yml --dry-run")
    
    if console:
        console.print("\n[green]✓ Demo completed successfully![/green]")
        console.print("[dim]Config-Genie is ready for network automation tasks.[/dim]")
    else:
        print("\n✓ Demo completed successfully!")
        print("Config-Genie is ready for network automation tasks.")

if __name__ == "__main__":
    main()