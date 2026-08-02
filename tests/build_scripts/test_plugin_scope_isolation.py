"""Plugin instruction files must not universalize all-internal-scope rules (issue #4317)."""
from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_INSTRUCTIONS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "copilot-cli" / "instructions"
)
RULES_DIR = Path(__file__).parent.parent.parent / ".claude" / "rules"

_INTERNAL_PREFIXES = (".agents/", ".claude/", ".serena/")


def _is_all_internal(paths: list[str]) -> bool:
    return all(any(p.startswith(pre) for pre in _INTERNAL_PREFIXES) for p in paths)


def _load_frontmatter(md_file: Path) -> dict:
    text = md_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    return yaml.safe_load(text[3:end]) or {}


class TestPluginScopeIsolation:
    """Rules with all-internal paths must not appear in plugin with applyTo:'**'."""

    def test_no_all_internal_rule_has_universal_scope_in_plugin(self) -> None:
        if not PLUGIN_INSTRUCTIONS_DIR.exists():
            return
        for rule_src in RULES_DIR.glob("*.md"):
            fm = _load_frontmatter(rule_src)
            paths = fm.get("paths", fm.get("applyTo", None))
            if paths is None:
                continue
            if isinstance(paths, str):
                paths = [paths]
            if not _is_all_internal(paths):
                continue
            # This rule has all-internal source paths; it must NOT be in the plugin
            plugin_file = PLUGIN_INSTRUCTIONS_DIR / (
                rule_src.stem + ".instructions.md"
            )
            assert not plugin_file.exists(), (
                f"{rule_src.name} has all-internal paths {paths!r} "
                f"but {plugin_file} exists in the plugin"
            )

    def test_known_internal_rules_absent_from_plugin(self) -> None:
        """Regression guard: governance, secret-redaction, session-logs must not be in plugin."""
        for name in ("governance", "secret-redaction", "session-logs"):
            plugin_file = PLUGIN_INSTRUCTIONS_DIR / f"{name}.instructions.md"
            assert not plugin_file.exists(), (
                f"{plugin_file} should not be in the plugin (all-internal scope)"
            )
