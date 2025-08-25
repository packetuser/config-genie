"""Interactive CLI session for Config-Genie."""

import cmd
import getpass
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import termios
    import tty
    HAS_TERMIOS = True
except ImportError:
    # Windows doesn't have termios
    HAS_TERMIOS = False

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

from .inventory import Inventory, Device
from .connector import ConnectionManager


# Create console with minimal padding and consistent formatting
console = Console(
    width=None,  # Use terminal width
    legacy_windows=False,
    force_terminal=True,
    _environ=None
)

# Simple color helper functions
def white(text: str) -> str:
    """White text for primary messages."""
    return f"\033[37m{text}\033[0m"

def grey(text: str) -> str:
    """Grey text for secondary messages."""
    return f"\033[90m{text}\033[0m"

def cyan(text: str) -> str:
    """Cyan text for status and info messages."""
    return f"\033[36m{text}\033[0m"

def red(text: str) -> str:
    """Red text for errors only."""
    return f"\033[31m{text}\033[0m"


class InteractiveSession(cmd.Cmd):
    """Interactive command-line session for Config-Genie."""
    
    def __init__(self, inventory_path: Optional[str] = None, dry_run: bool = False, verbose: bool = False):
        super().__init__()
        self.prompt = "(config-genie) "
        self.intro = None  # We'll handle welcome message separately
        
        self.inventory_path = inventory_path
        self.dry_run = dry_run
        self.verbose = verbose
        self.debug_mode = False  # New debug mode flag
        
        self.inventory = Inventory()
        self.connection_manager = ConnectionManager()
        self.selected_devices: List[Device] = []
        self.session_history: List[Dict[str, Any]] = []
        
        # Load inventory if provided
        if inventory_path:
            self._load_inventory(inventory_path)
        else:
            # Try to auto-load devices.yaml from various locations
            import os
            potential_paths = [
                'devices.yaml',  # Current directory
                'config-genie/devices.yaml',  # config-genie subdirectory
                os.path.expanduser('~/config-genie/devices.yaml')  # Home directory
            ]
            
            for path in potential_paths:
                if os.path.exists(path):
                    try:
                        self.inventory.load_yaml(path)
                        console.print(f"[green]✓ Auto-loaded {len(self.inventory.devices)} devices from {path}[/green]")
                        break
                    except Exception as e:
                        console.print(f"[yellow]⚠ Could not auto-load {path}: {e}[/yellow]")
    
    def run(self) -> None:
        """Start the interactive session."""
        console.print("\n[bold blue]Interactive Mode[/bold blue]")
        console.print("Type 'help' for available commands or 'quit' to exit.")
        console.print("[dim]Press '?' after typing a command for instant context help.[/dim]\n")
        
        try:
            # Re-enable custom cmdloop for instant help, with better state management
            self.cmdloop_with_instant_help()
        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'quit' to exit.[/yellow]")
        
        console.print("\n[green]Goodbye![/green]")
        self._cleanup()
    
    def parseline(self, line: str) -> tuple:
        """Override parseline to handle '?' syntax for context help."""
        line = line.strip()
        if line.endswith(' ?'):
            # Remove the '?' and show context help
            command_line = line[:-2].strip()
            parts = command_line.split()
            if parts:
                command = parts[0]
                args = ' '.join(parts[1:]) if len(parts) > 1 else ''
                self._show_context_help(command, args)
                # Return None values to indicate the line was handled
                return None, None, None
        return super().parseline(line)
    
    def do_help(self, arg: str) -> None:
        """Show help for commands."""
        if not arg:
            console.print(Panel.fit(
                "[bold white]Available Commands:[/bold white]\n\n"
                "[white]inventory[/white] - Load and manage device inventory\n"
                "[white]devices[/white] - List and filter devices\n"
                "[white]select[/white] - Select devices for operations\n"
                "[white]connect[/white] - Connect to selected devices\n"
                "[white]execute[/white] - Execute commands on connected devices\n"
                "[white]templates[/white] - Manage configuration templates\n"
                "[white]history[/white] - Show session history\n"
                "[white]status[/white] - Show current session status\n"
                "[white]debug[/white] - Toggle debug mode for SSH communication\n"
                "[white]quit[/white] - Exit the session",
                title="Help"
            ))
        else:
            # Show help for specific command
            method = getattr(self, f'do_{arg}', None)
            if method and method.__doc__:
                console.print(f"[bold]{arg}:[/bold] {method.__doc__}")
            else:
                console.print(f"[red]No help available for '{arg}'[/red]")
    
    def default(self, line: str) -> None:
        """Handle unknown commands, including '?' for help."""
        if line.strip() == '?':
            self.do_help('')
        else:
            console.print(f"[red]Unknown command: {line}[/red]")
            console.print("Type 'help' or '?' for available commands.")
    
    def do_inventory(self, arg: str) -> None:
        """Load inventory file. Usage: inventory [path]"""
        if not arg:
            if self.inventory_path:
                console.print(f"[green]Current inventory:[/green] {self.inventory_path}")
            else:
                console.print("[yellow]No inventory loaded.[/yellow]")
                path = input("Enter inventory file path: ").strip()
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
                str(device.name),
                str(device.ip_address),
                str(device.model or "-"),
                str(device.site or "-"),
                str(device.role or "-"),
                str(status)
            )
        
        console.print(table)
    
    def do_select(self, arg: str) -> None:
        """Select devices for operations. Usage: select [all|none|device1,device2|filter]"""
        if not arg:
            # Show current selection
            if self.selected_devices:
                print(cyan(f"Selected devices: {', '.join(str(d.name) for d in self.selected_devices)}"))
            else:
                print(grey("No devices selected."))
            return
        
        if arg == "all":
            self.selected_devices = self.inventory.get_all_devices()
            print(cyan(f"Selected all {len(self.selected_devices)} devices"))
        
        elif arg == "none":
            self.selected_devices = []
            print(cyan("Cleared device selection"))
        
        elif ',' in arg:
            # Select specific devices by name
            device_names = [name.strip() for name in arg.split(',')]
            self.selected_devices = []
            
            for name in device_names:
                device = self.inventory.get_device(name)
                if device:
                    self.selected_devices.append(device)
                else:
                    print(grey(f"Device not found: {name}"))
            
            print(cyan(f"Selected {len(self.selected_devices)} devices"))
        
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
                    print(red(f"Unknown filter: {arg}"))
                    return
                
                print(cyan(f"Selected {len(self.selected_devices)} devices matching {arg}"))
            else:
                print(red(f"Invalid selection: {arg}"))
    
    def do_connect(self, arg: str) -> None:
        """Connect to selected devices. Usage: connect"""
        if not self.selected_devices:
            print(grey("No devices selected. Use 'select' command first."))
            return
        
        # Get credentials
        if not self.connection_manager.credentials:
            print(cyan("Enter device credentials:"))
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            # Note: Enable password disabled for current environment - uncomment if needed
            # enable_password = Prompt.ask("Enable password (optional)", password=True, default="")
            
            self.connection_manager.set_credentials(
                username, 
                password, 
                None  # No enable password for current environment
                # enable_password if enable_password else None  # Uncomment if enable password needed
            )
        
        # Connect to devices
        print(cyan(f"Connecting to {len(self.selected_devices)} devices..."))
        
        connected = 0
        for device in self.selected_devices:
            try:
                print(cyan(f"Connecting to {device.name}..."), end=" ")
                self.connection_manager.connect_device(device)
                print(white("✓"))
                connected += 1
            except Exception as e:
                print(red(f"✗ {str(e)}"))
        
        print(white(f"Connected to {connected}/{len(self.selected_devices)} devices"))
    
    def do_execute(self, arg: str) -> None:
        """Execute command on connected devices. Usage: execute <command>"""
        if not arg:
            print(red("Please provide a command to execute"))
            return
        
        if not self.selected_devices:
            print(grey("No devices selected."))
            return
        
        # Check connections
        connected_devices = []
        for device in self.selected_devices:
            conn = self.connection_manager.get_connection(device.name)
            if conn and conn.connected:
                connected_devices.append(device)
        
        # Check if we have connected devices
        if not connected_devices:
            print(grey("No connected devices. Use 'connect' command first."))
            return
        
        # Confirm execution unless it's a show command
        is_show_command = arg.strip().lower().startswith(('show', 'display'))
        
        if not is_show_command and not self.dry_run:
            # Use plain input to avoid Rich console padding issues
            response = input(f"Execute '{arg}' on {len(connected_devices)} devices? [y/n]: ").lower().strip()
            if response not in ['y', 'yes']:
                print(grey("Command execution cancelled."))
                return
        
        # Execute command
        print(cyan(f"Executing: {arg}"))
        if self.dry_run:
            console.print("[blue]DRY RUN MODE - Command would be executed on:[/blue]")
            for device in connected_devices:
                console.print(f"  • {device.name} ({device.ip_address})")
        else:
            # Execute command using execution manager
            from .execution import ExecutionManager
            execution_manager = ExecutionManager(self.connection_manager)
            
            plan = execution_manager.create_execution_plan(
                devices=connected_devices,
                commands=[arg],
                dry_run=False,
                validate=False  # Skip validation for single commands
            )
            
            results = execution_manager.execute_plan(plan)
            
            # Display results
            for device_name, result in results.items():
                console.print(f"\n[bold cyan]═══ {device_name} ═══[/bold cyan]")
                
                if result.status.value == "success":
                    if result.output and result.output.strip():
                        # Print raw output to stdout
                        print(result.output)
                    else:
                        console.print("[green]✓ Command completed successfully (no output)[/green]")
                else:
                    console.print(f"[red]✗ Command failed: {result.error}[/red]")
                
                if result.execution_time:
                    console.print(f"[dim]Execution time: {result.execution_time:.2f}s[/dim]")
            
            # Ensure clean terminal state after execution
            sys.stdout.flush()
        
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
            devices_str = ", ".join(str(d) for d in entry['devices'][:3])
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
    

    def _show_context_help(self, command: str, args: str) -> None:
        """Show context-sensitive help for commands."""
        if command == "connect":
            console.print(Panel.fit(
                "[bold]connect[/bold] - Connect to selected devices\n\n"
                "[cyan]Usage:[/cyan] connect\n\n"
                "[yellow]Prerequisites:[/yellow]\n"
                "• Devices must be selected first (use 'select' command)\n"
                "• Will prompt for credentials if not already provided\n\n"
                "[yellow]Examples:[/yellow]\n"
                "connect\n\n"
                "[dim]Note: This command connects to all currently selected devices[/dim]",
                title="Context Help"
            ))
        
        elif command == "select":
            console.print(Panel(
                "[bold white]select[/bold white] - [white]Select devices for operations[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]select                     # Show current selection\n"
                "select all                 # Select all devices\n"
                "select none                # Clear selection\n"
                "select device1,device2     # Select specific devices\n"
                "select model=2960X         # Select by model\n"
                "select site=100McCaul      # Select by site\n"
                "select role=switch         # Select by role[/white]\n\n"
                "[cyan]Available filters:[/cyan]\n"
                "[white]• model=<model_name>\n"
                "• site=<site_name>\n"
                "• role=<role_name>\n"
                "• name=<pattern>[/white]",
                title="Context Help",
                width=60
            ))
        
        elif command == "execute":
            console.print(Panel.fit(
                "[bold white]execute[/bold white] - [white]Execute command on connected devices[/white]\n\n"
                "[cyan]Usage:[/cyan] [white]execute <command>[/white]\n\n"
                "[cyan]Prerequisites:[/cyan]\n"
                "[white]• Devices must be selected and connected\n"
                "• Non-show commands require confirmation[/white]\n\n"
                "[cyan]Common commands:[/cyan]\n"
                "[white]show version\n"
                "show running-config\n"
                "show ip interface brief\n"
                "show vlan brief\n"
                "show interface status[/white]\n\n"
                "[dim]Note: Show commands execute immediately, config changes require confirmation[/dim]",
                title="Context Help"
            ))
        
        elif command == "devices":
            console.print(Panel(
                "[bold white]devices[/bold white] - [white]List and filter devices[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]devices                    # List all devices\n"
                "devices model=2960X        # Filter by model\n"
                "devices site=100McCaul     # Filter by site\n"
                "devices role=switch        # Filter by role\n"
                "devices name=sw-           # Filter by name pattern[/white]\n\n"
                "[cyan]Available filters:[/cyan]\n"
                "[white]• model=<model_name>\n"
                "• site=<site_name>\n"
                "• role=<role_name>\n"
                "• name=<pattern>[/white]",
                title="Context Help",
                width=60
            ))
        
        elif command == "inventory":
            console.print(Panel(
                "[bold white]inventory[/bold white] - [white]Load and manage device inventory[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]inventory                  # Show current inventory status\n"
                "inventory <path>           # Load inventory from file[/white]\n\n"
                "[cyan]Supported formats:[/cyan]\n"
                "[white]• YAML files (.yml, .yaml)\n"
                "• Text files (.txt)[/white]\n\n"
                "[cyan]Auto-load locations:[/cyan]\n"
                "[white]• ./devices.yaml\n"
                "• ./config-genie/devices.yaml\n"
                "• ~/config-genie/devices.yaml[/white]",
                title="Context Help",
                width=60
            ))
        
        elif command == "templates":
            console.print(Panel.fit(
                "[bold]templates[/bold] - Manage configuration templates\n\n"
                "[cyan]Usage:[/cyan]\n"
                "templates list           # List available templates\n"
                "templates create         # Create new template\n"
                "templates edit <name>    # Edit existing template\n"
                "templates delete <name>  # Delete template\n\n"
                "[yellow]Status:[/yellow] Template management system coming soon",
                title="Context Help"
            ))
        
        elif command == "history":
            console.print(Panel.fit(
                "[bold]history[/bold] - Show session command history\n\n"
                "[cyan]Usage:[/cyan] history\n\n"
                "Shows all commands executed in current session with:\n"
                "• Command text\n"
                "• Target devices\n"
                "• Execution mode (DRY RUN or EXECUTE)",
                title="Context Help"
            ))
        
        elif command == "status":
            console.print(Panel.fit(
                "[bold]status[/bold] - Show current session status\n\n"
                "[cyan]Usage:[/cyan] status\n\n"
                "Displays current session information:\n"
                "• Inventory status\n"
                "• Device counts (loaded/selected/connected)\n"
                "• Execution mode\n"
                "• Commands executed count",
                title="Context Help"
            ))
        
        else:
            console.print(f"[yellow]No context help available for '{command}'[/yellow]")
            console.print("Use 'help' to see all available commands")

    def _cleanup(self) -> None:
        """Clean up session resources."""
        self.connection_manager.disconnect_all()
    
    def cmdloop_with_instant_help(self) -> None:
        """Custom command loop that shows help instantly when '?' is pressed."""
        if self.intro:
            self.stdout.write(str(self.intro) + "\n")
        
        stop = None
        while not stop:
            if self.cmdqueue:
                line = self.cmdqueue.pop(0)
            else:
                try:
                    line = self._input_with_instant_help()
                except EOFError:
                    line = 'EOF'
                except KeyboardInterrupt:
                    print("^C")
                    continue  # Skip command execution and go back to prompt
            
            stop = self.onecmd(line)
            stop = self.onecmd_finish(line, stop)
    
    def onecmd_finish(self, line: str, stop: bool) -> bool:
        """Hook called after each command. Override for custom behavior."""
        return stop
    
    def _input_with_instant_help(self) -> str:
        """Custom input handler that shows help when '?' is pressed."""
        if not sys.stdin.isatty() or not HAS_TERMIOS:
            # Fall back to regular input if not in a terminal or on Windows
            return input(self.prompt)
        
        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        
        try:
            # Set terminal to raw mode for character-by-character input
            tty.setraw(sys.stdin.fileno())
            
            # Use raw stdout for better terminal control
            sys.stdout.write(self.prompt)
            sys.stdout.flush()
            
            input_buffer = []
            cursor_pos = 0
            
            while True:
                char = sys.stdin.read(1)
                
                # Handle special characters
                if char == '\r' or char == '\n':  # Enter
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    return ''.join(input_buffer)
                
                elif char == '\x7f' or char == '\x08':  # Backspace/Delete
                    if cursor_pos > 0 and input_buffer:
                        input_buffer.pop(cursor_pos - 1)
                        cursor_pos -= 1
                        # Clear line and redraw
                        sys.stdout.write('\r\033[K')  # Move to start and clear line
                        sys.stdout.write(self.prompt + ''.join(input_buffer))
                        sys.stdout.flush()
                
                elif char == '\x03':  # Ctrl+C
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    raise KeyboardInterrupt
                
                elif char == '\x04':  # Ctrl+D (EOF)
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    raise EOFError
                
                elif char == '\t':  # Tab for autocomplete
                    # Handle autocomplete
                    current_line = ''.join(input_buffer)
                    completions = self._get_completions(current_line)
                    
                    if completions:
                        if len(completions) == 1:
                            # Single completion - complete it
                            completion = completions[0]
                            # Find the word being completed
                            parts = current_line.split()
                            if parts:
                                last_word = parts[-1] if current_line.endswith(' ') else parts[-1] if parts else ''
                                if not current_line.endswith(' '):
                                    # Replace the last partial word
                                    prefix = ' '.join(parts[:-1])
                                    if prefix:
                                        new_line = prefix + ' ' + completion
                                    else:
                                        new_line = completion
                                else:
                                    new_line = current_line + completion
                            else:
                                new_line = completion
                            
                            # Update buffer
                            input_buffer = list(new_line)
                            cursor_pos = len(input_buffer)
                            
                            # Redraw line
                            sys.stdout.write('\r\033[K')
                            sys.stdout.write(self.prompt + new_line)
                            sys.stdout.flush()
                        else:
                            # Multiple completions - show them
                            sys.stdout.write('\n')
                            # Show completions in columns
                            import shutil
                            term_width = shutil.get_terminal_size().columns
                            max_width = max(len(comp) for comp in completions)
                            cols = max(1, term_width // (max_width + 2))
                            
                            for i, comp in enumerate(completions):
                                if i > 0 and i % cols == 0:
                                    sys.stdout.write('\n')
                                sys.stdout.write(comp.ljust(max_width + 2))
                            sys.stdout.write('\n')
                            
                            # Redraw prompt and current input
                            sys.stdout.write(self.prompt + ''.join(input_buffer))
                            sys.stdout.flush()
                
                elif char == '?':
                    # Show instant help
                    command_line = ''.join(input_buffer).strip()
                    # Move to start of line and clear it
                    sys.stdout.write('\r\033[K')
                    sys.stdout.flush()
                    
                    # Temporarily restore terminal settings for Rich output
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    
                    try:
                        if command_line:
                            parts = command_line.split()
                            command = parts[0]
                            args = ' '.join(parts[1:]) if len(parts) > 1 else ''
                            self._show_context_help(command, args)
                        else:
                            # No command typed, show general help
                            self.do_help('')
                    finally:
                        # Return to raw mode
                        tty.setraw(sys.stdin.fileno())
                    
                    # Ensure clean line before redrawing prompt
                    sys.stdout.write('\r\033[K')
                    sys.stdout.write(self.prompt + ''.join(input_buffer))
                    sys.stdout.flush()
                
                elif char.isprintable():
                    # Add printable character to buffer
                    input_buffer.insert(cursor_pos, char)
                    cursor_pos += 1
                    sys.stdout.write(char)
                    sys.stdout.flush()
                
                # Handle escape sequences for arrow keys (optional enhancement)
                elif char == '\x1b':  # ESC sequence
                    next_char = sys.stdin.read(1)
                    if next_char == '[':
                        arrow_char = sys.stdin.read(1)
                        # Could handle arrow keys here for cursor movement
                        pass
        
        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def _get_completions(self, line: str) -> List[str]:
        """Get completions for the current line using cmd.Cmd's completion system."""
        # Parse the line to determine command and arguments
        parts = line.strip().split()
        if not parts:
            # No command typed, return available commands
            return [name[3:] for name in dir(self) if name.startswith('do_') and len(name) > 3]
        
        command = parts[0]
        if len(parts) == 1 and not line.endswith(' '):
            # Still completing the command name
            commands = [name[3:] for name in dir(self) if name.startswith('do_') and len(name) > 3]
            return [cmd for cmd in commands if cmd.startswith(command)]
        
        # Completing arguments for the command
        # Use the existing complete_* methods
        complete_method = getattr(self, f'complete_{command}', None)
        if complete_method:
            # Get the text being completed (last word or empty string)
            if line.endswith(' '):
                text = ''
                begidx = len(line)
            else:
                text = parts[-1]
                begidx = len(line) - len(text)
            
            endidx = len(line)
            return complete_method(text, line, begidx, endidx)
        
        return []
    
    # Autocomplete methods
    def complete_devices(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for devices command filters."""
        options = ['model=', 'site=', 'role=', 'name=']
        return [option for option in options if option.startswith(text)]
    
    def complete_select(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for select command."""
        # Base options
        options = ['all', 'none']
        
        # Add device names (ensure they're strings)
        device_names = [str(device.name) for device in self.inventory.get_all_devices()]
        options.extend(device_names)
        
        # Add filter options
        if '=' in text or any('=' in part for part in line.split()):
            # Already in filter mode, suggest values
            if text.startswith('model='):
                models = set(device.model for device in self.inventory.get_all_devices() if device.model)
                return [f"model={model}" for model in models if f"model={model}".startswith(text)]
            elif text.startswith('site='):
                sites = set(device.site for device in self.inventory.get_all_devices() if device.site)
                return [f"site={site}" for site in sites if f"site={site}".startswith(text)]
            elif text.startswith('role='):
                roles = set(device.role for device in self.inventory.get_all_devices() if device.role)
                return [f"role={role}" for role in roles if f"role={role}".startswith(text)]
        else:
            # Add filter prefixes
            options.extend(['model=', 'site=', 'role='])
        
        return [option for option in options if option.startswith(text)]
    
    def complete_inventory(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for inventory command with file paths."""
        import os
        import glob
        
        # Get the directory and partial filename
        if os.path.sep in text:
            directory = os.path.dirname(text)
            partial = os.path.basename(text)
        else:
            directory = '.'
            partial = text
        
        try:
            # Get matching files
            pattern = os.path.join(directory, partial + '*')
            matches = glob.glob(pattern)
            
            # Filter for relevant file extensions
            relevant_files = []
            for match in matches:
                if os.path.isdir(match):
                    relevant_files.append(match + os.path.sep)
                elif match.endswith(('.yml', '.yaml', '.txt')):
                    relevant_files.append(match)
            
            return relevant_files
        except:
            return []
    
    def complete_execute(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for execute command with common Cisco commands."""
        cisco_commands = [
            'show version',
            'show running-config',
            'show ip interface brief',
            'show vlan brief',
            'show interface status',
            'show mac address-table',
            'show cdp neighbors',
            'show spanning-tree',
            'show ip route',
            'show interface',
            'show logging',
            'show clock',
            'show users',
            'enable',
            'configure terminal',
            'interface',
            'vlan',
            'ip route',
            'no shutdown',
            'shutdown',
            'description',
            'switchport mode access',
            'switchport mode trunk',
            'switchport access vlan',
            'switchport trunk allowed vlan'
        ]
        
        return [cmd for cmd in cisco_commands if cmd.startswith(text)]
    
    def do_debug(self, arg: str) -> None:
        """Toggle debug mode. Usage: debug [on|off]"""
        if not arg:
            # Show current status
            status = "ON" if self.debug_mode else "OFF"
            print(cyan(f"Debug mode is currently {status}"))
            return
        
        arg = arg.lower().strip()
        if arg in ['on', 'true', '1', 'yes']:
            self.debug_mode = True
            # Enable debug on connection manager too
            self.connection_manager.debug_mode = True
            print(cyan("Debug mode enabled - SSH communication will be shown"))
        elif arg in ['off', 'false', '0', 'no']:
            self.debug_mode = False
            # Disable debug on connection manager too
            self.connection_manager.debug_mode = False
            print(grey("Debug mode disabled"))
        else:
            print(red("Usage: debug [on|off]"))

    def do_quit(self, line: str) -> bool:
        """Exit the session."""
        return True
    
    def do_exit(self, line: str) -> bool:
        """Exit the session."""
        return True
    
    def do_q(self, line: str) -> bool:
        """Exit the session."""
        return True
    
    def do_EOF(self, line: str) -> bool:
        """Handle Ctrl+D to exit."""
        console.print()
        return True