# Changelog

All notable changes to Config-Genie will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `connect pick` — an interactive device picker for the `connect` command: arrow keys move the cursor, space toggles the device under the cursor, `a`/`c` select all/clear, Enter confirms and connects to the picked devices, `q`/Ctrl+C cancels. Falls back with a message if run outside a real terminal. Uses the same table layout as `inventory list` so both commands share one visual language
- `connect add` — connects to devices without disconnecting existing sessions first (see below)
- `connect pick` now scrolls automatically when the device list is taller than the terminal: the visible window follows the cursor, and a "N more above/below" indicator shows how many devices are scrolled off-screen
- `connect <ip>` — connect by IP address (e.g. `connect 192.168.1.1`), matching an inventory device with that IP if one exists, or connecting directly if it isn't in the inventory. Works alongside device names in comma-separated lists (e.g. `connect sw01,192.168.1.5`). New `Inventory.get_device_by_ip()` and `is_ip_address()` helpers back this

### Changed
- Clarified `connect pick`'s checkbox: it now always means "will connect on Enter" and nothing else. Previously the checkbox mark and the Connected status were combined into one column (e.g. `[x] ✓`), which was ambiguous about what the checkbox itself meant. Now already-connected devices start pre-checked and are labeled `(connected)` next to their name instead
- Removed decorative emoji from README section headings, keeping plain text and simple symbols (e.g. `✓`/`✗`)
- `connect` now disconnects any existing sessions before connecting by default, so you always end up connected to exactly the devices you just selected instead of accumulating connections across repeated `connect` calls. Use `connect add ...` (or bare `connect add` to retry devices that previously failed) to keep existing connections and add to them instead
- `inventory list` and `connect pick` now share one visual language: `connect pick` renders the same table columns as `inventory list` (Name, IP Address, Model, Site, Role), with Pick and Connected merged into a single column (e.g. `[x] ✓`) since both are just per-device status markers
- Removed the separate `select` command. `connect` now does the job of both: `connect <names>`, `connect model=2960X`, `connect site=<site>`, `connect role=<role>`, and `connect all` select and connect in one step; `connect` with no argument still connects to the current selection (e.g. left over from a previous `connect` call)
- Merged the `devices` command into `inventory`: `inventory list [filter]` replaces `devices [filter]`. `inventory load <path>` is now the explicit form for loading a file; the old bare `inventory <path>` shorthand still works for backward compatibility
- `inventory list`'s "Status" column (which showed a stale "selected" label left over from the removed `select` command) is now a "Connected" column showing `✓` for devices with an active connection

### Fixed
- `connect add <device>` no longer discards the previously selected/connected devices - it now accumulates onto the current selection instead of replacing it with only the most recently added device. Previously, connecting to several devices one at a time with repeated `connect add` calls left everything connected, but `execute` would silently only run on the last device added, since `self.selected_devices` had been overwritten each time
- `connect` (with no argument, or re-running `connect <names>`) now skips devices that already have a live connection instead of blindly reconnecting all of them, which previously opened a duplicate, leaked SSH session for every already-connected device on each retry. This also makes bare `connect` actually useful: it now retries only devices that failed to connect last time
- Fixed misaligned output after pressing Enter at the `(config-genie)` prompt: raw terminal mode (used for arrow-key history/instant help) disables automatic carriage-return translation, so writing a bare `\n` moved to the next line without returning to column 0 — causing every following line (e.g. `Selected N devices`, the `Execute '...' on N devices? [y/n]` confirmation) to be indented by however many characters were typed on the prompt line. All raw-mode newline writes now emit `\r\n`.
- Device selection now works for a single device name (e.g. `connect 256`); previously only comma-separated lists (`connect 256,400`, formerly `select 256,400`) were recognized and a lone name fell through to "Invalid selection"
- `connect <names|filter>` now selects and connects to the specified devices directly, instead of silently ignoring its argument and connecting to whatever was left over in the selection from a previous call

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