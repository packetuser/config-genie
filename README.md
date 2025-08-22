# Config-Genie

CLI-based network automation tool for Cisco devices. Config-Genie allows network administrators to interactively connect to multiple devices, validate, preview, and apply configuration commands or snippets with safety and rollback mechanisms.

## 🚀 Features

- **Interactive CLI** with step-by-step prompts and rich console output
- **Multiple device inventory management** (YAML and text format support)
- **Template/snippet library** with variable substitution and validation
- **Dry-run mode** for previewing changes before applying
- **Command-level rollback capabilities** for safe operations
- **Comprehensive safety checks** and confirmation prompts
- **Session history and logging** for audit trails
- **Multi-device operations** with automatic retry and error handling

## 📋 Requirements

- Python 3.11+
- Linux (Ubuntu 22.04 recommended)
- Network access to Cisco devices
- SSH access to target devices

## 📦 Installation

```bash
# Install required dependencies
pip install pyyaml click rich paramiko

# Install Config-Genie in development mode
pip install -e .
```

## 🎯 Quick Start

1. **Create an inventory file** (`devices.yml`):
```yaml
devices:
  - name: sw01-hq
    ip_address: 192.168.1.10
    model: 2960X
    site: HQ
    role: access
  - name: sw02-hq
    ip_address: 192.168.1.11
    model: 9300
    site: HQ
    role: distribution
```

2. **Validate your inventory**:
```bash
config-genie validate devices.yml
```

3. **View available templates**:
```bash
config-genie templates
```

4. **Start interactive mode**:
```bash
config-genie -i devices.yml
```

## 🖥️ Usage

### Command Line Interface

```bash
# Validate inventory and check device reachability
config-genie validate inventory.yml

# List available configuration templates
config-genie templates

# Execute a single command (dry-run)
config-genie execute "show version" -i inventory.yml --dry-run

# Interactive mode with inventory
config-genie -i inventory.yml

# Verbose output
config-genie -v -i inventory.yml
```

### Interactive Mode

```bash
config-genie
```

Available interactive commands:
- `help` - Show available commands
- `inventory [path]` - Load inventory file
- `devices [filter]` - List and filter devices
- `select <devices>` - Select devices for operations
- `connect` - Connect to selected devices
- `execute <command>` - Execute commands on connected devices
- `templates` - Manage configuration templates
- `history` - Show session history
- `status` - Show current session status
- `quit` - Exit the session

## 📄 Inventory Formats

### YAML Format (`devices.yml`)
```yaml
devices:
  - name: sw01
    ip_address: 192.168.1.1
    model: 2960X
    site: HQ
    role: access
  - name: sw02
    ip_address: 192.168.1.2
    model: 9300
    site: Branch
    role: distribution
```

### Text Format (`devices.txt`)
```
# IP,Name,Model,Site,Role
192.168.1.1,sw01,2960X,HQ,access
192.168.1.2,sw02,9300,Branch,distribution
# Or just IP addresses
192.168.1.3
192.168.1.4
```

## 🔧 Templates

Config-Genie includes built-in templates and supports custom templates with variable substitution:

```yaml
# Custom template example
name: interface_config
description: Basic interface configuration
commands:
  - interface ${interface}
  - description ${description}
  - switchport mode ${mode}
  - switchport access vlan ${vlan}
  - no shutdown
variables:
  interface: GigabitEthernet0/1
  description: User Port
  mode: access
  vlan: "10"
tags:
  - interface
  - basic
```

## 🛡️ Safety Features

- **Command validation** against Cisco syntax rules
- **Risky command detection** (reload, erase, shutdown, etc.)
- **Multi-device safety checks** for bulk operations
- **Device compatibility validation** based on model
- **Rollback command generation** for configuration changes
- **Interactive confirmations** for dangerous operations

## 🧪 Testing

```bash
# Run the demo
python3 demo.py

# Run basic functionality tests
python3 run_tests.py

# Test specific functionality
PYTHONPATH=src python3 -c "
from config_genie.validation import CiscoCommandValidator
validator = CiscoCommandValidator()
result = validator.validate_commands(['show version'])
print(f'Validation passed: {result.is_valid}')
"
```

## 📊 Logging and History

Config-Genie automatically logs all operations:

- **Connection attempts** and results
- **Command executions** with output and timing
- **Template usage** with variable substitutions
- **Validation results** and safety checks
- **Rollback operations** and success/failure

Logs are stored in `~/.config/config-genie/logs/` with both file logging and session history.

## 🚨 Safety Levels

- **LOW**: Informational warnings (logging, SNMP changes)
- **MEDIUM**: Operations requiring attention (bulk changes, mixed models)
- **HIGH**: Potentially disruptive operations (VLAN removal, route changes)
- **CRITICAL**: Operations causing downtime (reload, erase, format)

## 🎮 Development

```bash
# Install development dependencies
pip install -e ".[dev,test]"

# Run tests with pytest (if available)
pytest

# Run custom test runner
python3 run_tests.py

# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/
```

## 🏗️ Architecture

Config-Genie follows a modular architecture:

- **CLI Module**: Interactive prompts, command parsing, and help
- **Inventory Module**: Device loading, validation, and filtering
- **Connector Module**: SSH connections and command execution
- **Validation Module**: Command syntax and safety validation
- **Execution Manager**: Orchestrated command execution with rollback
- **Templates Module**: Template management and variable substitution
- **Logging Module**: Session history and audit logging
- **Safety Module**: Risk assessment and confirmation prompts

## 🔌 Supported Cisco Platforms

- **IOS and IOS-XE** (primary focus)
- **Catalyst 2960X, 9200, 9300, 9500** series switches
- **Extensible** for additional platforms via plugin system

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run the test suite
5. Submit a pull request

## 📜 License

MIT License - see LICENSE file for details.

## 🆘 Support

For issues and support:
1. Check the logs in `~/.config/config-genie/logs/`
2. Run with `-v` for verbose output
3. Use the demo script to verify functionality
4. Check device connectivity and credentials

## 📚 Examples

See `demo.py` for comprehensive usage examples and `sample_inventory.yml` for inventory file format.