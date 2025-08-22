"""Logging and session history management."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .inventory import Device


class SessionLogger:
    """Manages session logging and history."""
    
    def __init__(self, log_dir: Optional[str] = None, log_level: str = "INFO"):
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            # Default to ~/.config/config-genie/logs
            home = Path.home()
            self.log_dir = home / '.config' / 'config-genie' / 'logs'
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up logging
        self.logger = logging.getLogger('config-genie')
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Create formatters
        self.console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        
        # Set up file handler
        log_file = self.log_dir / f"config-genie-{datetime.now().strftime('%Y%m%d')}.log"
        self.file_handler = logging.FileHandler(log_file)
        self.file_handler.setLevel(logging.DEBUG)
        self.file_handler.setFormatter(self.file_formatter)
        self.logger.addHandler(self.file_handler)
        
        # Session history
        self.session_history: List[Dict[str, Any]] = []
        self.current_session_id = self._generate_session_id()
        
        # Load previous history
        self._load_history()
        
        self.logger.info(f"Session started: {self.current_session_id}")
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        return f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    
    def _load_history(self) -> None:
        """Load previous session history."""
        history_file = self.log_dir / "session_history.json"
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    self.session_history = json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load session history: {e}")
                self.session_history = []
    
    def _save_history(self) -> None:
        """Save session history to file."""
        history_file = self.log_dir / "session_history.json"
        try:
            # Keep only last 1000 entries to prevent file from growing too large
            if len(self.session_history) > 1000:
                self.session_history = self.session_history[-1000:]
            
            with open(history_file, 'w') as f:
                json.dump(self.session_history, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save session history: {e}")
    
    def log_connection_attempt(self, device: Device, success: bool, error: Optional[str] = None) -> None:
        """Log device connection attempt."""
        if success:
            self.logger.info(f"Connected to device {device.name} ({device.ip_address})")
        else:
            self.logger.error(f"Failed to connect to device {device.name} ({device.ip_address}): {error}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'connection',
            'device_name': device.name,
            'device_ip': device.ip_address,
            'success': success,
            'error': error
        })
    
    def log_command_execution(
        self,
        device: Device,
        commands: List[str],
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        execution_time: Optional[float] = None,
        dry_run: bool = False
    ) -> None:
        """Log command execution."""
        command_summary = f"{len(commands)} commands" if len(commands) > 1 else commands[0] if commands else "no commands"
        
        if success:
            self.logger.info(f"Executed {command_summary} on {device.name} (dry_run={dry_run})")
        else:
            self.logger.error(f"Failed to execute {command_summary} on {device.name}: {error}")
        
        # Log individual commands at debug level
        for i, command in enumerate(commands):
            self.logger.debug(f"Command {i+1}/{len(commands)} on {device.name}: {command}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'command_execution',
            'device_name': device.name,
            'device_ip': device.ip_address,
            'commands': commands,
            'success': success,
            'output': output[:500] if output and len(output) > 500 else output,  # Truncate long output
            'error': error,
            'execution_time': execution_time,
            'dry_run': dry_run
        })
        
        self._save_history()
    
    def log_template_usage(
        self,
        template_name: str,
        devices: List[Device],
        variables: Optional[Dict[str, str]] = None,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """Log template usage."""
        device_names = [d.name for d in devices]
        
        if success:
            self.logger.info(f"Applied template '{template_name}' to devices: {', '.join(device_names)}")
        else:
            self.logger.error(f"Failed to apply template '{template_name}': {error}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'template_usage',
            'template_name': template_name,
            'devices': device_names,
            'variables': variables,
            'success': success,
            'error': error
        })
        
        self._save_history()
    
    def log_validation_result(
        self,
        device: Device,
        commands: List[str],
        validation_errors: int,
        validation_warnings: int,
        validation_details: Optional[str] = None
    ) -> None:
        """Log validation results."""
        self.logger.info(
            f"Validated {len(commands)} commands for {device.name}: "
            f"{validation_errors} errors, {validation_warnings} warnings"
        )
        
        if validation_details:
            self.logger.debug(f"Validation details for {device.name}: {validation_details}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'validation',
            'device_name': device.name,
            'device_ip': device.ip_address,
            'commands_count': len(commands),
            'validation_errors': validation_errors,
            'validation_warnings': validation_warnings,
            'validation_details': validation_details
        })
    
    def log_rollback(
        self,
        devices: List[Device],
        rollback_commands: List[str],
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """Log rollback operation."""
        device_names = [d.name for d in devices]
        
        if success:
            self.logger.info(f"Rollback completed successfully on devices: {', '.join(device_names)}")
        else:
            self.logger.error(f"Rollback failed on devices {', '.join(device_names)}: {error}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'rollback',
            'devices': device_names,
            'rollback_commands': rollback_commands,
            'success': success,
            'error': error
        })
        
        self._save_history()
    
    def log_safety_check(
        self,
        check_type: str,
        details: str,
        severity: str = "info"
    ) -> None:
        """Log safety check results."""
        log_method = getattr(self.logger, severity.lower(), self.logger.info)
        log_method(f"Safety check [{check_type}]: {details}")
        
        # Add to session history
        self.session_history.append({
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'safety_check',
            'check_type': check_type,
            'details': details,
            'severity': severity
        })
    
    def get_session_history(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        device_name: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get session history with optional filtering."""
        history = self.session_history
        
        # Filter by session ID
        if session_id:
            history = [h for h in history if h.get('session_id') == session_id]
        
        # Filter by event type
        if event_type:
            history = [h for h in history if h.get('event_type') == event_type]
        
        # Filter by device name
        if device_name:
            history = [h for h in history if h.get('device_name') == device_name or 
                      device_name in h.get('devices', [])]
        
        # Apply limit
        if limit:
            history = history[-limit:]
        
        return history
    
    def get_session_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a session or all sessions."""
        history = self.get_session_history(session_id=session_id)
        
        stats = {
            'total_events': len(history),
            'event_types': {},
            'devices': set(),
            'successful_operations': 0,
            'failed_operations': 0,
            'commands_executed': 0,
            'session_duration': None
        }
        
        if not history:
            return stats
        
        # Calculate statistics
        first_event = min(h['timestamp'] for h in history)
        last_event = max(h['timestamp'] for h in history)
        
        try:
            first_time = datetime.fromisoformat(first_event.replace('Z', '+00:00'))
            last_time = datetime.fromisoformat(last_event.replace('Z', '+00:00'))
            stats['session_duration'] = (last_time - first_time).total_seconds()
        except:
            pass
        
        for event in history:
            # Count event types
            event_type = event.get('event_type', 'unknown')
            stats['event_types'][event_type] = stats['event_types'].get(event_type, 0) + 1
            
            # Track devices
            if 'device_name' in event:
                stats['devices'].add(event['device_name'])
            if 'devices' in event:
                stats['devices'].update(event['devices'])
            
            # Count successes/failures
            if event.get('success') is True:
                stats['successful_operations'] += 1
            elif event.get('success') is False:
                stats['failed_operations'] += 1
            
            # Count commands
            if event.get('event_type') == 'command_execution':
                stats['commands_executed'] += len(event.get('commands', []))
        
        stats['devices'] = list(stats['devices'])
        
        return stats
    
    def export_history(self, filename: str, session_id: Optional[str] = None) -> None:
        """Export history to JSON file."""
        history = self.get_session_history(session_id=session_id)
        
        export_path = Path(filename)
        if not export_path.is_absolute():
            export_path = self.log_dir / export_path
        
        with open(export_path, 'w') as f:
            json.dump(history, f, indent=2, default=str)
        
        self.logger.info(f"Exported {len(history)} history entries to {export_path}")
    
    def clear_history(self, older_than_days: Optional[int] = None) -> int:
        """Clear history, optionally keeping recent entries."""
        if older_than_days is None:
            # Clear all history
            count = len(self.session_history)
            self.session_history = []
        else:
            # Clear entries older than specified days
            cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff = cutoff.replace(day=cutoff.day - older_than_days)
            cutoff_iso = cutoff.isoformat()
            
            original_count = len(self.session_history)
            self.session_history = [
                h for h in self.session_history 
                if h.get('timestamp', '') >= cutoff_iso
            ]
            count = original_count - len(self.session_history)
        
        self._save_history()
        self.logger.info(f"Cleared {count} history entries")
        return count
    
    def close(self) -> None:
        """Close logger and save final state."""
        self.logger.info(f"Session ended: {self.current_session_id}")
        self._save_history()
        
        # Remove handlers to avoid issues
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)