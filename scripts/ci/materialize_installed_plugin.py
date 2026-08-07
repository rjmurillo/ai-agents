#!/usr/bin/env python3
"""Lay out the plugin the way the real installer does, for CI guards.

Kept out of workflow YAML per ADR-006, and shared so the vanilla rows and the
positive rows cannot drift into materializing different layouts, which is how
a guard ends up testing something the customer never runs.

The layout mirrors what `copilot plugin install` produces, which
tests/e2e/test_installed_plugin_hook_e2e.py already encodes as
``~/.copilot/installed-plugins/<marketplace>/<plugin>``.

The consumer directory is deliberately NOT this repository. Every regression
in this class has hidden in the maintainer environment, where the ai-agents
checkout makes paths resolve that would not resolve on a user's machine.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def materialize(plugin_source: Path, install_root: Path) -> None:
    if not plugin_source.is_dir():
        raise SystemExit(f"plugin source is not a directory: {plugin_source}")
    marker = plugin_source / ".claude-plugin" / "plugin.json"
    if not marker.is_file():
        raise SystemExit(f"plugin source has no manifest at {marker}")
    if install_root.exists():
        shutil.rmtree(install_root)
    install_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, install_root)
    if not (install_root / "hooks" / "hooks.json").is_file():
        raise SystemExit(f"materialized plugin has no hooks.json under {install_root}")


def create_consumer_repo(consumer_cwd: Path) -> None:
    """A scratch git repo that is not this repository."""
    consumer_cwd.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", str(consumer_cwd)],
        check=True,
        capture_output=True,
    )
    (consumer_cwd / "README.md").write_text("consumer scratch repo\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-source", required=True, type=Path)
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--consumer-cwd", required=True, type=Path)
    args = parser.parse_args(argv)

    materialize(args.plugin_source, args.install_root)
    create_consumer_repo(args.consumer_cwd)
    print(f"Materialized {args.plugin_source} -> {args.install_root}")
    print(f"Consumer repo at {args.consumer_cwd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
