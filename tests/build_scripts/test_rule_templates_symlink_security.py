"""CWE-22/CWE-59 defense: a symlinked ANCESTOR of ``templates/rules/``.

Split out on its own (not appended to ``test_rule_templates.py``, which sits
at the taste-lint 500-line file-size ceiling) rather than grown in place, the
same seam-splitting precedent ``test_skill_templates_symlink_security.py``
already used for ``skill_templates.py``.

CodeRabbit review, PR #5775: ``_name_validation_error`` (``rule_templates.py``)
checked whether the candidate ``templates/rules/<name>.md`` FILE itself is a
symlink, but never checked whether an ANCESTOR directory (``templates``
itself) is a symlink to somewhere outside the repository. ``Path.is_symlink()``
and ``Path.is_file()`` on a path with a symlinked parent both resolve the
parent transparently and report on the real leaf, so a candidate reached
through such an ancestor passed every existing check and would have been
rendered. The fix resolves the source root ``templates/rules/`` and each
candidate's own path, rejecting anything that resolves outside the resolved
repository root.

The same ancestor-symlink shape also reaches ``templates/rules/partials``: a
real ``partials/`` directory sitting under a symlinked ``templates/rules``
does not trip ``_partials_dir_error``'s leaf-only ``is_symlink()`` check
either, only its resolved-containment branch.
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

import rule_templates  # noqa: E402


def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repository with git init."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_source_root_symlink_ancestor_exits_2(tmp_path: Path) -> None:
    """templates symlinked outside repo, rules/<name>.md real: exit 2, no write.

    The leaf-only ``tmpl_path.is_symlink()`` check in
    ``_name_validation_error`` inspects only the candidate's final path
    component. When an ANCESTOR (``templates`` itself) is the symlink,
    ``_iter_template_candidates`` still globs a regular file reached
    through it, and that file's ``is_symlink()``/``is_file()`` both
    report on the real leaf, transparently following the symlinked
    parent. Only the resolved-containment check on the source root and
    the candidate's own resolved path (added for this test) catches it.
    """
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-templates-outside"
    (outside / "rules").mkdir(parents=True)
    (outside / "rules" / "leaked.md").write_text("leaked body\n", encoding="utf-8")

    templates_link = root / "templates"
    try:
        templates_link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert "leaked" not in rule_templates.discover(root)
    assert not (root / "src" / "claude" / "rules").exists()


def test_partials_dir_error_direct_containment_branch(tmp_path: Path) -> None:
    """_partials_dir_error's containment branch, called directly.

    A real (non-symlink) directory outside the repo root isolates the
    resolved-containment branch from the ``is_symlink()`` leaf check
    that would otherwise fire first (as in
    ``test_partials_dir_symlink_exits_2_nothing_written`` in
    ``test_rule_templates.py``, where ``partials`` itself is the
    symlink). Fails if the containment check is removed.
    """
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-partials-direct-outside"
    outside.mkdir()

    error = rule_templates._partials_dir_error(root, outside)

    assert error is not None
    assert "outside the repository root" in error
    assert "resolves to" in error


def test_partials_dir_ancestor_symlink_exits_2_via_containment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """templates/rules is a symlinked ancestor of a real external partials/ dir.

    ``partials`` itself is a real directory reached through the
    symlinked ``templates/rules`` ancestor, so ``_partials_dir_error``'s
    leaf-only ``is_symlink()`` check does not fire; its
    resolved-containment branch is what catches this. ``compile_all``
    checks the partials directory before ``discover_errors`` runs, so
    this end-to-end layout trips ``_partials_dir_error``'s containment
    branch, not ``_name_validation_error``'s source-root check (see
    ``test_source_root_symlink_ancestor_exits_2`` above), even though
    the same ancestor symlink would trip that check too if
    ``discover_errors`` ever ran for this layout.
    """
    root = fake_repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-rules-ancestor-outside"
    (outside / "partials").mkdir(parents=True)

    templates_dir = root / "templates"
    templates_dir.mkdir()
    rules_link = templates_dir / "rules"
    try:
        rules_link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create symlink on this platform")

    result = rule_templates.compile_all(root, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert not (root / "src" / "claude" / "rules").exists()
    err = capsys.readouterr().err
    assert "templates/rules/partials resolves to" in err
    assert "outside the repository root" in err
