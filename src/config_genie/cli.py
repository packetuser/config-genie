"""Main CLI entry point for Config-Genie."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from . import __version__
from .interactive import InteractiveSession


console = Console()


@click.group(invoke_without_command=True)
@click.option('--inventory', '-i', help='Path to inventory file')
@click.option('--dry-run', is_flag=True, help='Preview changes without applying')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.version_option(version=__version__, prog_name="config-genie")
@click.pass_context
def main(ctx: click.Context, inventory: Optional[str], dry_run: bool, verbose: bool) -> None:
    """Config-Genie: CLI-based network automation tool for Cisco devices."""
    
    # Store options in context
    ctx.ensure_object(dict)
    ctx.obj['inventory'] = inventory
    ctx.obj['dry_run'] = dry_run
    ctx.obj['verbose'] = verbose
    
    # If no subcommand provided, start interactive mode
    if ctx.invoked_subcommand is None:
        # ASCII art title with version
        ascii_art = f"""[bold cyan]
 ██████╗ ██████╗ ███╗   ██╗███████╗██╗ ██████╗ 
██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██╔════╝ 
██║     ██║   ██║██╔██╗ ██║█████╗  ██║██║  ███╗
██║     ██║   ██║██║╚██╗██║██╔══╝  ██║██║   ██║
╚██████╗╚██████╔╝██║ ╚████║██║     ██║╚██████╔╝
 ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝ ╚═════╝ 
                                               
 ██████╗ ███████╗███╗   ██╗██╗███████╗         
██╔════╝ ██╔════╝████╗  ██║██║██╔════╝         
██║  ███╗█████╗  ██╔██╗ ██║██║█████╗           
██║   ██║██╔══╝  ██║╚██╗██║██║██╔══╝           
╚██████╔╝███████╗██║ ╚████║██║███████╗         
 ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝         
                                               
                    [dim]v{__version__}[/dim]
[/bold cyan]"""
        
        console.print(ascii_art)
        console.print(Panel.fit(
            "[white]CLI-based network automation tool for Cisco devices[/white]\n"
            f"[dim]Version {__version__}[/dim]",
            title="[bold white]Welcome[/bold white]",
            border_style="cyan"
        ))
        
        # Start interactive session
        session = InteractiveSession(
            inventory_path=inventory,
            dry_run=dry_run,
            verbose=verbose
        )
        session.run()


@main.command()
@click.argument('inventory_path')
def validate(inventory_path: str) -> None:
    """Validate inventory file format and device reachability."""
    from .inventory import Inventory
    
    try:
        inventory = Inventory()
        
        # Load based on file extension
        path = Path(inventory_path)
        if not path.exists():
            console.print(f"[red]Error:[/red] Inventory file not found: {inventory_path}")
            sys.exit(1)
        
        if path.suffix.lower() in ['.yml', '.yaml']:
            inventory.load_yaml(inventory_path)
        else:
            inventory.load_txt(inventory_path)
        
        devices = inventory.get_all_devices()
        console.print(f"[green]✓[/green] Loaded {len(devices)} devices from inventory")
        
        # Show summary table
        table = Table(title="Device Inventory")
        table.add_column("Name")
        table.add_column("IP Address")
        table.add_column("Model")
        table.add_column("Site")
        table.add_column("Role")
        
        for device in devices:
            table.add_row(
                str(device.name),
                str(device.ip_address),
                str(device.model or "-"),
                str(device.site or "-"),
                str(device.role or "-")
            )
        
        console.print(table)
        
        # Check reachability if requested
        try:
            if Confirm.ask("Check device reachability?"):
                console.print("\n[yellow]Checking device reachability...[/yellow]")
                results = inventory.validate_reachability()
                
                reachable = sum(1 for r in results.values() if r)
                total = len(results)
                
                console.print(f"\n[green]✓[/green] {reachable}/{total} devices reachable")
                
                # Show unreachable devices
                unreachable = [name for name, reachable in results.items() if not reachable]
                if unreachable:
                    console.print(f"[red]✗[/red] Unreachable devices: {', '.join(unreachable)}")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Skipping reachability check.[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@main.command()
def templates() -> None:
    """Manage configuration templates and snippets."""
    from .templates import TemplateManager
    
    template_manager = TemplateManager()
    
    # Simple template listing for now
    templates = template_manager.list_templates()
    if not templates:
        console.print("[yellow]No templates found.[/yellow]")
        console.print("Use 'config-genie templates create' to create your first template.")
        return
    
    table = Table(title="Available Templates")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Commands")
    
    for template in templates:
        commands_preview = ", ".join(template.commands[:2])
        if len(template.commands) > 2:
            commands_preview += f", ... (+{len(template.commands) - 2} more)"
        
        table.add_row(
            template.name,
            template.description or "-",
            commands_preview
        )
    
    console.print(table)


@main.command()
@click.argument('command')
@click.option('--inventory', '-i', help='Path to inventory file')
@click.option('--filter', '-f', help='Filter devices (e.g., model=2960X)')
@click.option('--dry-run', is_flag=True, help='Preview without applying')
def execute(command: str, inventory: Optional[str], filter: Optional[str], dry_run: bool) -> None:
    """Execute a single command on devices."""
    console.print(f"[yellow]Executing command:[/yellow] {command}")
    
    if dry_run:
        console.print("[blue]DRY RUN MODE - No changes will be applied[/blue]")
    
    # This is a placeholder - full implementation would be in execution manager
    console.print("[green]✓[/green] Command execution planned (not implemented yet)")


if __name__ == "__main__":
    main()