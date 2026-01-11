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


def validate_and_resolve_path(path_str: str, allowed_base: Path) -> Path | None:
    """
    Validate that a path string is safe and resolve it against a trusted base directory.
    This prevents directory traversal by ensuring the final path stays within allowed_base.

    Args:
        path_str: Path string provided by the user.
        allowed_base: Base directory that the resolved path must remain within.

    Returns:
        A resolved Path object if the path is safe, or None otherwise.
    """
    # Normalize inputs
    raw = str(path_str)
    base = allowed_base.resolve()

    try:
        # Treat all user input as relative to the trusted base and resolve it.
        # Using strict=False so that existence of the path is not required for validation.
        resolved_path = (base / raw).resolve(strict=False)

        # Ensure the resolved path is contained within the allowed base
        resolved_path.relative_to(base)
        return resolved_path
    except (ValueError, OSError):
        # Any resolution or containment error means the path is unsafe
        return None


def package_skill(skill_path, output_dir=None):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the .skill file (defaults to current directory)

    Returns:
        Path to the created .skill file, or None if error
    """
    # SECURITY: Validate and resolve skill_path to trusted base (prevents CWE-22)
    skills_root = (Path.home() / ".claude" / "skills").resolve()

    # Step 1: Validate path safety and resolve to a single trusted path
    resolved_skill_path = validate_and_resolve_path(str(skill_path), skills_root)
    if resolved_skill_path is None:
        print(f"❌ Error: Skill path contains unsafe characters or escapes allowed directory")
        print(f"   Allowed root: {skills_root}")
        return None

    # Step 2: Validate skill folder exists (using validated path)
    if not resolved_skill_path.exists():
        print(f"❌ Error: Skill folder not found: {resolved_skill_path}")
        return None

    if not resolved_skill_path.is_dir():
        print(f"❌ Error: Path is not a directory: {resolved_skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = resolved_skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"❌ Error: SKILL.md not found in {resolved_skill_path}")
        return None

    # Run validation before packaging
    print("🔍 Validating skill...")
    valid, message = validate_skill(resolved_skill_path)
    if not valid:
        print(f"❌ Validation failed: {message}")
        print("   Please fix the validation errors before packaging.")
        return None
    print(f"✅ {message}\n")

    # Determine output location
    skill_name = resolved_skill_path.name
    if output_dir:
        # SECURITY: Validate and resolve output_dir to trusted base
        base = Path.cwd().resolve()
        resolved_output_path = validate_and_resolve_path(str(output_dir), allowed_base=base)
        if resolved_output_path is None:
            print(f"❌ Error: Output path contains unsafe characters or escapes allowed directory")
            return None

        resolved_output_path.mkdir(parents=True, exist_ok=True)
    else:
        resolved_output_path = Path.cwd()

    skill_filename = resolved_output_path / f"{skill_name}.skill"

    # Create the .skill file (zip format)
    try:
        with zipfile.ZipFile(skill_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the skill directory (using validated path)
            for file_path in resolved_skill_path.rglob('*'):
                if file_path.is_file():
                    # Skip common exclusions
                    if file_path.name.startswith('.') or '__pycache__' in str(file_path):
                        continue
                    # Calculate the relative path within the zip
                    arcname = file_path.relative_to(resolved_skill_path.parent)
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
