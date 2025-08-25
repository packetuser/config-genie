#!/usr/bin/env python3
"""
Simple script to help update the changelog.
Usage: python3 update_changelog.py [version] [date]
"""

import sys
from datetime import datetime
from pathlib import Path

def update_changelog(version: str, date: str = None):
    """Add a new version section to the changelog."""
    
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    changelog_path = Path(__file__).parent / "CHANGELOG.md"
    
    if not changelog_path.exists():
        print("CHANGELOG.md not found!")
        return
    
    # Read current changelog
    with open(changelog_path, 'r') as f:
        content = f.read()
    
    # Find where to insert new version (after the header)
    lines = content.split('\n')
    insert_index = -1
    
    for i, line in enumerate(lines):
        if line.startswith('## [') and ']' in line:
            insert_index = i
            break
    
    if insert_index == -1:
        print("Could not find where to insert new version in changelog!")
        return
    
    # Create new version section template
    new_section = [
        f"## [{version}] - {date}",
        "",
        "### Added",
        "- ",
        "",
        "### Fixed",
        "- ",
        "",
        "### Changed",
        "- ",
        "",
        "### Removed",
        "- ",
        "",
    ]
    
    # Insert new section
    lines = lines[:insert_index] + new_section + lines[insert_index:]
    
    # Write back to file
    with open(changelog_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Added version {version} section to CHANGELOG.md")
    print("Please edit the file to add your changes under the appropriate sections.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 update_changelog.py <version> [date]")
        print("Example: python3 update_changelog.py 0.3.0")
        sys.exit(1)
    
    version = sys.argv[1]
    date = sys.argv[2] if len(sys.argv) > 2 else None
    
    update_changelog(version, date)