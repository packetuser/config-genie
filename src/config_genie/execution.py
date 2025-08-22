"""Execution manager for orchestrating command execution across devices."""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any

from .inventory import Device
from .connector import ConnectionManager, CiscoSSHConnector
from .validation import CiscoCommandValidator, ValidationResult
from .templates import Template


class ExecutionStatus(Enum):
    """Status of command execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExecutionResult:
    """Result of executing commands on a device."""
    device_name: str
    status: ExecutionStatus
    commands: List[str]
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    rollback_commands: Optional[List[str]] = None


@dataclass
class ExecutionPlan:
    """Plan for executing commands across devices."""
    devices: List[Device]
    commands: List[str]
    dry_run: bool
    stop_on_error: bool
    rollback_on_failure: bool
    validation_results: Dict[str, ValidationResult]


class ExecutionManager:
    """Orchestrates command execution across multiple devices."""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.validator = CiscoCommandValidator()
        self.execution_history: List[Dict[str, Any]] = []
        
        # Execution state
        self.current_execution: Optional[Dict[str, Any]] = None
        self.rollback_stack: List[Dict[str, Any]] = []
    
    def create_execution_plan(
        self,
        devices: List[Device],
        commands: List[str],
        dry_run: bool = False,
        stop_on_error: bool = True,
        rollback_on_failure: bool = True,
        validate: bool = True
    ) -> ExecutionPlan:
        """Create an execution plan with validation."""
        
        validation_results = {}
        
        if validate:
            # Validate commands for each device
            for device in devices:
                result = self.validator.validate_commands(commands, device)
                validation_results[device.name] = result
        
        return ExecutionPlan(
            devices=devices,
            commands=commands,
            dry_run=dry_run,
            stop_on_error=stop_on_error,
            rollback_on_failure=rollback_on_failure,
            validation_results=validation_results
        )
    
    def execute_plan(self, plan: ExecutionPlan) -> Dict[str, ExecutionResult]:
        """Execute the planned commands across devices."""
        
        # Check validation results
        if not plan.dry_run:
            validation_errors = []
            for device_name, result in plan.validation_results.items():
                if not result.is_valid:
                    validation_errors.extend(f"{device_name}: {err}" for err in result.errors)
            
            if validation_errors:
                raise ValueError(f"Validation failed:\n" + "\n".join(validation_errors))
        
        # Execute commands
        results = {}
        successful_devices = []
        
        # Track execution for rollback
        execution_session = {
            'id': int(time.time()),
            'devices': [d.name for d in plan.devices],
            'commands': plan.commands,
            'start_time': time.time(),
            'dry_run': plan.dry_run,
            'results': {}
        }
        
        self.current_execution = execution_session
        
        try:
            for device in plan.devices:
                result = self._execute_on_device(device, plan.commands, plan.dry_run)
                results[device.name] = result
                execution_session['results'][device.name] = result
                
                if result.status == ExecutionStatus.SUCCESS:
                    successful_devices.append(device.name)
                elif result.status == ExecutionStatus.FAILED:
                    if plan.stop_on_error:
                        # Rollback successful devices if configured
                        if plan.rollback_on_failure and successful_devices:
                            self._rollback_devices(successful_devices, plan.commands, results)
                        break
        
        finally:
            execution_session['end_time'] = time.time()
            execution_session['duration'] = execution_session['end_time'] - execution_session['start_time']
            
            # Add to history
            self.execution_history.append(execution_session)
            
            # Add to rollback stack if successful and not dry run
            if not plan.dry_run and successful_devices:
                self.rollback_stack.append({
                    'session_id': execution_session['id'],
                    'devices': successful_devices,
                    'commands': plan.commands,
                    'timestamp': execution_session['start_time']
                })
            
            self.current_execution = None
        
        return results
    
    def _execute_on_device(
        self, 
        device: Device, 
        commands: List[str], 
        dry_run: bool
    ) -> ExecutionResult:
        """Execute commands on a single device."""
        
        start_time = time.time()
        
        try:
            # Get connection
            connection = self.connection_manager.get_connection(device.name)
            if not connection or not connection.connected:
                return ExecutionResult(
                    device_name=device.name,
                    status=ExecutionStatus.FAILED,
                    commands=commands,
                    error="Device not connected"
                )
            
            if dry_run:
                # Simulate execution
                return ExecutionResult(
                    device_name=device.name,
                    status=ExecutionStatus.SUCCESS,
                    commands=commands,
                    output="DRY RUN - Commands would be executed",
                    execution_time=time.time() - start_time
                )
            
            # Execute commands
            output_lines = []
            
            # Check if commands are configuration commands
            config_commands = self._filter_config_commands(commands)
            show_commands = self._filter_show_commands(commands)
            
            # Execute show commands directly
            for command in show_commands:
                try:
                    output = connection.send_command(command)
                    output_lines.append(f"# {command}")
                    output_lines.append(output)
                except Exception as e:
                    return ExecutionResult(
                        device_name=device.name,
                        status=ExecutionStatus.FAILED,
                        commands=commands,
                        error=f"Failed to execute '{command}': {str(e)}",
                        execution_time=time.time() - start_time
                    )
            
            # Execute configuration commands
            if config_commands:
                try:
                    config_output = connection.send_config_commands(config_commands)
                    for command, output in config_output.items():
                        output_lines.append(f"(config)# {command}")
                        if output.strip():
                            output_lines.append(output)
                except Exception as e:
                    return ExecutionResult(
                        device_name=device.name,
                        status=ExecutionStatus.FAILED,
                        commands=commands,
                        error=f"Configuration failed: {str(e)}",
                        execution_time=time.time() - start_time
                    )
            
            # Generate rollback commands
            rollback_commands = self._generate_rollback_commands(commands)
            
            return ExecutionResult(
                device_name=device.name,
                status=ExecutionStatus.SUCCESS,
                commands=commands,
                output="\n".join(output_lines),
                execution_time=time.time() - start_time,
                rollback_commands=rollback_commands
            )
            
        except Exception as e:
            return ExecutionResult(
                device_name=device.name,
                status=ExecutionStatus.FAILED,
                commands=commands,
                error=f"Execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _filter_config_commands(self, commands: List[str]) -> List[str]:
        """Filter out configuration commands."""
        config_commands = []
        for command in commands:
            command = command.strip()
            if not command or command.startswith('!'):
                continue
            
            # Skip show commands and other exec commands
            if not command.lower().startswith(('show', 'ping', 'traceroute', 'telnet', 'ssh')):
                config_commands.append(command)
        
        return config_commands
    
    def _filter_show_commands(self, commands: List[str]) -> List[str]:
        """Filter out show/exec commands."""
        show_commands = []
        for command in commands:
            command = command.strip()
            if command.lower().startswith(('show', 'ping', 'traceroute')):
                show_commands.append(command)
        
        return show_commands
    
    def _generate_rollback_commands(self, commands: List[str]) -> List[str]:
        """Generate rollback commands for the given commands."""
        rollback_commands = []
        
        for command in reversed(commands):
            command = command.strip().lower()
            
            if not command or command.startswith('!'):
                continue
            
            # Generate opposite commands
            if command.startswith('no '):
                # Remove the 'no' to restore
                rollback_commands.append(command[3:].strip())
            elif any(command.startswith(cmd) for cmd in ['interface ', 'vlan ', 'ip route ']):
                # For creation commands, add 'no'
                rollback_commands.append(f"no {command}")
            elif 'shutdown' in command and not command.startswith('no'):
                # For shutdown, add no shutdown
                rollback_commands.append('no shutdown')
            elif command == 'no shutdown':
                # For no shutdown, add shutdown
                rollback_commands.append('shutdown')
            # Add more rollback patterns as needed
        
        return rollback_commands
    
    def _rollback_devices(
        self, 
        device_names: List[str], 
        original_commands: List[str],
        execution_results: Dict[str, ExecutionResult]
    ) -> Dict[str, ExecutionResult]:
        """Rollback commands on specified devices."""
        rollback_results = {}
        
        for device_name in device_names:
            result = execution_results.get(device_name)
            if not result or not result.rollback_commands:
                continue
            
            # Get device object
            device = None
            for conn_device in self.connection_manager.connections.values():
                if conn_device.device.name == device_name:
                    device = conn_device.device
                    break
            
            if device:
                rollback_result = self._execute_on_device(
                    device, 
                    result.rollback_commands, 
                    dry_run=False
                )
                rollback_result.status = ExecutionStatus.ROLLED_BACK
                rollback_results[device_name] = rollback_result
        
        return rollback_results
    
    def rollback_last_execution(self) -> Dict[str, ExecutionResult]:
        """Rollback the last successful execution."""
        if not self.rollback_stack:
            raise ValueError("No executions available for rollback")
        
        last_execution = self.rollback_stack.pop()
        
        rollback_results = {}
        for device_name in last_execution['devices']:
            # Find device
            device = None
            for conn in self.connection_manager.connections.values():
                if conn.device.name == device_name:
                    device = conn.device
                    break
            
            if device:
                rollback_commands = self._generate_rollback_commands(last_execution['commands'])
                result = self._execute_on_device(device, rollback_commands, dry_run=False)
                result.status = ExecutionStatus.ROLLED_BACK
                rollback_results[device_name] = result
        
        return rollback_results
    
    def execute_template(
        self,
        template: Template,
        devices: List[Device],
        variables: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, ExecutionResult]:
        """Execute a template on devices with variable substitution."""
        
        # Render template with variables
        rendered_commands = template.render(variables)
        
        # Create and execute plan
        plan = self.create_execution_plan(devices, rendered_commands, **kwargs)
        return self.execute_plan(plan)
    
    def get_execution_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get execution history."""
        history = self.execution_history
        if limit:
            history = history[-limit:]
        return history
    
    def get_rollback_stack(self) -> List[Dict[str, Any]]:
        """Get available rollback operations."""
        return list(self.rollback_stack)
    
    def clear_rollback_stack(self) -> None:
        """Clear the rollback stack."""
        self.rollback_stack.clear()