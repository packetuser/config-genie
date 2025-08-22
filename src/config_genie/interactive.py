"""Interactive CLI session for Config-Genie."""

import cmd
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

from .inventory import Inventory, Device
from .connector import ConnectionManager


console = Console()


class InteractiveSession(cmd.Cmd):
    """Interactive command-line session for Config-Genie."""
    
    def __init__(self, inventory_path: Optional[str] = None, dry_run: bool = False, verbose: bool = False):
        super().__init__()
        self.prompt = "[cyan](config-genie)[/cyan] "
        self.intro = None  # We'll handle welcome message separately
        
        self.inventory_path = inventory_path
        self.dry_run = dry_run
        self.verbose = verbose
        
        self.inventory = Inventory()
        self.connection_manager = ConnectionManager()
        self.selected_devices: List[Device] = []
        self.session_history: List[Dict[str, Any]] = []
        
        # Load inventory if provided
        if inventory_path:
            self._load_inventory(inventory_path)
    
    def run(self) -> None:
        """Start the interactive session."""
        console.print("\n[bold blue]Interactive Mode[/bold blue]")
        console.print("Type 'help' for available commands or 'quit' to exit.\n")
        
        # Override cmd's cmdloop to use rich for prompting
        while True:
            try:
                line = Prompt.ask(self.prompt, console=console)
                if line.lower() in ['quit', 'exit', 'q']:
                    break
                elif line.strip():
                    self.onecmd(line)
            except KeyboardInterrupt:
                console.print("\n[yellow]Use 'quit' to exit.[/yellow]")
            except EOFError:
                break
        
        console.print("\n[green]Goodbye![/green]")
        self._cleanup()
    
    def do_help(self, arg: str) -> None:
        """Show help for commands."""
        if not arg:
            console.print(Panel.fit(
                "[bold]Available Commands:[/bold]\n\n"
                "[cyan]inventory[/cyan] - Load and manage device inventory\n"
                "[cyan]devices[/cyan] - List and filter devices\n"
                "[cyan]select[/cyan] - Select devices for operations\n"
                "[cyan]connect[/cyan] - Connect to selected devices\n"
                "[cyan]execute[/cyan] - Execute commands on connected devices\n"
                "[cyan]templates[/cyan] - Manage configuration templates\n"
                "[cyan]history[/cyan] - Show session history\n"
                "[cyan]status[/cyan] - Show current session status\n"
                "[cyan]quit[/cyan] - Exit the session",
                title="Help"
            ))
        else:
            # Show help for specific command
            method = getattr(self, f'do_{arg}', None)
            if method and method.__doc__:
                console.print(f"[bold]{arg}:[/bold] {method.__doc__}")
            else:
                console.print(f"[red]No help available for '{arg}'[/red]")
    
    def do_inventory(self, arg: str) -> None:
        """Load inventory file. Usage: inventory [path]"""
        if not arg:
            if self.inventory_path:
                console.print(f"[green]Current inventory:[/green] {self.inventory_path}")
            else:
                console.print("[yellow]No inventory loaded.[/yellow]")
                path = Prompt.ask("Enter inventory file path")
                if path:
                    self._load_inventory(path)
        else:
            self._load_inventory(arg)
    
    def do_devices(self, arg: str) -> None:
        """List and filter devices. Usage: devices [filter]"""
        devices = self.inventory.get_all_devices()
        if not devices:
            console.print("[yellow]No devices in inventory. Load an inventory file first.[/yellow]")
            return
        
        # Apply filters if provided
        if arg:
            # Simple filter parsing (e.g., "model=2960X" or "site=HQ")
            if '=' in arg:
                key, value = arg.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'model':
                    devices = self.inventory.filter_devices(model=value)
                elif key == 'site':
                    devices = self.inventory.filter_devices(site=value)
                elif key == 'role':
                    devices = self.inventory.filter_devices(role=value)
                elif key == 'name':
                    devices = self.inventory.filter_devices(name_pattern=value)
                else:
                    console.print(f"[red]Unknown filter key: {key}[/red]")
                    return
        
        # Display devices in table
        table = Table(title=f"Devices ({len(devices)} found)")
        table.add_column("Name", style="cyan")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Site")
        table.add_column("Role")
        table.add_column("Status")
        
        for device in devices:
            # Check if device is selected
            status = "selected" if device in self.selected_devices else "-"
            
            table.add_row(
                device.name,
                device.ip_address,
                device.model or "-",
                device.site or "-",
                device.role or "-",
                status
            )
        
        console.print(table)
    
    def do_select(self, arg: str) -> None:
        """Select devices for operations. Usage: select [all|none|device1,device2|filter]"""
        if not arg:
            # Show current selection
            if self.selected_devices:
                console.print(f"[green]Selected devices:[/green] {', '.join(d.name for d in self.selected_devices)}")
            else:
                console.print("[yellow]No devices selected.[/yellow]")
            return
        
        if arg == "all":
            self.selected_devices = self.inventory.get_all_devices()
            console.print(f"[green]Selected all {len(self.selected_devices)} devices[/green]")
        
        elif arg == "none":
            self.selected_devices = []
            console.print("[green]Cleared device selection[/green]")
        
        elif ',' in arg:
            # Select specific devices by name
            device_names = [name.strip() for name in arg.split(',')]
            self.selected_devices = []
            
            for name in device_names:
                device = self.inventory.get_device(name)
                if device:
                    self.selected_devices.append(device)
                else:
                    console.print(f"[red]Device not found: {name}[/red]")
            
            console.print(f"[green]Selected {len(self.selected_devices)} devices[/green]")
        
        else:
            # Try to parse as filter
            if '=' in arg:
                key, value = arg.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'model':
                    self.selected_devices = self.inventory.filter_devices(model=value)
                elif key == 'site':
                    self.selected_devices = self.inventory.filter_devices(site=value)
                elif key == 'role':
                    self.selected_devices = self.inventory.filter_devices(role=value)
                else:
                    console.print(f"[red]Unknown filter: {arg}[/red]")
                    return
                
                console.print(f"[green]Selected {len(self.selected_devices)} devices matching {arg}[/green]")
            else:
                console.print(f"[red]Invalid selection: {arg}[/red]")
    
    def do_connect(self, arg: str) -> None:
        """Connect to selected devices. Usage: connect"""
        if not self.selected_devices:
            console.print("[yellow]No devices selected. Use 'select' command first.[/yellow]")
            return
        
        # Get credentials
        if not self.connection_manager.credentials:
            console.print("[blue]Enter device credentials:[/blue]")
            username = Prompt.ask("Username")
            password = Prompt.ask("Password", password=True)
            enable_password = Prompt.ask("Enable password (optional)", password=True, default="")
            
            self.connection_manager.set_credentials(
                username, 
                password, 
                enable_password if enable_password else None
            )
        
        # Connect to devices
        console.print(f"[yellow]Connecting to {len(self.selected_devices)} devices...[/yellow]")
        
        connected = 0
        for device in self.selected_devices:
            try:
                console.print(f"Connecting to {device.name}...", end=" ")
                self.connection_manager.connect_device(device)
                console.print("[green]✓[/green]")
                connected += 1
            except Exception as e:
                console.print(f"[red]✗ {str(e)}[/red]")
        
        console.print(f"\n[green]Connected to {connected}/{len(self.selected_devices)} devices[/green]")
    
    def do_execute(self, arg: str) -> None:
        """Execute command on connected devices. Usage: execute <command>"""
        if not arg:
            console.print("[red]Please provide a command to execute[/red]")
            return
        
        if not self.selected_devices:
            console.print("[yellow]No devices selected.[/yellow]")
            return
        
        # Check connections
        connected_devices = []
        for device in self.selected_devices:
            conn = self.connection_manager.get_connection(device.name)
            if conn and conn.connected:
                connected_devices.append(device)
        
        if not connected_devices:
            console.print("[red]No connected devices. Use 'connect' command first.[/red]")
            return
        
        # Confirm execution unless it's a show command
        is_show_command = arg.strip().lower().startswith(('show', 'display'))
        
        if not is_show_command and not self.dry_run:
            if not Confirm.ask(f"Execute '{arg}' on {len(connected_devices)} devices?"):
                console.print("[yellow]Command execution cancelled.[/yellow]")
                return
        
        # Execute command
        console.print(f"[yellow]Executing:[/yellow] {arg}")
        if self.dry_run:
            console.print("[blue]DRY RUN MODE - Command would be executed on:[/blue]")
            for device in connected_devices:
                console.print(f"  • {device.name} ({device.ip_address})")
        else:
            # Placeholder for actual execution
            console.print("[green]✓[/green] Command executed (implementation pending)")
        
        # Record in history
        self.session_history.append({
            'command': arg,
            'devices': [d.name for d in connected_devices],
            'dry_run': self.dry_run,
            'timestamp': None  # Would use datetime in real implementation
        })
    
    def do_templates(self, arg: str) -> None:
        """Manage configuration templates. Usage: templates [list|create|edit|delete]"""
        console.print("[yellow]Template management not implemented yet.[/yellow]")
        console.print("This will be available in the template management system.")
    
    def do_history(self, arg: str) -> None:
        """Show session command history."""
        if not self.session_history:
            console.print("[yellow]No command history.[/yellow]")
            return
        
        table = Table(title="Session History")
        table.add_column("#")
        table.add_column("Command")
        table.add_column("Devices")
        table.add_column("Mode")
        
        for i, entry in enumerate(self.session_history, 1):
            devices_str = ", ".join(entry['devices'][:3])
            if len(entry['devices']) > 3:
                devices_str += f" (+{len(entry['devices']) - 3} more)"
            
            mode = "DRY RUN" if entry['dry_run'] else "EXECUTE"
            
            table.add_row(
                str(i),
                entry['command'],
                devices_str,
                mode
            )
        
        console.print(table)
    
    def do_status(self, arg: str) -> None:
        """Show current session status."""
        console.print(Panel.fit(
            f"[bold]Session Status[/bold]\n\n"
            f"Inventory: {'✓ ' + self.inventory_path if self.inventory_path else '✗ Not loaded'}\n"
            f"Devices loaded: {len(self.inventory.devices)}\n"
            f"Selected devices: {len(self.selected_devices)}\n"
            f"Connected devices: {len(self.connection_manager.connections)}\n"
            f"Mode: {'DRY RUN' if self.dry_run else 'EXECUTE'}\n"
            f"Commands executed: {len(self.session_history)}",
            title="Status"
        ))
    
    def _load_inventory(self, path: str) -> None:
        """Load inventory from file."""
        try:
            inventory_path = Path(path)
            if not inventory_path.exists():
                console.print(f"[red]File not found: {path}[/red]")
                return
            
            if inventory_path.suffix.lower() in ['.yml', '.yaml']:
                self.inventory.load_yaml(path)
            else:
                self.inventory.load_txt(path)
            
            self.inventory_path = path
            device_count = len(self.inventory.devices)
            console.print(f"[green]✓[/green] Loaded {device_count} devices from {path}")
            
        except Exception as e:
            console.print(f"[red]Error loading inventory: {str(e)}[/red]")
    
    def _cleanup(self) -> None:
        """Clean up session resources."""
        self.connection_manager.disconnect_all()