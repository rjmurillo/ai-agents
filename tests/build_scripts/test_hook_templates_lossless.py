"""Lossless byte-identity for hook_templates.py's first render (ADR-109 B4).

Unlike agents/rules/skills, hooks has no mustache render step (module
docstring: "the compile is a byte copy... after a JSON-parseability check").
So there is no separate fixtures/ directory to keep in sync with a
transformation: the committed ``templates/hooks/<rel>`` tree IS the
fixture, and this test pins the three-way byte-identity chain
``templates/hooks/<rel>`` -> ``src/claude/hooks/<rel>`` (or
``src/claude/hooks.json``) -> ``.claude/hooks/<rel>`` (or
``.claude/hooks/hooks.json``, ``.claude/settings.json``) the compile step
plus the binplace step produce end to end, against the real repository
tree, per TASK-034 Acceptance Criteria: "the first render byte-identical
to today's committed files."

Independent pin on the corpus size (mirrors test_rule_templates_lossless.py's
CodeRabbit-motivated frozenset): the 13 executables, dispatch_groups.json,
and PreToolUse/markdownlint-safe-config.yaml, from `git ls-files .claude/hooks`
at HEAD (2026-09-15; TASK-034 Objective, "23 total... 13 executables...
hooks.json, dispatch_groups.json, and PreToolUse/markdownlint-safe-config.yaml").
"""

from __future__ import annotations

import stat
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_HOOK_TREE_FILES = frozenset(
    {
        "dispatch_groups.json",
        "invoke_dispatch_claude.py",
        "session-start.sh",
        "PreCompact/invoke_compact_checkpoint.py",
        "PreToolUse/_bootstrap.py",
        "PreToolUse/markdownlint-safe-config.yaml",
        "SessionEnd/invoke_memory_reflection.py",
        "SessionStart/invoke_checkout_freshness_check.py",
        "SessionStart/invoke_context_loader.py",
        "SessionStart/invoke_plugin_hook_drift_check.py",
        "SessionStart/plugin_hook_drift_model.py",
        "SessionStart/plugin_hook_drift_report.py",
        "SessionStart/plugin_hook_drift_safety.py",
        "SessionStart/plugin_hook_drift_state.py",
        "UserPromptSubmit/invoke_memory_recall.py",
    }
)


def test_expected_corpus_matches_committed_templates_tree() -> None:
    """The frozen expectation and the on-disk template tree agree (sans hooks.json)."""
    templates_root = _REPO_ROOT / "templates" / "hooks"
    on_disk = {
        p.relative_to(templates_root).as_posix()
        for p in templates_root.rglob("*")
        if p.is_file() and p.name not in {"hooks.json", "settings.tmpl"}
    }
    assert on_disk == EXPECTED_HOOK_TREE_FILES


def test_hooks_tree_files_byte_identical_across_the_chain() -> None:
    """templates/hooks/<rel> == src/claude/hooks/<rel> == .claude/hooks/<rel>."""
    for rel in sorted(EXPECTED_HOOK_TREE_FILES):
        template_bytes = (_REPO_ROOT / "templates" / "hooks" / rel).read_bytes()
        plugin_bytes = (_REPO_ROOT / "src" / "claude" / "hooks" / rel).read_bytes()
        install_bytes = (_REPO_ROOT / ".claude" / "hooks" / rel).read_bytes()
        assert template_bytes == plugin_bytes == install_bytes, rel


def test_hooks_json_byte_identical_at_plugin_root_and_install_path() -> None:
    """templates/hooks/hooks.json == src/claude/hooks.json == .claude/hooks/hooks.json."""
    template_bytes = (_REPO_ROOT / "templates" / "hooks" / "hooks.json").read_bytes()
    plugin_bytes = (_REPO_ROOT / "src" / "claude" / "hooks.json").read_bytes()
    install_bytes = (_REPO_ROOT / ".claude" / "hooks" / "hooks.json").read_bytes()
    assert template_bytes == plugin_bytes == install_bytes


def test_settings_byte_identical_direct_to_install_tree() -> None:
    """templates/hooks/settings.tmpl == .claude/settings.json (no plugin-tree hop)."""
    template_bytes = (_REPO_ROOT / "templates" / "hooks" / "settings.tmpl").read_bytes()
    install_bytes = (_REPO_ROOT / ".claude" / "settings.json").read_bytes()
    assert template_bytes == install_bytes
    assert not (_REPO_ROOT / "src" / "claude" / "settings.json").exists()


def test_session_start_sh_stays_executable_end_to_end() -> None:
    """The one executable-bit-sensitive file keeps its FULL mode through both hops.

    Compares the complete permission bits (``stat.S_IMODE``), not only the
    owner execute bit: a mode change from 0o755 to 0o700 still carries the
    owner execute bit but has silently dropped the group/other read and
    execute bits a checked-out clone (or another consumer) may rely on.
    """
    template_mode = stat.S_IMODE(
        (_REPO_ROOT / "templates" / "hooks" / "session-start.sh").stat().st_mode
    )
    plugin_mode = stat.S_IMODE(
        (_REPO_ROOT / "src" / "claude" / "hooks" / "session-start.sh").stat().st_mode
    )
    install_mode = stat.S_IMODE(
        (_REPO_ROOT / ".claude" / "hooks" / "session-start.sh").stat().st_mode
    )
    assert template_mode == plugin_mode == install_mode
    assert template_mode & 0o100  # still executable, not just byte-for-byte equal
