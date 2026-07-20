# Changelog

All notable changes to Config-Genie will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-07-20

### Added
- `netbox` command in interactive mode — load device inventory from NetBox without any CLI flags; prompts for URL/token if `NETBOX_URL`/`NETBOX_TOKEN` aren't set, and offers to save the result as a YAML inventory file
- `insecure` flag (and `NETBOX_VERIFY_SSL=false` env var) to skip TLS certificate verification when connecting to NetBox instances with self-signed certificates
- Device selection step for NetBox import: after fetching candidates, both `config-genie netbox` (CLI) and the interactive `netbox` command display a numbered table and prompt for which devices to import (supports `all`, `none`, comma lists, ranges like `1,3-5`, and device names); CLI adds a `--select` flag to skip the prompt
- Default role filtering: NetBox import candidates are limited to device roles containing "switch" (e.g. "Edge Switch", "Access Switch") unless `--role`/`role=` is given, or `--role all`/`role=all` is used to see every role
- `Inventory.fetch_netbox_devices()` and `parse_device_selection()` helpers backing the new selection workflow

### Fixed
- NetBox device selection prompt now accepts device names (e.g. a switch literally named `300`) instead of only interpreting numeric input as a row number, which previously raised "Invalid selection" for numeric-looking device names
- `inventory <path>` in interactive mode now replaces the currently loaded inventory instead of merging into it, fixing an "Error loading inventory: Duplicate device name" error when re-loading an inventory file (including the one auto-loaded at startup). A failed reload no longer wipes out the previously loaded inventory.
- Command syntax validation now correctly warns about commands with leading whitespace (the check previously ran after the command was already stripped, so it could never trigger)
- Device compatibility checks now flag stack-member commands like `switch 1 priority 15`, not just commands containing the literal word "stack"
- Best-practices validation now correctly recommends saving the config after configuration changes (an empty-string entry in a `startswith()` check was matching every command, so the recommendation never fired)
- Rollback feasibility checks no longer flag safe `no shutdown` commands as risky just because they contain the substring "shutdown"
- Dry-run execution no longer fails with "Device not connected" — dry runs now simulate success without requiring an active device connection, as intended
- `Device` IP/hostname validation now correctly rejects malformed values like `invalid-ip` instead of silently accepting anything alphanumeric with dots/dashes stripped, while still allowing fully-qualified hostnames (e.g. `switch1.example.com`)
- Fixed test suite issues (incorrect mock setups causing false failures/hangs in SSH connector tests, and an outdated assertion in the CLI welcome-banner test) uncovered while auditing 11 previously-failing tests

## [0.3.0] - 2026-07-17

### Added
- NetBox integration: `config-genie netbox` command to pull device inventory directly from a NetBox instance via the `pynetbox` SDK
- `Inventory.load_netbox()` method supporting site/role/status filtering, `NETBOX_URL`/`NETBOX_TOKEN` env var fallback, and `--save` to persist fetched inventory as YAML
- `pynetbox` added as a project dependency

## [0.2.2] - 2025-08-25

### Added
- Command history with up/down arrow key navigation
- Left/right arrow keys for cursor movement within command lines
- `history` command to view recent command history
- Dynamic version display in ASCII art banner
- Professional ASCII art banner for "CONFIG GENIE" title

### Fixed
- Inventory command inconsistency with auto-loading
- Auto-loaded devices now properly show in `inventory` command
- ASCII art character clarity (C and E no longer look like S characters)

### Changed
- Persistent configuration mode - devices stay in config mode between commands
- Enhanced debug logging for configuration commands
- Command history automatically excludes duplicates and special commands
- Improved color consistency with more white text and cyan accents

## [0.2.1] - 2025-08-22

### Added
- Debug mode with comprehensive SSH communication logging
- Manual configuration mode exit with `exit_config` command
- Enhanced terminal output formatting and alignment fixes

### Fixed
- Enable mode handling for passwordless SSH environments
- Command execution and privileged mode handling
- Terminal whitespace and alignment issues
- SSH connection timeout reduced from 30s to 8s for faster feedback

### Changed
- Improved color scheme with consistent white and cyan theming
- Better error handling and user feedback during connections

## [0.2.0] - 2025-08-22

### Added
- Enhanced interactive shell with instant help system
- Context-sensitive help with `?` after commands
- Tab autocompletion for commands and Cisco command syntax
- Rich console formatting for better user experience
- Custom command loop with improved input handling

### Fixed
- Command execution reliability
- Interactive session stability
- Terminal control character handling

### Changed
- Upgraded user interface with Rich library integration
- Improved command parsing and validation
- Enhanced session management

## [0.1.0] - 2025-08-22

### Added
- Initial implementation of Config-Genie network automation tool
- SSH connectivity to Cisco devices using Paramiko
- Device inventory management (YAML and text formats)
- Basic command execution framework
- Template system for configuration management
- Interactive CLI session
- Device selection and filtering capabilities
- Dry-run mode for safe testing
- Configuration validation system

### Features
- Multi-device command execution
- Rollback capabilities
- Session history tracking
- Connection management with retry logic
- Support for Cisco IOS/IOS-XE devices
- YAML and plain text inventory formats
- Configuration templates with variable substitution

---

## Version History Summary

- **0.2.2**: Command history, dynamic banner, inventory fixes
- **0.2.1**: Debug mode, persistent config mode, UI improvements  
- **0.2.0**: Enhanced interactive shell with instant help and autocompletion
- **0.1.0**: Initial implementation with core network automation features