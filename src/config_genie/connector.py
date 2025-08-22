"""SSH connector module for Cisco devices."""

import re
import time
from typing import Dict, List, Optional, Tuple

try:
    import paramiko
except ImportError:
    paramiko = None

from .inventory import Device


class CiscoSSHConnector:
    """SSH connector for Cisco devices with IOS/IOS-XE support."""
    
    def __init__(
        self, 
        device: Device, 
        username: str, 
        password: str,
        enable_password: Optional[str] = None,
        timeout: int = 30,
        banner_timeout: int = 15
    ):
        self.device = device
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self.banner_timeout = banner_timeout
        
        self.ssh_client = None
        self.shell = None
        self.connected = False
        self.privileged = False
    
    def connect(self) -> bool:
        """Establish SSH connection to the device."""
        if paramiko is None:
            raise ImportError("paramiko is required for SSH connections")
        
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.device.ip_address,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                banner_timeout=self.banner_timeout,
                look_for_keys=False,
                allow_agent=False
            )
            
            # Open interactive shell
            self.shell = self.ssh_client.invoke_shell()
            self.shell.settimeout(self.timeout)
            
            # Wait for initial prompt and clear buffer
            time.sleep(2)
            self._clear_buffer()
            
            # Disable paging
            self._send_command("terminal length 0")
            self._send_command("terminal width 0")
            
            self.connected = True
            return True
            
        except Exception as e:
            self._cleanup()
            raise ConnectionError(f"Failed to connect to {self.device.name}: {str(e)}")
    
    def enter_enable_mode(self) -> bool:
        """Enter privileged EXEC mode."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        
        if self.privileged:
            return True
        
        try:
            # Check current mode
            output = self._send_command("", expect_prompt=True)
            if "#" in output:
                self.privileged = True
                return True
            
            # Enter enable mode
            if not self.enable_password:
                raise ValueError("Enable password required but not provided")
            
            self.shell.send("enable\n")
            time.sleep(1)
            
            # Send enable password
            self.shell.send(f"{self.enable_password}\n")
            time.sleep(2)
            
            # Verify we're in enable mode
            output = self._send_command("", expect_prompt=True)
            if "#" in output:
                self.privileged = True
                return True
            else:
                raise ConnectionError("Failed to enter privileged mode - check enable password")
                
        except Exception as e:
            raise ConnectionError(f"Failed to enter enable mode: {str(e)}")
    
    def send_command(self, command: str, expect_prompt: bool = True) -> str:
        """Send a command and return the output."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        
        return self._send_command(command, expect_prompt)
    
    def send_config_commands(self, commands: List[str]) -> Dict[str, str]:
        """Send configuration commands and return results."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        if not self.privileged:
            raise ConnectionError("Must be in privileged mode for configuration commands")
        
        results = {}
        
        # Enter config mode
        config_output = self._send_command("configure terminal")
        if "config" not in config_output.lower():
            raise ConnectionError("Failed to enter configuration mode")
        
        try:
            for command in commands:
                if command.strip():
                    output = self._send_command(command.strip())
                    results[command] = output
                    
                    # Check for errors
                    if self._has_config_error(output):
                        raise ValueError(f"Configuration error for command '{command}': {output}")
        
        finally:
            # Exit config mode
            self._send_command("end")
        
        return results
    
    def get_running_config(self, section: Optional[str] = None) -> str:
        """Get running configuration or specific section."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        
        command = "show running-config"
        if section:
            command += f" | section {section}"
        
        return self._send_command(command)
    
    def save_config(self) -> str:
        """Save running config to startup config."""
        if not self.connected or not self.privileged:
            raise ConnectionError("Must be connected and in privileged mode")
        
        # Use 'copy run start' and handle prompts
        self.shell.send("copy running-config startup-config\n")
        time.sleep(1)
        
        # Handle confirmation prompt
        output = self._read_until_prompt(timeout=10)
        if "[startup-config]" in output:
            self.shell.send("\n")  # Confirm default filename
            output += self._read_until_prompt(timeout=10)
        
        return output
    
    def disconnect(self) -> None:
        """Close SSH connection."""
        self._cleanup()
    
    def _send_command(self, command: str, expect_prompt: bool = True) -> str:
        """Internal method to send command and get output."""
        if command:
            self.shell.send(f"{command}\n")
        
        if expect_prompt:
            return self._read_until_prompt()
        else:
            time.sleep(1)
            return self._read_available()
    
    def _read_until_prompt(self, timeout: Optional[int] = None) -> str:
        """Read output until device prompt is found."""
        if timeout is None:
            timeout = self.timeout
        
        output = ""
        start_time = time.time()
        
        # Common Cisco prompts
        prompt_patterns = [
            r'[\w\-\.]+[>#]\s*$',  # Basic prompt
            r'[\w\-\.]+\(config[^)]*\)#\s*$',  # Config mode
            r'--More--',  # Paging prompt
            r'\[confirm\]',  # Confirmation prompt
        ]
        
        while time.time() - start_time < timeout:
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                output += chunk
                
                # Handle more prompts
                if "--More--" in chunk:
                    self.shell.send(" ")  # Space to continue
                    continue
                
                # Check for command prompt
                lines = output.split('\n')
                if lines:
                    last_line = lines[-1].strip()
                    for pattern in prompt_patterns:
                        if re.search(pattern, last_line):
                            return self._clean_output(output)
            
            time.sleep(0.1)
        
        raise TimeoutError(f"Timeout waiting for prompt. Last output: {output[-200:]}")
    
    def _read_available(self) -> str:
        """Read all available output without waiting for prompt."""
        output = ""
        time.sleep(0.5)  # Brief pause to let output accumulate
        
        while self.shell.recv_ready():
            chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
            output += chunk
            time.sleep(0.1)
        
        return self._clean_output(output)
    
    def _clear_buffer(self) -> None:
        """Clear any data in the receive buffer."""
        while self.shell.recv_ready():
            self.shell.recv(4096)
            time.sleep(0.1)
    
    def _clean_output(self, output: str) -> str:
        """Clean command output by removing prompts and control characters."""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output = ansi_escape.sub('', output)
        
        # Remove carriage returns
        output = output.replace('\r', '')
        
        # Remove the command echo (first line usually)
        lines = output.split('\n')
        if len(lines) > 1:
            # Remove first line if it looks like command echo
            first_line = lines[0].strip()
            if first_line and not first_line.startswith(('!', ' ')):
                lines = lines[1:]
        
        # Remove last line if it's a prompt
        if lines:
            last_line = lines[-1].strip()
            if re.search(r'[\w\-\.]+[>#]\s*$', last_line):
                lines = lines[:-1]
        
        return '\n'.join(lines).strip()
    
    def _has_config_error(self, output: str) -> bool:
        """Check if output contains configuration errors."""
        error_patterns = [
            r'% Invalid input detected',
            r'% Ambiguous command',
            r'% Incomplete command',
            r'% Unknown command',
            r'% Access denied',
        ]
        
        for pattern in error_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True
        
        return False
    
    def _cleanup(self) -> None:
        """Clean up connection resources."""
        self.connected = False
        self.privileged = False
        
        if self.shell:
            try:
                self.shell.close()
            except:
                pass
            self.shell = None
        
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None


class ConnectionManager:
    """Manage multiple device connections."""
    
    def __init__(self):
        self.connections: Dict[str, CiscoSSHConnector] = {}
        self.credentials: Optional[Tuple[str, str, Optional[str]]] = None
    
    def set_credentials(self, username: str, password: str, enable_password: Optional[str] = None) -> None:
        """Set default credentials for connections."""
        self.credentials = (username, password, enable_password)
    
    def connect_device(self, device: Device, retry_count: int = 3) -> CiscoSSHConnector:
        """Connect to a device with retry logic."""
        if not self.credentials:
            raise ValueError("Credentials must be set before connecting")
        
        username, password, enable_password = self.credentials
        
        for attempt in range(retry_count):
            try:
                connector = CiscoSSHConnector(
                    device=device,
                    username=username,
                    password=password,
                    enable_password=enable_password
                )
                
                connector.connect()
                
                # Try to enter enable mode if enable password provided
                if enable_password:
                    connector.enter_enable_mode()
                
                self.connections[device.name] = connector
                return connector
                
            except Exception as e:
                if attempt == retry_count - 1:
                    raise e
                time.sleep(2 ** attempt)  # Exponential backoff
        
        raise ConnectionError(f"Failed to connect to {device.name} after {retry_count} attempts")
    
    def disconnect_device(self, device_name: str) -> None:
        """Disconnect from a specific device."""
        if device_name in self.connections:
            self.connections[device_name].disconnect()
            del self.connections[device_name]
    
    def disconnect_all(self) -> None:
        """Disconnect from all devices."""
        for connector in self.connections.values():
            connector.disconnect()
        self.connections.clear()
    
    def get_connection(self, device_name: str) -> Optional[CiscoSSHConnector]:
        """Get connection for a device."""
        return self.connections.get(device_name)