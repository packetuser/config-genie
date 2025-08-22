"""Integration tests for Config-Genie components."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config_genie.inventory import Device, Inventory
from config_genie.templates import Template, TemplateManager
from config_genie.validation import CiscoCommandValidator
from config_genie.execution import ExecutionManager
from config_genie.connector import ConnectionManager
from config_genie.logging import SessionLogger
from config_genie.safety import SafetyManager


class TestIntegration:
    """Integration tests combining multiple modules."""
    
    def test_complete_workflow_dry_run(self):
        """Test complete workflow in dry-run mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up components
            inventory = Inventory()
            devices = [
                Device("sw01", "192.168.1.1", model="2960X", site="HQ"),
                Device("sw02", "192.168.1.2", model="9300", site="HQ")
            ]
            for device in devices:
                inventory.add_device(device)
            
            # Set up template manager
            template_manager = TemplateManager(temp_dir)
            
            # Set up execution components
            connection_manager = ConnectionManager()
            execution_manager = ExecutionManager(connection_manager)
            
            # Set up logging
            logger = SessionLogger(temp_dir)
            
            # Set up safety manager
            safety_manager = SafetyManager(auto_confirm=True)
            
            # Create a test template
            template = Template(
                name="test_interface_config",
                commands=[
                    "interface ${interface}",
                    "description Test Port",
                    "switchport mode access",
                    "switchport access vlan ${vlan}",
                    "no shutdown"
                ],
                variables={"interface": "GigabitEthernet0/1", "vlan": "10"}
            )
            
            template_manager.save_template(template)
            
            # Test workflow: validate -> safety check -> execute (dry run)
            commands = template.render({"interface": "GigabitEthernet0/2", "vlan": "20"})
            
            # Validation
            validator = CiscoCommandValidator()
            for device in devices:
                validation_result = validator.validate_commands(commands, device)
                assert validation_result.is_valid
                logger.log_validation_result(device, commands, 0, 0)
            
            # Safety checks
            safety_checks = safety_manager.perform_safety_checks(commands, devices)
            # Should have some safety concerns (mixed models)
            assert len(safety_checks) > 0
            
            # Execution (dry run)
            plan = execution_manager.create_execution_plan(
                devices, commands, dry_run=True, validate=True
            )
            results = execution_manager.execute_plan(plan)
            
            # Verify results
            assert len(results) == 2
            for device_name, result in results.items():
                assert result.status.value == "success"  # Dry run should succeed
                logger.log_command_execution(
                    next(d for d in devices if d.name == device_name),
                    commands, True, result.output, 
                    execution_time=result.execution_time, dry_run=True
                )
            
            # Check history
            history = logger.get_session_history()
            assert len(history) >= 4  # 2 validations + 2 executions
            
            stats = logger.get_session_statistics()
            assert stats['successful_operations'] >= 2
            
            logger.close()
    
    def test_template_to_execution_workflow(self):
        """Test workflow from template creation to execution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create components
            template_manager = TemplateManager(temp_dir)
            connection_manager = ConnectionManager()
            execution_manager = ExecutionManager(connection_manager)
            
            # Create test devices
            devices = [Device("test-sw", "192.168.1.1", model="2960X")]
            
            # Create template from commands
            raw_commands = [
                "vlan 100",
                "name DATA_VLAN",
                "interface GigabitEthernet0/5",
                "switchport access vlan 100"
            ]
            
            template = template_manager.create_template_from_commands(
                name="vlan_setup",
                commands=raw_commands,
                description="Set up data VLAN"
            )
            
            template_manager.save_template(template)
            
            # Retrieve and execute template
            retrieved_template = template_manager.get_template("vlan_setup")
            assert retrieved_template is not None
            assert retrieved_template.name == "vlan_setup"
            
            # Execute template (dry run)
            results = execution_manager.execute_template(
                retrieved_template,
                devices,
                dry_run=True,
                validate=True
            )
            
            assert len(results) == 1
            assert "test-sw" in results
            assert results["test-sw"].status.value == "success"
    
    def test_validation_and_safety_integration(self):
        """Test integration between validation and safety modules."""
        devices = [Device("critical-sw", "192.168.1.1", model="9300")]
        
        # Create validator and safety manager
        validator = CiscoCommandValidator()
        safety_manager = SafetyManager(auto_confirm=True)
        
        # Test with risky commands
        risky_commands = [
            "reload",
            "erase startup-config", 
            "interface management 0",
            "shutdown"
        ]
        
        # Validation should pass (syntax is correct)
        validation_result = validator.validate_commands(risky_commands, devices[0])
        assert validation_result.is_valid  # No syntax errors
        
        # Safety checks should catch risks
        safety_checks = safety_manager.perform_safety_checks(risky_commands, devices)
        critical_checks = [c for c in safety_checks if c.level == "critical"]
        high_checks = [c for c in safety_checks if c.level == "high"]
        
        assert len(critical_checks) >= 2  # reload and erase should be critical
        assert len(high_checks) >= 1   # management interface should be high
        
        # Test safety decision making
        should_proceed = safety_manager.should_proceed_with_checks(safety_checks)
        # With auto_confirm=True, should proceed after confirmation
        assert should_proceed is True
    
    def test_error_handling_integration(self):
        """Test error handling across modules."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test invalid inventory loading
            inventory = Inventory()
            
            try:
                inventory.load_yaml("nonexistent_file.yml")
                assert False, "Should have raised FileNotFoundError"
            except FileNotFoundError:
                pass  # Expected
            
            # Test invalid template
            template_manager = TemplateManager(temp_dir)
            invalid_template = Template("", [])  # Empty name and commands
            
            validation_issues = template_manager.validate_template(invalid_template)
            assert len(validation_issues) > 0
            
            # Test execution without connection
            connection_manager = ConnectionManager()
            execution_manager = ExecutionManager(connection_manager)
            
            device = Device("unreachable", "192.168.999.999")
            plan = execution_manager.create_execution_plan([device], ["show version"], dry_run=True)
            
            # Dry run should still work even without connection
            results = execution_manager.execute_plan(plan)
            assert len(results) == 1
            assert results["unreachable"].status.value == "success"  # Dry run simulates success
    
    def test_history_and_logging_integration(self):
        """Test logging integration across all modules."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = SessionLogger(temp_dir)
            
            # Test multiple types of logging
            device = Device("test-device", "192.168.1.1")
            
            # Connection logging
            logger.log_connection_attempt(device, True)
            logger.log_connection_attempt(device, False, "Timeout")
            
            # Command execution logging
            commands = ["show version", "show interfaces"]
            logger.log_command_execution(device, commands, True, "Output", 1.5, False)
            
            # Template logging
            logger.log_template_usage("basic_config", [device], {"vlan": "10"})
            
            # Validation logging
            logger.log_validation_result(device, commands, 0, 1, "One warning")
            
            # Safety check logging
            logger.log_safety_check("risky_command", "Found risky operation", "high")
            
            # Rollback logging
            logger.log_rollback([device], ["undo command"], True)
            
            # Verify comprehensive history
            full_history = logger.get_session_history()
            assert len(full_history) >= 7
            
            # Test filtering
            connection_history = logger.get_session_history(event_type='connection')
            assert len(connection_history) == 2
            
            command_history = logger.get_session_history(event_type='command_execution')
            assert len(command_history) == 1
            
            device_history = logger.get_session_history(device_name='test-device')
            assert len(device_history) >= 5  # Most events are for this device
            
            # Test statistics
            stats = logger.get_session_statistics()
            assert stats['total_events'] >= 7
            assert stats['successful_operations'] >= 3
            assert stats['failed_operations'] >= 1
            assert 'test-device' in stats['devices']
            
            logger.close()
    
    def test_full_cli_integration(self):
        """Test CLI integration with underlying modules."""
        # This would test the CLI commands, but since we can't easily test 
        # interactive CLI, we'll test the underlying functionality
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test inventory file
            inventory_file = Path(temp_dir) / "test_inventory.txt"
            with open(inventory_file, 'w') as f:
                f.write("192.168.1.1,sw01,2960X,HQ,access\n")
                f.write("192.168.1.2,sw02,9300,HQ,distribution\n")
            
            # Test inventory loading (similar to CLI validate command)
            inventory = Inventory()
            inventory.load_txt(str(inventory_file))
            
            devices = inventory.get_all_devices()
            assert len(devices) == 2
            assert devices[0].name == "sw01"
            assert devices[1].model == "9300"
            
            # Test device filtering (similar to CLI device selection)
            hq_devices = inventory.filter_devices(site="HQ")
            assert len(hq_devices) == 2
            
            access_devices = inventory.filter_devices(role="access")
            assert len(access_devices) == 1
            assert access_devices[0].name == "sw01"
            
            # Test template listing (similar to CLI templates command)
            template_manager = TemplateManager(temp_dir)
            templates = template_manager.list_templates()
            assert len(templates) >= 5  # Built-in templates
            
            basic_template = template_manager.get_template("basic_interface_config")
            assert basic_template is not None
            assert len(basic_template.commands) > 0