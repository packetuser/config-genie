"""Template and snippet management system."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import yaml
except ImportError:
    yaml = None


class Template:
    """Configuration template or snippet."""
    
    def __init__(
        self,
        name: str,
        commands: List[str],
        description: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None
    ):
        self.name = name
        self.commands = commands
        self.description = description
        self.variables = variables or {}
        self.tags = tags or []
    
    def render(self, variables: Optional[Dict[str, str]] = None) -> List[str]:
        """Render template with variable substitution."""
        var_dict = self.variables.copy()
        if variables:
            var_dict.update(variables)
        
        rendered_commands = []
        for command in self.commands:
            rendered_command = command
            
            # Simple variable substitution with ${variable_name} syntax
            for var_name, var_value in var_dict.items():
                pattern = f"${{{var_name}}}"
                rendered_command = rendered_command.replace(pattern, str(var_value))
            
            rendered_commands.append(rendered_command)
        
        return rendered_commands
    
    def validate_syntax(self) -> List[str]:
        """Validate template syntax and return any issues found."""
        issues = []
        
        if not self.name:
            issues.append("Template name is required")
        
        if not self.commands:
            issues.append("Template must contain at least one command")
        
        # Check for common Cisco configuration issues
        for i, command in enumerate(self.commands):
            if not command.strip():
                issues.append(f"Line {i + 1}: Empty command")
                continue
            
            # Check for potential syntax issues
            if command.strip().startswith('!'):
                continue  # Comments are OK
            
            # Check for unresolved variables
            unresolved_vars = re.findall(r'\$\{([^}]+)\}', command)
            for var in unresolved_vars:
                if var not in self.variables:
                    issues.append(f"Line {i + 1}: Unresolved variable '${var}'")
        
        return issues
    
    def get_variables(self) -> List[str]:
        """Extract all variable names used in the template."""
        variables = set()
        for command in self.commands:
            found_vars = re.findall(r'\$\{([^}]+)\}', command)
            variables.update(found_vars)
        return list(variables)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary for serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'commands': self.commands,
            'variables': self.variables,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Template':
        """Create template from dictionary."""
        return cls(
            name=data['name'],
            commands=data['commands'],
            description=data.get('description'),
            variables=data.get('variables', {}),
            tags=data.get('tags', [])
        )


class TemplateManager:
    """Manage configuration templates and snippets."""
    
    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Default to ~/.config/config-genie/templates
            home = Path.home()
            self.templates_dir = home / '.config' / 'config-genie' / 'templates'
        
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.templates: Dict[str, Template] = {}
        
        # Load built-in templates
        self._create_builtin_templates()
        
        # Load user templates
        self._load_templates()
    
    def _create_builtin_templates(self) -> None:
        """Create built-in example templates."""
        builtin_templates = [
            Template(
                name="basic_interface_config",
                description="Basic interface configuration",
                commands=[
                    "interface ${interface}",
                    "description ${description}",
                    "switchport mode ${mode}",
                    "switchport access vlan ${vlan}",
                    "no shutdown"
                ],
                variables={
                    "interface": "GigabitEthernet0/1",
                    "description": "User Port",
                    "mode": "access",
                    "vlan": "10"
                },
                tags=["interface", "basic", "switchport"]
            ),
            Template(
                name="vlan_creation",
                description="Create VLAN with name",
                commands=[
                    "vlan ${vlan_id}",
                    "name ${vlan_name}"
                ],
                variables={
                    "vlan_id": "10",
                    "vlan_name": "DATA_VLAN"
                },
                tags=["vlan", "basic"]
            ),
            Template(
                name="save_config",
                description="Save running configuration",
                commands=[
                    "copy running-config startup-config"
                ],
                tags=["maintenance", "save"]
            ),
            Template(
                name="show_interface_status",
                description="Show interface status summary",
                commands=[
                    "show interfaces status"
                ],
                tags=["show", "interface", "troubleshooting"]
            ),
            Template(
                name="show_vlan_brief",
                description="Show VLAN summary",
                commands=[
                    "show vlan brief"
                ],
                tags=["show", "vlan", "troubleshooting"]
            )
        ]
        
        for template in builtin_templates:
            self.templates[template.name] = template
    
    def _load_templates(self) -> None:
        """Load templates from files."""
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r') as f:
                    data = json.load(f)
                
                template = Template.from_dict(data)
                self.templates[template.name] = template
                
            except Exception as e:
                print(f"Warning: Failed to load template {template_file}: {e}")
        
        # Also load YAML templates if available
        if yaml:
            for template_file in self.templates_dir.glob("*.yml"):
                try:
                    with open(template_file, 'r') as f:
                        data = yaml.safe_load(f)
                    
                    template = Template.from_dict(data)
                    self.templates[template.name] = template
                    
                except Exception as e:
                    print(f"Warning: Failed to load YAML template {template_file}: {e}")
    
    def save_template(self, template: Template, format: str = 'json') -> None:
        """Save template to file."""
        if format.lower() == 'yaml' and not yaml:
            raise ValueError("PyYAML is required for YAML format")
        
        filename = f"{template.name}.{format.lower()}"
        filepath = self.templates_dir / filename
        
        data = template.to_dict()
        
        with open(filepath, 'w') as f:
            if format.lower() == 'yaml':
                yaml.dump(data, f, default_flow_style=False, indent=2)
            else:
                json.dump(data, f, indent=2)
        
        self.templates[template.name] = template
    
    def delete_template(self, name: str) -> bool:
        """Delete a template."""
        if name not in self.templates:
            return False
        
        # Remove from memory
        del self.templates[name]
        
        # Remove files
        for ext in ['json', 'yml', 'yaml']:
            filepath = self.templates_dir / f"{name}.{ext}"
            if filepath.exists():
                filepath.unlink()
        
        return True
    
    def get_template(self, name: str) -> Optional[Template]:
        """Get template by name."""
        return self.templates.get(name)
    
    def list_templates(self, tag: Optional[str] = None) -> List[Template]:
        """List all templates, optionally filtered by tag."""
        templates = list(self.templates.values())
        
        if tag:
            templates = [t for t in templates if tag in t.tags]
        
        return sorted(templates, key=lambda t: t.name)
    
    def search_templates(self, query: str) -> List[Template]:
        """Search templates by name or description."""
        query_lower = query.lower()
        results = []
        
        for template in self.templates.values():
            if (query_lower in template.name.lower() or 
                (template.description and query_lower in template.description.lower())):
                results.append(template)
        
        return sorted(results, key=lambda t: t.name)
    
    def validate_template(self, template: Template) -> List[str]:
        """Validate template and return issues."""
        issues = template.validate_syntax()
        
        # Check for duplicates
        if template.name in self.templates:
            existing = self.templates[template.name]
            if existing != template:
                issues.append(f"Template '{template.name}' already exists")
        
        return issues
    
    def create_template_from_commands(
        self, 
        name: str, 
        commands: List[str],
        description: Optional[str] = None,
        auto_detect_variables: bool = True
    ) -> Template:
        """Create a template from a list of commands."""
        variables = {}
        
        if auto_detect_variables:
            # Auto-detect potential variables (simple heuristics)
            for command in commands:
                # Look for IP addresses
                ip_matches = re.findall(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', command)
                for ip in ip_matches:
                    var_name = f"ip_address_{len(variables) + 1}"
                    variables[var_name] = ip
                
                # Look for interface names
                if_matches = re.findall(r'\b((?:GigabitEthernet|FastEthernet|Ethernet)\d+/\d+(?:/\d+)?)\b', command)
                for interface in if_matches:
                    var_name = f"interface_{len(variables) + 1}"
                    variables[var_name] = interface
                
                # Look for VLAN IDs
                vlan_matches = re.findall(r'\bvlan (\d+)\b', command, re.IGNORECASE)
                for vlan in vlan_matches:
                    var_name = f"vlan_id_{len(variables) + 1}"
                    variables[var_name] = vlan
        
        return Template(
            name=name,
            commands=commands,
            description=description,
            variables=variables
        )
    
    def get_template_tags(self) -> List[str]:
        """Get all unique tags from templates."""
        tags = set()
        for template in self.templates.values():
            tags.update(template.tags)
        return sorted(list(tags))