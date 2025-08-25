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
        timeout: int = 8,
        banner_timeout: int = 15,
        debug_mode: bool = False
    ):
        self.device = device
        self.username = username
        self.password = password
        self.enable_password = enable_password
        self.timeout = timeout
        self.banner_timeout = banner_timeout
        self.debug_mode = debug_mode
        
        self.ssh_client = None
        self.shell = None
        self.connected = False
        self.privileged = False
        self.in_config_mode = False
    
    def _debug_print(self, message: str, prefix: str = "DEBUG") -> None:
        """Print debug message if debug mode is enabled."""
        if self.debug_mode:
            print(f"[{prefix}] {self.device.name}: {message}")
    
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
            
            # Check if we're already in privileged mode by checking if prompt ends with #
            # We can see from previous commands if the prompt was already #
            try:
                # Send a simple show command to see current privilege
                output = self._send_command("show privilege")
                if "privilege level 15" in output.lower() or "current privilege level is 15" in output.lower():
                    self._debug_print("Already in privileged mode (level 15)", "SUCCESS")
                    self.privileged = True
                elif "#" in output:  # Fallback check for # in output
                    self._debug_print("Already in privileged mode (# detected)", "SUCCESS")
                    self.privileged = True
                else:
                    self._debug_print("Not in privileged mode", "INFO")
                    self.privileged = False
            except:
                # If privilege check fails, try to determine from previous command responses
                # Since we just ran terminal commands successfully, check if device shows privilege
                self._debug_print("Privilege check failed, assuming not privileged", "WARN")
                self.privileged = False
            
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
            
            # Simple enable mode approach - just send enable and test with a command
            self._debug_print("Sending 'enable' command", "SEND")
            self.shell.send("enable\n")
            time.sleep(2)  # Give it time to process
            
            # Read any available output (could be password prompt or new prompt)
            available_output = self._read_available()
            self._debug_print(f"Available output after enable: {repr(available_output)}", "RECV")
            
            # Check if device is asking for password
            if "Password:" in available_output or "password:" in available_output:
                self._debug_print("Device is asking for enable password", "RECV")
                if self.enable_password:
                    self._debug_print("Sending enable password", "SEND")
                    self.shell.send(f"{self.enable_password}\n")
                    time.sleep(1)
                    password_response = self._read_available()
                    self._debug_print(f"Password response: {repr(password_response)}", "RECV")
                    available_output += password_response
                else:
                    raise ConnectionError("Device requires enable password but none provided")
            
            # Test if we're now in privileged mode by trying a privileged command
            try:
                # Try a simple privileged command that should work
                self._debug_print("Testing privilege with 'show privilege'", "SEND")
                test_result = self._send_command("show privilege")
                self._debug_print(f"Show privilege result: {repr(test_result)}", "RECV")
                
                # If the command worked and shows privilege level 15, we're good
                if "privilege level 15" in test_result.lower() or "current privilege level is 15" in test_result.lower():
                    self._debug_print("Successfully entered privileged mode (level 15)", "SUCCESS")
                    self.privileged = True
                    return True
                
                # Alternative check: try to see current prompt
                self._debug_print("Testing current prompt", "SEND")
                prompt_test = self._send_command("")  # Empty command to get prompt
                self._debug_print(f"Prompt test result: {repr(prompt_test)}", "RECV")
                if prompt_test.strip().endswith('#'):
                    self._debug_print("Successfully entered privileged mode (# prompt)", "SUCCESS")
                    self.privileged = True
                    return True
                    
                # If we get here, enable mode probably failed
                self._debug_print("Enable mode verification failed", "ERROR")
                return False
                    
            except Exception as test_e:
                # If show privilege fails, we might not be in enable mode
                return False
                
        except Exception as e:
            raise ConnectionError(f"Failed to enter enable mode: {str(e)}")
    
    def send_command(self, command: str, expect_prompt: bool = True) -> str:
        """Send a command and return the output."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        
        return self._send_command(command, expect_prompt)
    
    def send_config_commands(self, commands: List[str]) -> Dict[str, str]:
        """Send configuration commands and return results. Stays in config mode."""
        if not self.connected:
            raise ConnectionError("Not connected to device")
        if not self.privileged:
            raise ConnectionError("Must be in privileged mode for configuration commands")
        
        results = {}
        
        # Enter config mode only if not already in it
        if not self.in_config_mode:
            self._debug_print("Entering configuration mode", "CONFIG")
            config_output = self._send_command("configure terminal")
            if "config" not in config_output.lower():
                raise ConnectionError("Failed to enter configuration mode")
            self.in_config_mode = True
        
        # Execute commands in config mode
        for command in commands:
            if command.strip():
                self._debug_print(f"Executing config command: {command.strip()}", "CONFIG")
                output = self._send_command(command.strip())
                results[command] = output
                
                # Check for errors
                if self._has_config_error(output):
                    raise ValueError(f"Configuration error for command '{command}': {output}")
                
                # Check if command exits config mode (like 'end', 'exit')
                if command.strip().lower() in ['end', 'exit']:
                    self.in_config_mode = False
                    self._debug_print("Exited configuration mode", "CONFIG")
        
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
            self._debug_print(f"Sending command: '{command}'", "SEND")
            self.shell.send(f"{command}\n")
        
        if expect_prompt:
            output = self._read_until_prompt()
            self._debug_print(f"Command output: {repr(output)}", "RECV")
            return output
        else:
            time.sleep(1)
            output = self._read_available()
            self._debug_print(f"Available output: {repr(output)}", "RECV")
            return output
    
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
        
        self._debug_print(f"Looking for prompt, timeout={timeout}s", "DEBUG")
        
        while time.time() - start_time < timeout:
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                output += chunk
                self._debug_print(f"Received chunk: {repr(chunk)}", "RAW")
                
                # Handle more prompts
                if "--More--" in chunk:
                    self.shell.send(" ")  # Space to continue
                    continue
                
                # Check for command prompt
                lines = output.split('\n')
                if lines:
                    last_line = lines[-1].strip()
                    self._debug_print(f"Checking last line: {repr(last_line)}", "DEBUG")
                    for i, pattern in enumerate(prompt_patterns):
                        if re.search(pattern, last_line):
                            self._debug_print(f"Matched pattern {i}: {pattern}", "SUCCESS")
                            return self._clean_output(output)
            
            time.sleep(0.1)
        
        self._debug_print(f"Timeout! Full output: {repr(output)}", "ERROR")
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
        self.debug_mode = False
    
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
                    enable_password=enable_password,
                    debug_mode=self.debug_mode
                )
                
                connector.connect()
                
                # Try to enter enable mode only if not already in privileged mode
                if not connector.privileged:
                    try:
                        success = connector.enter_enable_mode()
                        if success:
                            print(f"Successfully entered privileged mode on {device.name}")
                        else:
                            print(f"Warning: Could not enter privileged mode on {device.name}")
                    except Exception as e:
                        # If enable mode fails, log it but continue
                        print(f"Warning: Enable mode failed on {device.name}: {str(e)}")
                        connector.privileged = False
                else:
                    print(f"Device {device.name} already in privileged mode")
                
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