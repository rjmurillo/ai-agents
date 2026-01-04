#!/usr/bin/env python3
"""
package_skill.py - Creates a distributable .skill file

Validates a skill using quick_validate.py, then packages it into a .skill
file (zip format) for distribution.

Usage:
    python package_skill.py <path/to/skill-folder> [output-directory]

Example:
    python package_skill.py ~/.claude/skills/my-skill
    python package_skill.py ~/.claude/skills/my-skill ./dist
"""

import sys
import zipfile
from pathlib import Path
import os

# Import validation from quick_validate
try:
    from quick_validate import validate_skill
except ImportError:
    # If running from different directory, try relative import
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from quick_validate import validate_skill


def validate_path_safety(path_str: str, allowed_base: Path) -> bool:
    """
    Validate that a path string is safe before resolving (prevents directory traversal).

    Args:
        path_str: Path string to validate (checked before resolution)
        allowed_base: Base directory that path must be within

    Returns:
        True if path is safe, False otherwise
    """
    # Normalize inputs to strings/Path
    path_str = str(path_str)
    base = allowed_base.resolve()

    # Optional early rejection of simple traversal attempts
    if '..' in path_str:
        return False

    try:
        candidate = Path(path_str)

        # If the user provides an absolute path, ensure it is within the allowed base
        if candidate.is_absolute():
            resolved_path = candidate.resolve()
        else:
            # Join relative paths to the trusted base before resolving
            resolved_path = (base / candidate).resolve()

        # Ensure the resolved path is contained within the allowed base
        resolved_path.relative_to(base)
        return True
    except (ValueError, OSError):
        return False


def package_skill(skill_path, output_dir=None):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the .skill file (defaults to current directory)

    Returns:
        Path to the created .skill file, or None if error
    """
    # SECURITY: Validate path safety BEFORE any resolution (prevents CWE-22)
    skills_root = (Path.home() / ".claude" / "skills").resolve()

    # Pre-validation: check string for traversal attempts before any Path operations
    if not validate_path_safety(str(skill_path), skills_root):
        print(f"❌ Error: Skill path contains unsafe characters or escapes allowed directory")
        print(f"   Allowed root: {skills_root}")
        return None

    # Now safe to resolve since we validated the string first
    user_skill_path = Path(skill_path)
    if not user_skill_path.is_absolute():
        user_skill_path = (skills_root / user_skill_path)

    try:
        skill_path = user_skill_path.resolve()  # lgtm[py/path-injection] - validated above
    except OSError as e:
        print(f"❌ Error: Invalid skill path '{user_skill_path}': {e}")
        return None

    # Double-check the resolved path is within the allowed skills root
    try:
        skill_path.relative_to(skills_root)
    except ValueError:
        print(f"❌ Error: Skill path escapes allowed skills directory: {skill_path}")
        print(f"   Allowed root: {skills_root}")
        return None

    # Validate skill folder exists
    if not skill_path.exists():
        print(f"❌ Error: Skill folder not found: {skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"❌ Error: Path is not a directory: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"❌ Error: SKILL.md not found in {skill_path}")
        return None

    # Run validation before packaging
    print("🔍 Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"❌ Validation failed: {message}")
        print("   Please fix the validation errors before packaging.")
        return None
    print(f"✅ {message}\n")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        # SECURITY: Validate path safety BEFORE resolution (prevents CWE-22)
        if not validate_path_safety(str(output_dir), allowed_base=Path.cwd()):
            print(f"❌ Error: Output path contains unsafe characters or escapes allowed directory")
            return None
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()

    skill_filename = output_path / f"{skill_name}.skill"

    # Create the .skill file (zip format)
    try:
        with zipfile.ZipFile(skill_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the skill directory
            for file_path in skill_path.rglob('*'):
                if file_path.is_file():
                    # Skip common exclusions
                    if file_path.name.startswith('.') or '__pycache__' in str(file_path):
                        continue
                    # Calculate the relative path within the zip
                    arcname = file_path.relative_to(skill_path.parent)
                    zipf.write(file_path, arcname)
                    print(f"  Added: {arcname}")

        print(f"\n✅ Successfully packaged skill to: {skill_filename}")
        return skill_filename

    except Exception as e:
        print(f"❌ Error creating .skill file: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python package_skill.py <path/to/skill-folder> [output-directory]")
        print("\nExample:")
        print("  python package_skill.py ~/.claude/skills/my-skill")
        print("  python package_skill.py ~/.claude/skills/my-skill ./dist")
        sys.exit(1)

    skill_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"📦 Packaging skill: {skill_path}")
    if output_dir:
        print(f"   Output directory: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
