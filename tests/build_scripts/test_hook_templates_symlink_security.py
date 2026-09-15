"""CWE-22/CWE-59 defense for build/scripts/hook_templates.py.

Split out on its own (not appended to test_hook_templates.py, which
approaches the taste-lint 500-line file-size ceiling), mirroring
test_rule_templates_symlink_security.py's split precedent.

Covers: a symlinked ANCESTOR of templates/hooks/ (templates itself), a
symlinked LEAF template or target, and a target that resolves outside the
repository through a real (non-symlink) ancestor. hook_templates.py has no
partials directory, so there is no partials-specific case here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import hook_templates  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_source_root_symlink_ancestor_exits_2(tmp_path: Path) -> None:
    """templates symlinked outside repo, hooks/guard.py real: exit 2, no write.

    The leaf-only ``is_symlink()`` check on a candidate template inspects
    only its final path component. When an ANCESTOR (``templates`` itself)
    is the symlink, a plain glob still finds a regular file reached
    through it. Only the resolved-containment check on the source root
    (checked once, ahead of every candidate) catches it.
    """
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-hooks-templates-outside"
    (outside / "hooks").mkdir(parents=True)
    (outside / "hooks" / "leaked.py").write_text("print('leaked')\n", encoding="utf-8")

    templates_link = root / "templates"
    try:
        templates_link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert not (root / "src" / "claude" / "hooks").exists()


def test_source_leaf_symlink_refused(tmp_path: Path) -> None:
    """A template file that is itself a symlink is refused, not rendered."""
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-hooks-leaf-outside.py"
    outside.write_text("print('leaked')\n", encoding="utf-8")

    hooks_dir = root / "templates" / "hooks"
    hooks_dir.mkdir(parents=True)
    link = hooks_dir / "guard.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    assert "guard.py" not in hook_templates.discover(root)
    errors = hook_templates.discover_errors(root)
    assert any("symlink" in e for e in errors)


def test_target_leaf_symlink_refused(tmp_path: Path) -> None:
    """A pre-existing symlink at the render target is refused (CWE-59)."""
    root = fake_repo(tmp_path)
    (root / "templates" / "hooks").mkdir(parents=True)
    (root / "templates" / "hooks" / "guard.py").write_text("print('ok')\n", encoding="utf-8")

    outside = tmp_path.parent / f"{tmp_path.name}-hooks-target-outside.py"
    outside.write_text("print('pwned')\n", encoding="utf-8")
    target_dir = root / "src" / "claude" / "hooks"
    target_dir.mkdir(parents=True)
    link = target_dir / "guard.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert outside.read_text(encoding="utf-8") == "print('pwned')\n"


def test_settings_target_symlink_refused(tmp_path: Path) -> None:
    """A symlinked .claude/settings.json target is refused, never written through."""
    root = fake_repo(tmp_path)
    (root / "templates" / "hooks").mkdir(parents=True)
    (root / "templates" / "hooks" / "settings.tmpl").write_text("{}", encoding="utf-8")

    outside = tmp_path.parent / f"{tmp_path.name}-settings-outside.json"
    outside.write_text('{"pwned": true}', encoding="utf-8")
    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True)
    link = claude_dir / "settings.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert outside.read_text(encoding="utf-8") == '{"pwned": true}'


def test_target_outside_repository_root_exits_2(tmp_path: Path, monkeypatch) -> None:
    """A target whose resolved path escapes the repository root is refused.

    ``src/claude`` is a real (non-symlink) directory that is itself a
    symlink target's ancestor: simulated here by pointing ``src`` at a
    directory outside the repository, so ``src/claude/hooks``'s resolved
    path escapes ``repo_root`` even though no single path component is a
    symlink to inspect directly.
    """
    root = fake_repo(tmp_path)
    (root / "templates" / "hooks").mkdir(parents=True)
    (root / "templates" / "hooks" / "guard.py").write_text("print('ok')\n", encoding="utf-8")

    outside_src = tmp_path.parent / f"{tmp_path.name}-src-outside"
    outside_src.mkdir()
    try:
        (root / "src").symlink_to(outside_src)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = hook_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert not (outside_src / "claude").exists()
