"""CLI for semantic-hooks installation and management."""

import argparse
import json
import shutil
import sys
from pathlib import Path


CONFIG_DIR = Path.home() / ".semantic-hooks"
CLAUDE_HOOKS_DIR = Path.home() / ".claude" / "hooks"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

# Semantic-hooks hook filenames (used for filtering)
SEMANTIC_HOOKS_FILENAMES = frozenset({
    "pre_tool_use.py",
    "post_tool_use.py",
    "post_response.py",
    "session_start.py",
    "session_end.py",
    "pre_compact.py",
})


def _find_hooks_dir() -> Path | None:
    """Find the hooks directory using multiple strategies.

    Tries:
    1. Development layout (source tree)
    2. Installed shared data location
    3. Package data via importlib.resources

    Returns:
        Path to hooks directory or None if not found.
    """
    # Strategy 1: Development layout (editable install or source tree)
    dev_hooks = Path(__file__).parent.parent.parent / "hooks"
    if dev_hooks.is_dir() and (dev_hooks / "pre_tool_use.py").exists():
        return dev_hooks

    # Strategy 2: Installed shared data location (varies by platform)
    # Common locations: /usr/share, /usr/local/share, ~/.local/share
    import site
    for base in [sys.prefix, site.USER_BASE] if hasattr(site, 'USER_BASE') else [sys.prefix]:
        if base:
            shared_hooks = Path(base) / "share" / "semantic-hooks" / "hooks"
            if shared_hooks.is_dir() and (shared_hooks / "pre_tool_use.py").exists():
                return shared_hooks

    return None


def _find_templates_dir() -> Path | None:
    """Find the templates directory using multiple strategies."""
    # Strategy 1: Development layout
    dev_templates = Path(__file__).parent.parent.parent / "templates"
    if dev_templates.is_dir():
        return dev_templates

    # Strategy 2: Installed shared data location
    import site
    for base in [sys.prefix, site.USER_BASE] if hasattr(site, 'USER_BASE') else [sys.prefix]:
        if base:
            shared_templates = Path(base) / "share" / "semantic-hooks" / "templates"
            if shared_templates.is_dir():
                return shared_templates

    return None


def cmd_install(args: argparse.Namespace) -> int:
    """Install hooks to Claude Code."""
    print("Installing semantic-hooks for Claude Code...")

    # Create config directory
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Copy default config if not exists
    config_file = CONFIG_DIR / "config.yaml"
    if not config_file.exists():
        default_config = """\
# Semantic Hooks Configuration

embedding:
  provider: openai
  model: text-embedding-3-small

thresholds:
  safe: 0.4
  transitional: 0.6
  risk: 0.85

guard:
  block_in_danger: false
  inject_bridge_context: true
  trajectory_window: 5

memory:
  path: ~/.semantic-hooks/memory.db
  max_nodes: 10000

logging:
  level: INFO
  file: ~/.semantic-hooks/hooks.log
"""
        config_file.write_text(default_config)
        print(f"  ✓ Created config: {config_file}")

    # Create Claude hooks directory
    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    # Find hooks directory
    hooks_dir = _find_hooks_dir()
    if hooks_dir is None:
        print("  ✗ Could not find hooks directory.")
        print("    Ensure semantic-hooks is properly installed.")
        return 1

    # Copy hook scripts
    hooks_to_install = list(SEMANTIC_HOOKS_FILENAMES)

    for hook_name in hooks_to_install:
        src = hooks_dir / hook_name
        dst = CLAUDE_HOOKS_DIR / hook_name
        if src.exists():
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            print(f"  ✓ Installed hook: {hook_name}")
        else:
            print(f"  ⚠ Hook not found: {src}")

    # Update Claude settings
    if not _update_claude_settings(args.force):
        print("  ⚠ Could not update Claude settings automatically")
        print(f"    Add hooks manually to: {CLAUDE_SETTINGS}")
        return 1

    print(f"  ✓ Updated Claude settings: {CLAUDE_SETTINGS}")
    print("\n✓ Installation complete!")
    print("\nRestart Claude Code to activate hooks.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall hooks from Claude Code."""
    print("Uninstalling semantic-hooks from Claude Code...")

    # Remove hook scripts
    hooks_to_remove = [
        "pre_tool_use.py",
        "post_tool_use.py",
        "post_response.py",
        "session_start.py",
        "session_end.py",
        "pre_compact.py",
    ]

    for hook_name in hooks_to_remove:
        hook_path = CLAUDE_HOOKS_DIR / hook_name
        if hook_path.exists():
            hook_path.unlink()
            print(f"  ✓ Removed hook: {hook_name}")

    # Remove from Claude settings
    if CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text())
            if "hooks" in settings:
                # Remove only our hooks, preserve others
                for event in ["SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "PostResponse", "PreCompact"]:
                    if event in settings["hooks"]:
                        settings["hooks"][event] = [
                            h for h in settings["hooks"][event]
                            if not _is_semantic_hooks_entry(h)
                        ]
                        if not settings["hooks"][event]:
                            del settings["hooks"][event]
                if not settings["hooks"]:
                    del settings["hooks"]
                CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
                print("  ✓ Updated Claude settings")
        except Exception as e:
            print(f"  ⚠ Could not update settings: {e}")

    if args.purge:
        # Remove config and memory
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)
            print(f"  ✓ Removed config directory: {CONFIG_DIR}")

    print("\n✓ Uninstallation complete!")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show installation status."""
    print("Semantic Hooks Status")
    print("=" * 40)

    # Check config
    config_file = CONFIG_DIR / "config.yaml"
    print(f"\nConfig: {config_file}")
    print(f"  Exists: {'✓' if config_file.exists() else '✗'}")

    # Check memory
    memory_file = CONFIG_DIR / "memory.db"
    print(f"\nMemory: {memory_file}")
    print(f"  Exists: {'✓' if memory_file.exists() else '✗'}")
    if memory_file.exists():
        import sqlite3
        try:
            with sqlite3.connect(memory_file) as conn:
                count = conn.execute("SELECT COUNT(*) FROM semantic_nodes").fetchone()[0]
            print(f"  Nodes: {count}")
        except Exception:
            print("  Nodes: (error reading)")

    # Check hooks
    print(f"\nClaude Hooks: {CLAUDE_HOOKS_DIR}")
    hooks = ["pre_tool_use.py", "post_tool_use.py", "post_response.py", "session_start.py", "session_end.py", "pre_compact.py"]
    for hook in hooks:
        hook_path = CLAUDE_HOOKS_DIR / hook
        status = "✓" if hook_path.exists() else "✗"
        print(f"  {hook}: {status}")

    # Check settings
    print(f"\nClaude Settings: {CLAUDE_SETTINGS}")
    if CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text())
            if "hooks" in settings:
                print("  Hooks configured: ✓")
                for event in settings.get("hooks", {}):
                    print(f"    - {event}")
            else:
                print("  Hooks configured: ✗")
        except Exception:
            print("  (error reading)")
    else:
        print("  Exists: ✗")

    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    """View or export semantic tree."""
    from semantic_hooks.memory import SemanticMemory

    memory = SemanticMemory()

    if args.export:
        tree = memory.export_tree(session_id=args.session)
        output = json.dumps(tree, indent=2)
        if args.export == "-":
            print(output)
        else:
            Path(args.export).write_text(output)
            print(f"Exported to: {args.export}")
        return 0

    # Show tree
    nodes = memory.get_recent(n=args.limit or 20, session_id=args.session)
    if not nodes:
        print("No nodes in memory.")
        return 0

    print(f"Recent Semantic Nodes ({len(nodes)})")
    print("=" * 60)
    for node in reversed(nodes):  # Chronological order
        zone_emoji = {
            "safe": "🟢",
            "transitional": "🟡",
            "risk": "🟠",
            "danger": "🔴",
        }.get(node.zone.value, "⚪")

        print(f"\n{zone_emoji} {node.topic}")
        print(f"   ΔS={node.delta_s:.3f} | {node.lambda_observe.value} | {node.module_used}")
        print(f"   {node.insight[:80]}{'...' if len(node.insight) > 80 else ''}")
        print(f"   {node.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """View or update configuration."""
    import yaml

    config_file = CONFIG_DIR / "config.yaml"

    if not config_file.exists():
        print(f"Config not found: {config_file}")
        print("Run 'semantic-hooks install --claude' first.")
        return 1

    config = yaml.safe_load(config_file.read_text()) or {}

    if args.show:
        print(yaml.dump(config, default_flow_style=False))
        return 0

    # Update values
    updated = False
    if args.delta_s_threshold is not None:
        config.setdefault("thresholds", {})["risk"] = args.delta_s_threshold
        updated = True

    if args.embedding_provider:
        config.setdefault("embedding", {})["provider"] = args.embedding_provider
        updated = True

    if args.block_in_danger is not None:
        config.setdefault("guard", {})["block_in_danger"] = args.block_in_danger
        updated = True

    if updated:
        config_file.write_text(yaml.dump(config, default_flow_style=False))
        print(f"Updated: {config_file}")
    else:
        print("No changes specified. Use --show to view current config.")

    return 0


def _is_semantic_hooks_entry(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to semantic-hooks.

    Args:
        hook_entry: Hook configuration dict from Claude settings.

    Returns:
        True if this is a semantic-hooks entry, False otherwise.
    """
    command = str(hook_entry.get("hooks", [{}])[0].get("command", ""))
    # Check if the command references any of our specific hook filenames
    return any(filename in command for filename in SEMANTIC_HOOKS_FILENAMES)


def _update_claude_settings(force: bool = False) -> bool:
    """Update Claude settings.json with hook configuration."""
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text())
        except json.JSONDecodeError:
            if not force:
                return False
            settings = {}

    hooks_config = settings.setdefault("hooks", {})

    # Define our hooks
    hook_definitions = {
        "SessionStart": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/session_start.py",
            }],
        },
        "PreToolUse": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/pre_tool_use.py",
                "timeout": 5000,
            }],
        },
        "PostToolUse": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/post_tool_use.py",
                "timeout": 3000,
            }],
        },
        "PostResponse": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/post_response.py",
                "timeout": 3000,
            }],
        },
        "PreCompact": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/pre_compact.py",
            }],
        },
        "SessionEnd": {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"python3 {CLAUDE_HOOKS_DIR}/session_end.py",
            }],
        },
    }

    # Add/update hooks
    for event, definition in hook_definitions.items():
        if event not in hooks_config:
            hooks_config[event] = []

        # Remove only existing semantic-hooks entries (not other hooks in .claude/hooks/)
        hooks_config[event] = [
            h for h in hooks_config[event]
            if not _is_semantic_hooks_entry(h)
        ]

        # Add our hook
        hooks_config[event].append(definition)

    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="semantic-hooks",
        description="Semantic tension tracking hooks for Claude Code CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    install_parser = subparsers.add_parser("install", help="Install hooks")
    install_parser.add_argument("--claude", action="store_true", help="Install for Claude Code")
    install_parser.add_argument("--force", action="store_true", help="Overwrite existing config")
    install_parser.set_defaults(func=cmd_install)

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall hooks")
    uninstall_parser.add_argument("--claude", action="store_true", help="Uninstall from Claude Code")
    uninstall_parser.add_argument("--purge", action="store_true", help="Also remove config and memory")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # status
    status_parser = subparsers.add_parser("status", help="Show installation status")
    status_parser.set_defaults(func=cmd_status)

    # tree
    tree_parser = subparsers.add_parser("tree", help="View semantic tree")
    tree_parser.add_argument("--export", metavar="FILE", help="Export to JSON file (- for stdout)")
    tree_parser.add_argument("--session", help="Filter by session ID")
    tree_parser.add_argument("--limit", type=int, help="Limit number of nodes")
    tree_parser.set_defaults(func=cmd_tree)

    # config
    config_parser = subparsers.add_parser("config", help="View/update configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current config")
    config_parser.add_argument("--delta-s-threshold", type=float, help="Set ΔS threshold")
    config_parser.add_argument("--embedding-provider", choices=["openai", "local"], help="Set embedding provider")
    config_parser.add_argument("--block-in-danger", type=lambda x: x.lower() == "true", help="Block in danger zone (true/false)")
    config_parser.set_defaults(func=cmd_config)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
