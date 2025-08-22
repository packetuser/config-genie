Config-Genie: Developer Specification
1. Overview

Config-Genie is a CLI-based network automation tool for Cisco devices. It allows network administrators to interactively connect to multiple devices, validate, preview, and apply configuration commands or snippets with safety and rollback mechanisms. The tool supports device inventories, template libraries, interactive filtering/grouping, and standard logging.

Primary Goals:

Safe, consistent changes across multiple Cisco devices

Immediate execution with pre-checks and dry-run support

User-friendly, interactive CLI for junior and senior network admins

Target Platforms: Linux (Ubuntu 22.04)
Supported Cisco Platforms: IOS and IOS-XE (focus on 2960X, 9200, 9300, 9500 devices)
Implementation Language: Python (fully)

2. Core Requirements
2.1 User Interaction

Interactive CLI with step-by-step prompts

Support for command-line flags/arguments for automation

Command history and tab-completion

Interactive help commands (help, ?)

Clean, minimal interface (no idle tips)

2.2 Device Management

Multiple inventories supported (devices.yml or devices.txt)

Ad hoc device entry supported

Interactive filtering and grouping by device attributes (model, site, role)

Auto-suggestions for device attributes

Inventory validation (IP format, duplicates, reachability)

No network discovery; devices added manually

2.3 Authentication

Username/password authentication, delegated to TACACS

Session-only credential caching; cleared after session timeout

2.4 Command Execution

Single-line or multi-line snippets per execution

Dry-run mode for previewing changes

Pre-execution validation: full device configuration checks for conflicts

Auto-retry for transient failures

Stop entire run if any device fails

Command-level rollback with interactive confirmation

Interactive confirmation before applying templates/snippets

Built-in safeguards:

Risky command detection

Multi-VLAN/interface warnings

Device reachability checks

Duplicate/conflicting command warnings within snippets

2.5 Templates/Snippets

CLI-editable library

Pre-built example templates for common Cisco tasks

Syntax highlighting and context-aware suggestions while editing

Interactive validation when saving/editing (syntax + conflicts)

Undo/rollback support for recently applied templates/snippets

Confirmation required for multi-device template application

2.6 Verification/Reporting

Command templates for verification/troubleshooting (show commands)

Single verification command at a time

Admin interprets verification output (no automated warnings)

Color-coded previews before applying changes:

Green = additions

Red = removals

Yellow = warnings

Standard logging: commands sent, success/failure, basic output

Session history: saved and viewable in CLI

Metrics:

Mandatory: time per device

Optional: total run time, success/failure counts, retries, skipped/unreachable devices, safety alerts

3. Architecture
3.1 Modules

CLI Module

Interactive prompt system, tab-completion, help commands

Command parsing and dispatch

Template/snippet editor with syntax highlighting

Inventory Module

Load, validate, and manage multiple inventories

Filtering and grouping by device attributes

Device Connector Module

Connect via SSH to Cisco devices

Delegate authentication to TACACS

Execute commands/snippets and retrieve output

Manage auto-retry and connection errors

Validator Module

Pre-check against current device config

Conflict detection, duplicate commands, multi-VLAN/interface checks

Execution Manager

Orchestrates command application

Handles dry-run mode, interactive confirmations, command-level rollback

Tracks metrics per device

Templates Module

Manage library of templates/snippets

Context-aware suggestions and validation

Logger Module

Standard logging of commands, results, session history

Color-coded previews for planned changes

Plugin System

Extendable interface for future custom commands, checks, or integrations

4. Data Handling
4.1 Inventory Files

Format: YAML (devices.yml) or plaintext (devices.txt)

Fields:

Device name / ID

IP address / hostname

Model

Site / role

Validation: IP format, duplicates, reachability check

4.2 Templates/Snippets

CLI-editable YAML or JSON format for structured templates

Syntax validation + conflict detection on save

Pre-built examples included

4.3 Session Data

In-memory cache for session credentials

Session history: command, device, status, timestamps

Cleared on session timeout

4.4 Logging

Standard logging to CLI only

Include command executed, device, success/failure, and basic output

Optional metrics collected for admin review

5. Error Handling

Connection Errors: Auto-retry; if ultimately fails, stop run, log failure

Command Validation Errors: Prevent execution; interactive warning or confirmation

Device Unreachable: Warn admin before attempting changes

Duplicate / Conflicting Commands: Warn admin during snippet/template editing

Rollback Errors: If rollback fails, log failure, stop further execution, notify admin via CLI

6. Testing Plan
6.1 Unit Tests

Validate individual modules:

CLI parsing and input handling

Inventory loading and validation

Template editing and syntax checking

Metrics calculation

6.2 Integration Tests

Full workflow simulations using mocked or virtual devices

Test execution manager, rollback, dry-run, auto-retry

Test interaction between CLI, templates, and device connector modules

Use pytest framework with fixtures for simulated devices

6.3 Test Coverage Goals

80%+ coverage of critical modules (execution manager, validator, templates, device connector)

Include edge cases:

Conflicting commands

Multi-device failures

Command-level rollback

7. Development Environment

Python 3.11+

Dependency management via pyproject.toml or requirements.txt

Linux only (Ubuntu 22.04 recommended)

Virtual environments recommended for isolation

Plugin interface for future extensibility

8. Security Considerations

TACACS handles authentication and permissions

Session-only credential caching; cleared on timeout

Safety checks to prevent disruptive commands

Admin confirmations for risky operations

9. Deliverables

CLI-based Python application: config-genie

Inventory management system

Template/snippet library with editing and validation

Command execution engine with rollback and dry-run support

Standard logging and session history

Unit and integration tests

Plugin interface for future extensions
