"""Inventory management for network devices."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml


def _validate_ip_address(ip_address: str) -> str:
    """Validate IP address format."""
    # Basic IP address validation (IPv4)
    ip_pattern = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    if not ip_pattern.match(ip_address) and not ip_address.replace('.', '').replace('-', '').isalnum():
        raise ValueError(f"Invalid IP address or hostname format: {ip_address}")
    return ip_address


class Device:
    """Network device model."""
    
    def __init__(
        self,
        name: str,
        ip_address: str,
        model: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None
    ):
        self.name = name
        self.ip_address = _validate_ip_address(ip_address)
        self.model = model
        self.site = site
        self.role = role
    
    def __repr__(self) -> str:
        return f"Device(name='{self.name}', ip_address='{self.ip_address}')"


class Inventory:
    """Device inventory management."""
    
    def __init__(self):
        self.devices: Dict[str, Device] = {}
    
    def load_yaml(self, file_path: Union[str, Path]) -> None:
        """Load devices from YAML file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Inventory file not found: {file_path}")
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict) or 'devices' not in data:
            raise ValueError("YAML file must contain 'devices' key")
        
        devices_data = data['devices']
        if not isinstance(devices_data, list):
            raise ValueError("'devices' must be a list")
        
        for device_data in devices_data:
            device = Device(
                name=device_data['name'],
                ip_address=device_data['ip_address'],
                model=device_data.get('model'),
                site=device_data.get('site'),
                role=device_data.get('role')
            )
            if device.name in self.devices:
                raise ValueError(f"Duplicate device name: {device.name}")
            self.devices[device.name] = device
    
    def load_txt(self, file_path: Union[str, Path]) -> None:
        """Load devices from text file (one IP per line or IP,name format)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Inventory file not found: {file_path}")
        
        with open(path, 'r') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 1:
                # Just IP address
                ip_address = parts[0]
                name = ip_address
            elif len(parts) >= 2:
                # IP,name or IP,name,model,site,role format
                ip_address = parts[0]
                name = parts[1]
                model = parts[2] if len(parts) > 2 and parts[2] else None
                site = parts[3] if len(parts) > 3 and parts[3] else None
                role = parts[4] if len(parts) > 4 and parts[4] else None
            else:
                continue
            
            try:
                device_data = {'name': name, 'ip_address': ip_address}
                if len(parts) > 2:
                    if len(parts) > 2 and parts[2]:
                        device_data['model'] = parts[2]
                    if len(parts) > 3 and parts[3]:
                        device_data['site'] = parts[3]
                    if len(parts) > 4 and parts[4]:
                        device_data['role'] = parts[4]
                
                device = Device(**device_data)
                if device.name in self.devices:
                    raise ValueError(f"Duplicate device name: {device.name} at line {line_num}")
                self.devices[device.name] = device
            except ValueError as e:
                raise ValueError(f"Error parsing line {line_num}: {e}")
    
    def add_device(self, device: Device) -> None:
        """Add a single device to inventory."""
        if device.name in self.devices:
            raise ValueError(f"Device {device.name} already exists in inventory")
        self.devices[device.name] = device
    
    def remove_device(self, name: str) -> None:
        """Remove device from inventory."""
        if name not in self.devices:
            raise ValueError(f"Device {name} not found in inventory")
        del self.devices[name]
    
    def get_device(self, name: str) -> Optional[Device]:
        """Get device by name."""
        return self.devices.get(name)
    
    def get_all_devices(self) -> List[Device]:
        """Get all devices."""
        return list(self.devices.values())
    
    def filter_devices(
        self, 
        model: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None,
        name_pattern: Optional[str] = None
    ) -> List[Device]:
        """Filter devices by attributes."""
        filtered_devices = []
        
        for device in self.devices.values():
            if model and device.model != model:
                continue
            if site and device.site != site:
                continue
            if role and device.role != role:
                continue
            if name_pattern and not re.search(name_pattern, device.name, re.IGNORECASE):
                continue
            
            filtered_devices.append(device)
        
        return filtered_devices
    
    def get_unique_values(self, attribute: str) -> List[str]:
        """Get unique values for a given attribute."""
        values = set()
        for device in self.devices.values():
            value = getattr(device, attribute, None)
            if value:
                values.add(value)
        return sorted(list(values))
    
    def validate_reachability(self) -> Dict[str, bool]:
        """Validate device reachability (basic ping test)."""
        import subprocess
        
        results = {}
        for device in self.devices.values():
            try:
                # Basic ping test (1 packet, 2 second timeout)
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '2', device.ip_address],
                    capture_output=True,
                    timeout=5
                )
                results[device.name] = result.returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                results[device.name] = False
        
        return results