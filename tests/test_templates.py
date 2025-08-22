"""Tests for template management system."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from config_genie.templates import Template, TemplateManager


class TestTemplate:
    """Test Template class functionality."""
    
    def test_template_creation(self):
        """Test basic template creation."""
        template = Template(
            name="test_template",
            commands=["interface GigabitEthernet0/1", "no shutdown"],
            description="Test template"
        )
        
        assert template.name == "test_template"
        assert len(template.commands) == 2
        assert template.description == "Test template"
        assert template.variables == {}
        assert template.tags == []
    
    def test_template_render_without_variables(self):
        """Test template rendering without variables."""
        template = Template(
            name="test",
            commands=["interface GigabitEthernet0/1", "no shutdown"]
        )
        
        rendered = template.render()
        assert rendered == ["interface GigabitEthernet0/1", "no shutdown"]
    
    def test_template_render_with_variables(self):
        """Test template rendering with variable substitution."""
        template = Template(
            name="test",
            commands=[
                "interface ${interface}",
                "description ${description}",
                "switchport access vlan ${vlan}"
            ],
            variables={
                "interface": "GigabitEthernet0/1",
                "description": "Test Port",
                "vlan": "10"
            }
        )
        
        rendered = template.render()
        expected = [
            "interface GigabitEthernet0/1",
            "description Test Port",
            "switchport access vlan 10"
        ]
        assert rendered == expected
    
    def test_template_render_with_override_variables(self):
        """Test template rendering with variable override."""
        template = Template(
            name="test",
            commands=["interface ${interface}"],
            variables={"interface": "GigabitEthernet0/1"}
        )
        
        rendered = template.render({"interface": "GigabitEthernet0/2"})
        assert rendered == ["interface GigabitEthernet0/2"]
    
    def test_template_validate_syntax_valid(self):
        """Test template validation for valid template."""
        template = Template(
            name="test",
            commands=["interface GigabitEthernet0/1", "no shutdown"],
            variables={}
        )
        
        issues = template.validate_syntax()
        assert issues == []
    
    def test_template_validate_syntax_issues(self):
        """Test template validation catches issues."""
        # Empty name
        template = Template(
            name="",
            commands=["interface GigabitEthernet0/1"]
        )
        issues = template.validate_syntax()
        assert any("name is required" in issue for issue in issues)
        
        # No commands
        template = Template(
            name="test",
            commands=[]
        )
        issues = template.validate_syntax()
        assert any("at least one command" in issue for issue in issues)
        
        # Unresolved variable
        template = Template(
            name="test",
            commands=["interface ${interface}"],
            variables={}
        )
        issues = template.validate_syntax()
        assert any("Unresolved variable" in issue for issue in issues)
    
    def test_get_variables(self):
        """Test extracting variables from template."""
        template = Template(
            name="test",
            commands=[
                "interface ${interface}",
                "vlan ${vlan_id}",
                "description ${interface} port"  # Duplicate variable
            ]
        )
        
        variables = template.get_variables()
        assert set(variables) == {"interface", "vlan_id"}
    
    def test_template_serialization(self):
        """Test template to/from dict conversion."""
        original = Template(
            name="test",
            commands=["interface GigabitEthernet0/1"],
            description="Test template",
            variables={"interface": "GigabitEthernet0/1"},
            tags=["interface", "basic"]
        )
        
        data = original.to_dict()
        restored = Template.from_dict(data)
        
        assert restored.name == original.name
        assert restored.commands == original.commands
        assert restored.description == original.description
        assert restored.variables == original.variables
        assert restored.tags == original.tags


class TestTemplateManager:
    """Test TemplateManager class functionality."""
    
    def test_template_manager_creation(self):
        """Test template manager creation with builtin templates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            # Should have builtin templates
            templates = manager.list_templates()
            assert len(templates) > 0
            
            # Check for specific builtin template
            basic_interface = manager.get_template("basic_interface_config")
            assert basic_interface is not None
            assert basic_interface.name == "basic_interface_config"
    
    def test_save_and_load_template_json(self):
        """Test saving and loading templates in JSON format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            template = Template(
                name="custom_template",
                commands=["interface GigabitEthernet0/1", "no shutdown"],
                description="Custom test template"
            )
            
            # Save template
            manager.save_template(template, format='json')
            
            # Verify it exists in manager
            loaded_template = manager.get_template("custom_template")
            assert loaded_template is not None
            assert loaded_template.name == "custom_template"
            assert loaded_template.commands == template.commands
            
            # Verify file was created
            json_file = Path(temp_dir) / "custom_template.json"
            assert json_file.exists()
    
    def test_delete_template(self):
        """Test template deletion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            template = Template(
                name="delete_me",
                commands=["show version"]
            )
            
            manager.save_template(template)
            assert manager.get_template("delete_me") is not None
            
            # Delete template
            result = manager.delete_template("delete_me")
            assert result is True
            assert manager.get_template("delete_me") is None
            
            # Try to delete non-existent template
            result = manager.delete_template("non_existent")
            assert result is False
    
    def test_list_templates_with_tag_filter(self):
        """Test listing templates with tag filtering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            # Get templates with 'show' tag
            show_templates = manager.list_templates(tag="show")
            assert len(show_templates) > 0
            assert all("show" in t.tags for t in show_templates)
            
            # Get templates with non-existent tag
            empty_templates = manager.list_templates(tag="nonexistent")
            assert len(empty_templates) == 0
    
    def test_search_templates(self):
        """Test template search functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            # Search by name
            results = manager.search_templates("interface")
            assert len(results) > 0
            assert any("interface" in t.name.lower() for t in results)
            
            # Search by description
            results = manager.search_templates("VLAN")
            assert len(results) > 0
    
    def test_validate_template(self):
        """Test template validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            # Valid template
            valid_template = Template(
                name="new_template",
                commands=["show version"]
            )
            issues = manager.validate_template(valid_template)
            assert len(issues) == 0
            
            # Duplicate template name
            duplicate_template = Template(
                name="basic_interface_config",  # Already exists as builtin
                commands=["show version"]
            )
            issues = manager.validate_template(duplicate_template)
            assert any("already exists" in issue for issue in issues)
    
    def test_create_template_from_commands(self):
        """Test creating template from command list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            commands = [
                "interface GigabitEthernet0/1",
                "ip address 192.168.1.1 255.255.255.0",
                "vlan 100"
            ]
            
            template = manager.create_template_from_commands(
                name="auto_template",
                commands=commands,
                description="Auto-created template",
                auto_detect_variables=True
            )
            
            assert template.name == "auto_template"
            assert template.commands == commands
            assert len(template.variables) > 0  # Should auto-detect some variables
    
    def test_get_template_tags(self):
        """Test getting all unique tags."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = TemplateManager(temp_dir)
            
            tags = manager.get_template_tags()
            assert len(tags) > 0
            assert "show" in tags
            assert "interface" in tags
            assert "vlan" in tags