"""Tests for execution command classification."""

from config_genie.execution import ExecutionManager


def test_exit_after_configuration_command_stays_in_config_sequence():
    manager = ExecutionManager(connection_manager=None)
    commands = ["interface GigabitEthernet0/1", "description Uplink", "exit"]

    assert manager._filter_config_commands(commands) == commands
    assert manager._filter_show_commands(commands) == []


def test_exit_without_configuration_context_is_an_exec_command():
    manager = ExecutionManager(connection_manager=None)
    commands = ["show version", "exit"]

    assert manager._filter_config_commands(commands) == []
    assert manager._filter_show_commands(commands) == commands
