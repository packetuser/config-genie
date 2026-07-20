"""Interactive CLI session for Config-Genie."""

import cmd
import getpass
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Set, Tuple

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
from rich.markup import escape

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
        
        # Command history for up/down arrow functionality
        self.command_history: List[str] = []
        self.history_index: int = -1
        
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
                        self.inventory_path = path  # Set the inventory path for consistent behavior
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
                "[white]inventory[/white] - Load (load/<path>) and list (list) device inventory\n"
                "[white]netbox[/white] - Load device inventory from NetBox\n"
                "[white]connect[/white] - Connect to devices (by name, filter e.g. role=switch, all/none, or 'pick' for an interactive picker)\n"
                "[white]execute[/white] - Execute commands on connected devices\n"
                "[white]exit_config[/white] - Exit configuration mode on devices\n"
                "[white]templates[/white] - Manage configuration templates\n"
                "[white]history[/white] - Show command history (use up/down arrows)\n"
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
        """Load and list device inventory.
        Usage:
          inventory                  # Show current inventory status
          inventory load <path>      # Load inventory from file
          inventory list [filter]    # List/filter loaded devices
          inventory <path>           # Shorthand for 'inventory load <path>'
        """
        if not arg:
            if self.inventory_path:
                console.print(f"[green]Current inventory:[/green] {self.inventory_path}")
            else:
                console.print("[yellow]No inventory loaded.[/yellow]")
                path = input("Enter inventory file path: ").strip()
                if path:
                    self._load_inventory(path)
            return
        
        subcommand, _, rest = arg.partition(' ')
        rest = rest.strip()
        
        if subcommand == 'load':
            if not rest:
                console.print("[red]Usage: inventory load <path>[/red]")
                return
            self._load_inventory(rest)
        elif subcommand == 'list':
            self._list_devices(rest)
        else:
            # Backward-compatible shorthand: 'inventory <path>' loads directly
            self._load_inventory(arg)
    
    def _list_devices(self, arg: str) -> None:
        """List and filter devices. Usage: [filter] where filter is
        model=<name>, site=<name>, role=<name>, or name=<pattern>"""
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
            else:
                console.print(f"[red]Invalid filter: {arg}[/red]")
                return
        
        # Display devices in table
        table = Table(title=f"Devices ({len(devices)} found)")
        table.add_column("Name", style="cyan")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Site")
        table.add_column("Role")
        table.add_column("Connected")
        
        for device in devices:
            conn = self.connection_manager.get_connection(device.name)
            status = "✓" if conn and conn.connected else "-"
            
            table.add_row(
                str(device.name),
                str(device.ip_address),
                str(device.model or "-"),
                str(device.site or "-"),
                str(device.role or "-"),
                str(status)
            )
        
        console.print(table)
    
    def do_netbox(self, arg: str) -> None:
        """Load device inventory from a NetBox instance. Usage: netbox [site=<site>] [role=<role>] [status=<status>] [insecure]"""
        import os
        from .inventory import parse_device_selection

        # Parse optional key=value filters and bare flags from the command line
        filters: Dict[str, str] = {}
        insecure = False
        for token in arg.split():
            if token.lower() in ('insecure', 'no-verify', 'no-verify-ssl'):
                insecure = True
            elif '=' in token:
                key, value = token.split('=', 1)
                filters[key.strip()] = value.strip()

        url = os.environ.get('NETBOX_URL')
        if not url:
            url = Prompt.ask("NetBox URL (e.g. https://netbox.example.com)").strip()
            if not url:
                console.print("[red]NetBox URL is required.[/red]")
                return

        token = os.environ.get('NETBOX_TOKEN')
        if not token:
            token = getpass.getpass("NetBox API token: ").strip()
            if not token:
                console.print("[red]NetBox token is required.[/red]")
                return

        site = filters.get('site')
        role = filters.get('role')
        status = filters.get('status', 'active')

        # By default, only surface devices whose role name contains "switch"
        # (e.g. "Edge Switch", "Access Switch", "core-switch"). Pass role=all
        # to disable this and see every role, or role=<name> for an exact
        # server-side role filter instead.
        role_contains: Optional[str] = None
        if role is None:
            role_contains = "switch"
        elif role.strip().lower() == "all":
            role = None

        # Env var NETBOX_VERIFY_SSL=false (or 0/no/off) also disables verification
        verify_ssl = not insecure
        env_verify = os.environ.get('NETBOX_VERIFY_SSL')
        if env_verify is not None and env_verify.strip().lower() in ('false', '0', 'no', 'off'):
            verify_ssl = False

        if not verify_ssl:
            console.print("[yellow]⚠ SSL certificate verification disabled for this NetBox connection.[/yellow]")

        try:
            console.print("[yellow]Connecting to NetBox...[/yellow]")
            candidates = self.inventory.fetch_netbox_devices(
                url=url, token=token, site=site, role=role, role_contains=role_contains,
                status=status, verify_ssl=verify_ssl
            )
        except (ValueError, ConnectionError) as e:
            console.print(f"[red]Error:[/red] {str(e)}")
            return

        if not candidates:
            console.print("[yellow]No matching devices found in NetBox.[/yellow]")
            return

        table = Table(title=f"NetBox Devices ({len(candidates)} found)")
        table.add_column("#", justify="right")
        table.add_column("Name", style="cyan")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Site")
        table.add_column("Role")

        for i, device in enumerate(candidates, 1):
            table.add_row(
                str(i),
                str(device.name),
                str(device.ip_address),
                str(device.model or "-"),
                str(device.site or "-"),
                str(device.role or "-")
            )

        console.print(table)

        try:
            selection = Prompt.ask(
                "Select devices to import (numbers, ranges like 1-3, names, 'all', or 'none')",
                default="all"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Import cancelled.[/yellow]")
            return

        try:
            indices = parse_device_selection(selection, candidates)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {str(e)}")
            return

        if not indices:
            console.print("[yellow]No devices selected. Nothing imported.[/yellow]")
            return

        for i in indices:
            device = candidates[i]
            self.inventory.devices[device.name] = device

        self.inventory_path = f"netbox:{url}"
        console.print(f"[green]✓[/green] Imported {len(indices)} of {len(candidates)} devices from NetBox")

        try:
            if Confirm.ask("Save this inventory to a local YAML file?", default=False):
                save_path = Prompt.ask("File path", default="devices.yaml").strip()
                if save_path:
                    self._save_inventory_yaml(save_path)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Skipping save.[/yellow]")
    
    def _save_inventory_yaml(self, path: str) -> None:
        """Persist the current in-memory inventory to a YAML file."""
        import yaml as _yaml

        devices = self.inventory.get_all_devices()
        data = {
            'devices': [
                {
                    'name': d.name,
                    'ip_address': d.ip_address,
                    'model': d.model,
                    'site': d.site,
                    'role': d.role,
                }
                for d in devices
            ]
        }
        try:
            with open(path, 'w') as f:
                _yaml.safe_dump(data, f, sort_keys=False)
            self.inventory_path = path
            console.print(f"[green]✓[/green] Saved inventory to {path}")
        except OSError as e:
            console.print(f"[red]Error saving inventory: {str(e)}[/red]")
    
    def _resolve_devices_from_arg(self, arg: str) -> Optional[List[Device]]:
        """Resolve a select/connect argument (all|none|names|filter) to a
        device list. Returns None (after printing an error) if the argument
        couldn't be resolved."""
        if arg == "all":
            devices = self.inventory.get_all_devices()
            print(cyan(f"Selected all {len(devices)} devices"))
            return devices
        
        if arg == "none":
            print(cyan("Cleared device selection"))
            return []
        
        if ',' in arg or ('=' not in arg and self.inventory.get_device(arg.strip())):
            # Select specific device(s) by name (comma-separated or single name)
            device_names = [name.strip() for name in arg.split(',')]
            devices = []
            
            for name in device_names:
                device = self.inventory.get_device(name)
                if device:
                    devices.append(device)
                else:
                    print(grey(f"Device not found: {name}"))
            
            print(cyan(f"Selected {len(devices)} devices"))
            return devices
        
        # Try to parse as filter
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
            else:
                print(red(f"Unknown filter: {arg}"))
                return None
            
            print(cyan(f"Selected {len(devices)} devices matching {arg}"))
            return devices
        
        print(red(f"Invalid selection: {arg}"))
        return None
    
    @staticmethod
    def _picker_handle_key(
        char: str,
        cursor: int,
        picked: Set[int],
        count: int,
        read_next: Callable[[], str],
    ) -> Tuple[int, Set[int], Optional[bool]]:
        """Process a single keypress for the interactive device picker.
        Pure function (no terminal I/O) so it can be unit tested directly.

        Returns (new_cursor, new_picked, action):
          action is True to confirm (Enter), False to cancel (q/Ctrl+C),
          or None to keep browsing. 'read_next' is called to read further
          bytes of an escape sequence (arrow keys) and lets tests supply
          canned input instead of a real terminal.
        """
        if count == 0:
            return cursor, picked, None
        
        if char in ('\r', '\n'):
            return cursor, picked, True
        
        if char in ('\x03', 'q', 'Q'):
            return cursor, picked, False
        
        if char == ' ':
            picked = set(picked)
            if cursor in picked:
                picked.discard(cursor)
            else:
                picked.add(cursor)
            return cursor, picked, None
        
        if char in ('a', 'A'):
            return cursor, set(range(count)), None
        
        if char in ('c', 'C'):
            return cursor, set(), None
        
        if char == '\x1b':  # ESC or start of an arrow-key escape sequence
            nxt = read_next()
            if nxt == '[':
                arrow = read_next()
                if arrow == 'A':  # Up
                    cursor = max(0, cursor - 1)
                elif arrow == 'B':  # Down
                    cursor = min(count - 1, cursor + 1)
                return cursor, picked, None
            # Bare Esc (no further bytes) cancels
            return cursor, picked, False
        
        return cursor, picked, None
    
    def _render_picker_lines(self, devices: List[Device], cursor: int, picked: Set[int]) -> List[str]:
        """Build the text lines for one frame of the device picker, reusing the
        same table look ('inventory list') so both commands share one visual
        language: same columns/order, cyan device names, and a Connected
        ✓/- column, plus a Pick checkbox column and a highlighted cursor row."""
        table = Table(title=f"Pick devices ({len(picked)}/{len(devices)} selected)")
        table.add_column("", width=1)  # cursor pointer
        table.add_column("Pick")
        table.add_column("Name", style="cyan")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Site")
        table.add_column("Role")
        table.add_column("Connected")
        
        for i, device in enumerate(devices):
            conn = self.connection_manager.get_connection(device.name)
            status = "✓" if conn and conn.connected else "-"
            pointer = "\u203a" if i == cursor else ""
            mark = escape("[x]") if i in picked else escape("[ ]")
            
            table.add_row(
                pointer,
                mark,
                str(device.name),
                str(device.ip_address),
                str(device.model or "-"),
                str(device.site or "-"),
                str(device.role or "-"),
                str(status),
                style="reverse" if i == cursor else None,
            )
        
        with console.capture() as capture:
            console.print(table)
        
        lines = capture.get().splitlines()
        lines.append("\u2191/\u2193 move  space toggle  a=all  c=clear  Enter=connect  q=cancel")
        return lines
    
    def _pick_devices_interactively(self) -> Optional[List[Device]]:
        """Interactive device picker for 'connect pick'. Returns the chosen
        devices, or None if the user cancelled or no terminal is available."""
        devices = self.inventory.get_all_devices()
        if not devices:
            console.print("[yellow]No devices in inventory. Load an inventory file first.[/yellow]")
            return None
        
        if not sys.stdin.isatty() or not HAS_TERMIOS:
            console.print("[yellow]'connect pick' needs an interactive terminal. Use 'connect <names>' instead.[/yellow]")
            return None
        
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        cursor = 0
        picked: Set[int] = set()
        prev_line_count = 0
        confirmed: Optional[bool] = None
        
        def read_char() -> str:
            return sys.stdin.read(1)
        
        try:
            tty.setraw(fd)
            sys.stdout.write('\033[?25l')  # hide cursor
            
            frame = self._render_picker_lines(devices, cursor, picked)
            for line in frame:
                sys.stdout.write(line + '\r\n')
            sys.stdout.flush()
            prev_line_count = len(frame)
            
            while confirmed is None:
                char = read_char()
                cursor, picked, confirmed = self._picker_handle_key(
                    char, cursor, picked, len(devices), read_char
                )
                
                frame = self._render_picker_lines(devices, cursor, picked)
                sys.stdout.write(f'\033[{prev_line_count}A')  # move to top of previous frame
                sys.stdout.write('\033[J')  # clear from cursor to end of screen
                for line in frame:
                    sys.stdout.write(line + '\r\n')
                sys.stdout.flush()
                prev_line_count = len(frame)
        finally:
            sys.stdout.write('\033[?25h')  # show cursor again
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
        if not confirmed:
            return None
        return [devices[i] for i in sorted(picked)]
    
    def do_connect(self, arg: str) -> None:
        """Connect to devices. Usage: connect [device1,device2|filter|pick]
        ('connect pick' opens an interactive picker: arrow keys to move,
        space to toggle, 'a' to select all, 'c' to clear, Enter to confirm
        and connect, 'q'/Ctrl+C to cancel. With no argument, connects to
        the current selection; devices that are already connected are
        skipped, so re-running 'connect' with no argument retries only the
        ones that previously failed)"""
        if arg.strip().lower() == 'pick':
            devices = self._pick_devices_interactively()
            if devices is None:
                print(grey("Selection cancelled."))
                return
            self.selected_devices = devices
        elif arg:
            # Allow 'connect <names|filter>' to select and connect in one step
            devices = self._resolve_devices_from_arg(arg)
            if devices is None:
                return
            self.selected_devices = devices
        
        if not self.selected_devices:
            print(grey("No devices selected. Use 'connect <name|filter>', 'connect all', or 'connect pick'."))
            return
        
        # Skip devices that already have a live connection so re-running
        # 'connect' (e.g. after a partial failure) doesn't open duplicate,
        # leaked SSH sessions to devices that already succeeded.
        already_connected = []
        to_connect = []
        for device in self.selected_devices:
            conn = self.connection_manager.get_connection(device.name)
            if conn and conn.connected:
                already_connected.append(device)
            else:
                to_connect.append(device)
        
        if already_connected:
            names = ', '.join(str(d.name) for d in already_connected)
            print(grey(f"Already connected: {names}"))
        
        if not to_connect:
            print(white(f"Connected to {len(already_connected)}/{len(self.selected_devices)} devices"))
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
        print(cyan(f"Connecting to {len(to_connect)} devices..."))
        
        connected = len(already_connected)
        for device in to_connect:
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
    
    def do_exit_config(self, arg: str) -> None:
        """Exit configuration mode on connected devices."""
        if not self.selected_devices:
            print(grey("No devices selected."))
            return
        
        # Check connections
        connected_devices = []
        for device in self.selected_devices:
            if device.name in self.connection_manager.connections:
                connection = self.connection_manager.connections[device.name]
                if connection.connected:
                    connected_devices.append(device)
        
        if not connected_devices:
            print(grey("No connected devices. Use 'connect' command first."))
            return
        
        print(cyan("Exiting configuration mode on all connected devices..."))
        
        for device in connected_devices:
            try:
                connection = self.connection_manager.connections[device.name]
                # Send 'end' to exit any config mode
                connection.send_command("end")
                # Reset config mode state
                connection.in_config_mode = False
                print(f"{device.name}: Exited configuration mode")
            except Exception as e:
                print(red(f"{device.name}: Failed to exit config mode - {str(e)}"))

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
        inventory_path = Path(path)
        if not inventory_path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return

        # Loading an inventory file replaces the current inventory rather
        # than merging into it, so re-loading the same (or another) file
        # doesn't fail with "duplicate device name" errors. Keep a backup
        # so a bad file doesn't wipe out an otherwise good inventory.
        previous_devices = dict(self.inventory.devices)
        self.inventory.devices.clear()

        try:
            if inventory_path.suffix.lower() in ['.yml', '.yaml']:
                self.inventory.load_yaml(path)
            else:
                self.inventory.load_txt(path)

            self.inventory_path = path
            device_count = len(self.inventory.devices)
            console.print(f"[green]✓[/green] Loaded {device_count} devices from {path}")

        except Exception as e:
            self.inventory.devices = previous_devices
            console.print(f"[red]Error loading inventory: {str(e)}[/red]")
    

    def _show_context_help(self, command: str, args: str) -> None:
        """Show context-sensitive help for commands."""
        if command == "connect":
            console.print(Panel(
                "[bold white]connect[/bold white] - [white]Connect to devices[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]connect                     # Retry current selection (skips already-connected)\n"
                "connect all                 # Connect to all devices\n"
                "connect pick                # Interactively pick devices to connect\n"
                "connect device1,device2     # Connect to specific devices\n"
                "connect model=2960X         # Connect to devices matching model\n"
                "connect site=100McCaul      # Connect to devices matching site\n"
                "connect role=switch         # Connect to devices matching role[/white]\n\n"
                "[cyan]'connect pick' keys:[/cyan]\n"
                "[white]• \u2191/\u2193 - move cursor\n"
                "• space - toggle device\n"
                "• a / c - select all / clear\n"
                "• Enter - confirm and connect\n"
                "• q / Ctrl+C - cancel[/white]\n\n"
                "[cyan]Available filters:[/cyan]\n"
                "[white]• model=<model_name>\n"
                "• site=<site_name>\n"
                "• role=<role_name>\n"
                "• name=<pattern>[/white]\n\n"
                "[dim]Note: Already-connected devices are skipped, so bare 'connect'\n"
                "retries only devices that failed to connect last time.\n"
                "Will prompt for credentials if not already provided.[/dim]",
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
        
        elif command == "inventory":
            console.print(Panel(
                "[bold white]inventory[/bold white] - [white]Load and list device inventory[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]inventory                  # Show current inventory status\n"
                "inventory load <path>      # Load inventory from file\n"
                "inventory <path>           # Shorthand for 'inventory load <path>'\n"
                "inventory list             # List all devices\n"
                "inventory list model=2960X # Filter by model\n"
                "inventory list site=100McCaul  # Filter by site\n"
                "inventory list role=switch # Filter by role\n"
                "inventory list name=sw-    # Filter by name pattern[/white]\n\n"
                "[cyan]Available list filters:[/cyan]\n"
                "[white]• model=<model_name>\n"
                "• site=<site_name>\n"
                "• role=<role_name>\n"
                "• name=<pattern>[/white]\n\n"
                "[cyan]Supported load formats:[/cyan]\n"
                "[white]• YAML files (.yml, .yaml)\n"
                "• Text files (.txt)[/white]\n\n"
                "[cyan]Auto-load locations:[/cyan]\n"
                "[white]• ./devices.yaml\n"
                "• ./config-genie/devices.yaml\n"
                "• ~/config-genie/devices.yaml[/white]",
                title="Context Help",
                width=60
            ))
        
        elif command == "netbox":
            console.print(Panel(
                "[bold white]netbox[/bold white] - [white]Load device inventory from NetBox[/white]\n\n"
                "[cyan]Usage:[/cyan]\n"
                "[white]netbox                              # Load all active devices\n"
                "netbox site=<site>                  # Filter by site\n"
                "netbox role=<role>                  # Filter by role\n"
                "netbox status=<status>              # Filter by status (default: active)\n"
                "netbox insecure                     # Ignore SSL certificate errors\n"
                "netbox site=hq role=access[/white]\n\n"
                "[cyan]Credentials:[/cyan]\n"
                "[white]• Uses NETBOX_URL / NETBOX_TOKEN env vars if set\n"
                "• Otherwise you'll be prompted interactively\n"
                "• NETBOX_VERIFY_SSL=false also ignores SSL errors[/white]",
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
    
    def onecmd(self, line: str) -> bool:
        """Override onecmd to add commands to history."""
        # Add non-empty commands to history (but not duplicates of the last command)
        line = line.strip()
        if line and line != 'EOF' and line != '?' and (not self.command_history or line != self.command_history[-1]):
            self.command_history.append(line)
            # Limit history size to prevent memory issues
            if len(self.command_history) > 1000:
                self.command_history.pop(0)
        
        # Reset history index when a new command is executed
        self.history_index = -1
        
        # Call parent implementation
        return super().onecmd(line)
    
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
                    sys.stdout.write('\r\n')
                    sys.stdout.flush()
                    # Reset history index for next input
                    self.history_index = -1
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
                    sys.stdout.write('\r\n')
                    sys.stdout.flush()
                    raise KeyboardInterrupt
                
                elif char == '\x04':  # Ctrl+D (EOF)
                    sys.stdout.write('\r\n')
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
                            sys.stdout.write('\r\n')
                            # Show completions in columns
                            import shutil
                            term_width = shutil.get_terminal_size().columns
                            max_width = max(len(comp) for comp in completions)
                            cols = max(1, term_width // (max_width + 2))
                            
                            for i, comp in enumerate(completions):
                                if i > 0 and i % cols == 0:
                                    sys.stdout.write('\r\n')
                                sys.stdout.write(comp.ljust(max_width + 2))
                            sys.stdout.write('\r\n')
                            
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
                
                # Handle escape sequences for arrow keys
                elif char == '\x1b':  # ESC sequence
                    next_char = sys.stdin.read(1)
                    if next_char == '[':
                        arrow_char = sys.stdin.read(1)
                        
                        if arrow_char == 'A':  # Up arrow
                            if self.command_history and self.history_index < len(self.command_history) - 1:
                                self.history_index += 1
                                historical_command = self.command_history[-(self.history_index + 1)]
                                
                                # Clear current line and show historical command
                                sys.stdout.write('\r\033[K')
                                sys.stdout.write(self.prompt + historical_command)
                                sys.stdout.flush()
                                
                                # Update buffer
                                input_buffer = list(historical_command)
                                cursor_pos = len(input_buffer)
                        
                        elif arrow_char == 'B':  # Down arrow
                            if self.history_index > 0:
                                self.history_index -= 1
                                historical_command = self.command_history[-(self.history_index + 1)]
                                
                                # Clear current line and show historical command
                                sys.stdout.write('\r\033[K')
                                sys.stdout.write(self.prompt + historical_command)
                                sys.stdout.flush()
                                
                                # Update buffer
                                input_buffer = list(historical_command)
                                cursor_pos = len(input_buffer)
                            elif self.history_index == 0:
                                # Go back to empty line
                                self.history_index = -1
                                
                                # Clear current line
                                sys.stdout.write('\r\033[K')
                                sys.stdout.write(self.prompt)
                                sys.stdout.flush()
                                
                                # Clear buffer
                                input_buffer = []
                                cursor_pos = 0
                        
                        # Left/Right arrows for cursor movement (future enhancement)
                        elif arrow_char == 'C':  # Right arrow
                            if cursor_pos < len(input_buffer):
                                cursor_pos += 1
                                sys.stdout.write('\033[C')  # Move cursor right
                                sys.stdout.flush()
                        
                        elif arrow_char == 'D':  # Left arrow
                            if cursor_pos > 0:
                                cursor_pos -= 1
                                sys.stdout.write('\033[D')  # Move cursor left
                                sys.stdout.flush()
        
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
    
    def complete_connect(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for connect command."""
        # Base options
        options = ['all', 'none', 'pick']
        
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
    
    def _complete_file_path(self, text: str) -> List[str]:
        """Complete a filesystem path for inventory files (.yml/.yaml/.txt)."""
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
        except Exception:
            return []
    
    def complete_inventory(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Autocomplete for inventory command: subcommands (load/list), file
        paths after 'load', and filter keys after 'list'."""
        words = line.split()
        # Determine how many completed words precede the one being typed
        typed_so_far = words[:-1] if (words and not line.endswith(' ')) else words
        
        if not typed_so_far or typed_so_far == ['inventory']:
            # Completing the subcommand itself: suggest load/list, or fall
            # back to file paths for the 'inventory <path>' shorthand
            subcommand_options = [opt for opt in ('load', 'list') if opt.startswith(text)]
            return subcommand_options + self._complete_file_path(text)
        
        subcommand = typed_so_far[1] if len(typed_so_far) > 1 else ''
        if subcommand == 'load':
            return self._complete_file_path(text)
        elif subcommand == 'list':
            options = ['model=', 'site=', 'role=', 'name=']
            return [option for option in options if option.startswith(text)]
        
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
    
    def do_history(self, arg: str) -> None:
        """Show command history. Use up/down arrows to navigate history."""
        if not self.command_history:
            print(grey("No command history yet."))
            return
        
        print(cyan("Command History:"))
        for i, command in enumerate(self.command_history[-10:], 1):  # Show last 10 commands
            print(f"{i:2d}: {command}")
        
        if len(self.command_history) > 10:
            print(grey(f"... and {len(self.command_history) - 10} more commands"))
        print(grey("Use up/down arrow keys to navigate through history."))

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