"""Issue #6506: publishing never lands in a redirected directory or reads a link.

``atomic_write.publish_bytes_atomically`` swaps one directory entry, so a
symlinked ANCESTOR directory still redirects where that entry lives. The
primitive now refuses a symlinked ancestor below the repository root, and
``generate_hooks_emit._copy_script`` reads its hook source without following
a symlink. Companion to ``test_generator_no_follow_writes.py``, which covers
a symlink at the destination itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import atomic_write  # noqa: E402
import generate_hooks_emit  # noqa: E402

_EXTERNAL_BYTES = b"external file, must never change\n"


def _external(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "external.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(_EXTERNAL_BYTES)
    return outside


def _plant_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _fake_checkout(tmp_path: Path) -> Path:
    """A directory that find_repo_root treats as a checkout."""
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    return root


def test_find_repo_root_returns_nearest_ancestor_with_git(tmp_path: Path) -> None:
    root = _fake_checkout(tmp_path)

    assert atomic_write.find_repo_root(root / "a" / "b" / "file.md") == root


def test_find_repo_root_accepts_a_git_file_from_a_linked_worktree(tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    (root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")

    assert atomic_write.find_repo_root(root / "x" / "file.md") == root


def test_find_repo_root_is_none_outside_a_checkout(tmp_path: Path) -> None:
    assert atomic_write.find_repo_root(tmp_path / "scratch" / "file.md") is None


def test_find_repo_root_skips_a_symlinked_ancestor_that_borrows_a_git_dir(
    tmp_path: Path,
) -> None:
    """Edge: a link to another repo must not become the root it hides behind."""
    root = _fake_checkout(tmp_path)
    other = tmp_path / "other-repo"
    (other / ".git").mkdir(parents=True)
    _plant_symlink(root / "linked", other)

    assert atomic_write.find_repo_root(root / "linked" / "file.md") == root


def test_publish_refuses_a_symlinked_ancestor_directory(tmp_path: Path) -> None:
    """The final-component swap alone still lands in a redirected directory."""
    root = _fake_checkout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "inside").mkdir()
    _plant_symlink(root / "inside" / "link", outside)
    target = root / "inside" / "link" / "generated.md"

    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(target, b"new\n")

    assert list(outside.iterdir()) == []


def test_publish_preserving_mode_refuses_a_symlinked_ancestor_directory(
    tmp_path: Path,
) -> None:
    root = _fake_checkout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _plant_symlink(root / "link", outside)

    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_preserving_mode(root / "link" / "x.md", b"new\n")

    assert list(outside.iterdir()) == []


def test_publish_refuses_when_the_parent_resolves_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense in depth: a link the ancestor walk misses still cannot escape."""
    root = _fake_checkout(tmp_path)
    (root / "inside").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(atomic_write, "reject_symlinked_ancestors", lambda *_a: None)
    _plant_symlink(root / "inside" / "link", outside)

    with pytest.raises(OSError, match="outside the repository"):
        atomic_write.publish_bytes_atomically(root / "inside" / "link" / "x.md", b"new\n")

    assert list(outside.iterdir()) == []


def test_publish_inside_a_checkout_without_links_succeeds(tmp_path: Path) -> None:
    root = _fake_checkout(tmp_path)
    (root / "a" / "b").mkdir(parents=True)
    target = root / "a" / "b" / "file.md"

    atomic_write.publish_bytes_atomically(target, b"new\n")

    assert target.read_bytes() == b"new\n"


def test_publish_allows_a_missing_ancestor_chain_inside_a_checkout(tmp_path: Path) -> None:
    """A missing directory is not a link; the temp write reports it as before."""
    root = _fake_checkout(tmp_path)

    with pytest.raises(FileNotFoundError):
        atomic_write.publish_bytes_atomically(root / "missing" / "file.md", b"new\n")


def test_publish_outside_any_checkout_is_not_confined(tmp_path: Path) -> None:
    target = tmp_path / "scratch" / "file.md"
    target.parent.mkdir()

    atomic_write.publish_bytes_atomically(target, b"new\n")

    assert target.read_bytes() == b"new\n"


def test_copy_script_refuses_a_symlinked_source(tmp_path: Path) -> None:
    """A symlinked hook source would ship bytes from outside the plugin tree."""
    external = _external(tmp_path)
    source = tmp_path / "src" / "hook.py"
    _plant_symlink(source, external)
    target = tmp_path / "out" / "hook.py"

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="cannot read hook script"):
        generate_hooks_emit._copy_script(source, target, matcher=None, what_if=False)

    assert not target.exists()


def test_copy_script_with_matcher_refuses_a_symlinked_source(tmp_path: Path) -> None:
    external = _external(tmp_path)
    source = tmp_path / "src" / "hook.py"
    _plant_symlink(source, external)
    target = tmp_path / "out" / "hook.py"

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="cannot read hook script"):
        generate_hooks_emit._copy_script(source, target, matcher="Bash", what_if=False)

    assert not target.exists()


def test_copy_script_reports_a_missing_source_as_a_generation_error(tmp_path: Path) -> None:
    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="cannot read hook script"):
        generate_hooks_emit._copy_script(
            tmp_path / "gone.py", tmp_path / "out" / "hook.py", matcher=None, what_if=False
        )


def test_copy_script_with_matcher_still_normalizes_crlf_source(tmp_path: Path) -> None:
    """Regression guard: the no-follow read keeps the LF output of read_text."""
    source = tmp_path / "src" / "hook.py"
    source.parent.mkdir()
    source.write_bytes(b"print('a')\r\nprint('b')\r\n")
    target = tmp_path / "out" / "hook.py"

    generate_hooks_emit._copy_script(source, target, matcher="Bash", what_if=False)

    assert b"\r" not in target.read_bytes()


def test_nested_git_dir_behind_a_planted_link_does_not_become_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link to a directory with its own ``.git`` must not move the root (#6506).

    ``root/link`` points at ``other``. ``other/sub`` holds a ``.git``, so a
    nearest-ancestor walk alone would call ``root/link/sub`` the root, find no
    ancestor to refuse, and accept a write that lands in ``other``. Anchoring to
    the working directory's checkout keeps ``root`` as the root.
    """
    root = _fake_checkout(tmp_path)
    other = tmp_path / "other"
    (other / "sub" / ".git").mkdir(parents=True)
    _plant_symlink(root / "link", other)
    monkeypatch.chdir(root)
    target = root / "link" / "sub" / "generated.md"

    assert atomic_write.find_repo_root(target) == root
    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(target, b"new\n")

    assert list((other / "sub").iterdir()) == [other / "sub" / ".git"]


def test_nested_git_dir_behind_a_planted_link_is_refused_when_cwd_is_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cwd anchor is absent here, so the fallback walk must not trust the link (#6506).

    ``repo/link`` points at ``outside``; ``outside/sub`` holds its own ``.git``.
    With the cwd in an unrelated directory, the nearest ``.git`` ancestor of the
    target is ``repo/link/sub``. The outermost ``.git`` ancestor, ``repo``, is the
    root instead, so the planted link is a refused ancestor.
    """
    repo = _fake_checkout(tmp_path / "repo")
    outside = tmp_path / "outside"
    (outside / "sub" / ".git").mkdir(parents=True)
    _plant_symlink(repo / "link", outside)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    target = repo / "link" / "sub" / "y.txt"

    assert atomic_write.find_repo_root(target) == repo
    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(target, b"new\n")

    assert not (outside / "sub" / "y.txt").exists()


def test_a_link_below_a_nested_checkout_is_refused_when_cwd_is_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link inside a submodule-style checkout is refused under the outer root too."""
    repo = _fake_checkout(tmp_path / "repo")
    (repo / "sub" / ".git").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    _plant_symlink(repo / "sub" / "link", outside)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(repo / "sub" / "link" / "y.txt", b"new\n")

    assert list(outside.iterdir()) == []


def test_a_nested_checkout_without_links_keeps_the_nearest_root_when_cwd_is_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative case: a legitimate submodule-style layout is not re-rooted."""
    repo = _fake_checkout(tmp_path / "repo")
    sub = repo / "sub"
    (sub / ".git").mkdir(parents=True)
    (sub / "d").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    target = sub / "d" / "file.md"

    assert atomic_write.find_repo_root(target) == sub
    atomic_write.publish_bytes_atomically(target, b"new\n")
    assert target.read_bytes() == b"new\n"


def test_find_repo_root_falls_back_to_the_nearest_git_when_outside_the_cwd_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    here = _fake_checkout(tmp_path / "here")
    there = _fake_checkout(tmp_path / "there")
    monkeypatch.chdir(here)

    assert atomic_write.find_repo_root(there / "a" / "file.md") == there


def test_find_repo_root_uses_the_cwd_checkout_when_the_cwd_is_its_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fake_checkout(tmp_path)
    monkeypatch.chdir(root)

    assert atomic_write.find_repo_root(root / "file.md") == root


def test_a_symlinked_checkout_root_is_not_confined(tmp_path: Path) -> None:
    """Pins the accepted limit: a root reached through a link has no root."""
    real = _fake_checkout(tmp_path)
    alias = tmp_path / "alias"
    _plant_symlink(alias, real)
    (real / "d").mkdir()

    assert atomic_write.find_repo_root(alias / "d" / "file.md") is None


# --- production path: _resolve_script_path hands _copy_script a resolved path ---


def _hook_source(tmp_path: Path) -> Path:
    source = tmp_path / "hooks_src"
    (source / "PreToolUse").mkdir(parents=True)
    return source


def test_resolve_script_path_refuses_an_in_tree_symlinked_leaf(tmp_path: Path) -> None:
    """``resolve`` would hide the link; the unresolved leaf must be checked first."""
    source = _hook_source(tmp_path)
    (source / "private.py").write_text("SECRET = 1\n", encoding="utf-8")
    _plant_symlink(source / "PreToolUse" / "hook.py", Path("..") / "private.py")

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="symlink"):
        generate_hooks_emit._resolve_script_path(
            source, "python3 .claude/hooks/PreToolUse/hook.py", "PreToolUse"
        )


def test_resolve_script_path_refuses_a_dangling_symlinked_leaf(tmp_path: Path) -> None:
    source = _hook_source(tmp_path)
    _plant_symlink(source / "PreToolUse" / "hook.py", Path("..") / "gone.py")

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="symlink"):
        generate_hooks_emit._resolve_script_path(
            source, "python3 .claude/hooks/PreToolUse/hook.py", "PreToolUse"
        )


def test_resolve_script_path_refuses_an_in_tree_symlinked_directory(tmp_path: Path) -> None:
    source = _hook_source(tmp_path)
    (source / "real").mkdir()
    (source / "real" / "hook.py").write_text("print('x')\n", encoding="utf-8")
    _plant_symlink(source / "linked", Path("real"))

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="symlinked ancestor"):
        generate_hooks_emit._resolve_script_path(
            source, "python3 .claude/hooks/linked/hook.py", "PreToolUse"
        )


def test_resolve_script_path_refuses_a_symlinked_leaf_on_the_flat_layout_fallback(
    tmp_path: Path,
) -> None:
    """The second candidate (``<Event>/<rel>``) gets the same check as the first."""
    source = _hook_source(tmp_path)
    (source / "private.py").write_text("SECRET = 1\n", encoding="utf-8")
    _plant_symlink(source / "PreToolUse" / "flat.py", Path("..") / "private.py")

    with pytest.raises(generate_hooks_emit.GenerateHooksError, match="symlink"):
        generate_hooks_emit._resolve_script_path(
            source, "python3 .claude/hooks/flat.py", "PreToolUse"
        )


def test_resolve_script_path_still_returns_a_regular_script(tmp_path: Path) -> None:
    source = _hook_source(tmp_path)
    script = source / "PreToolUse" / "hook.py"
    script.write_text("print('x')\n", encoding="utf-8")

    resolved = generate_hooks_emit._resolve_script_path(
        source, "python3 .claude/hooks/PreToolUse/hook.py", "PreToolUse"
    )

    assert resolved == script.resolve()


def test_resolve_script_path_returns_none_for_a_missing_script(tmp_path: Path) -> None:
    source = _hook_source(tmp_path)

    assert (
        generate_hooks_emit._resolve_script_path(
            source, "python3 .claude/hooks/PreToolUse/gone.py", "PreToolUse"
        )
        is None
    )


def test_resolve_script_path_accepts_a_symlinked_script_source_root(tmp_path: Path) -> None:
    """``script_source`` is build-authored; only links below it are refused."""
    real = _hook_source(tmp_path)
    (real / "PreToolUse" / "hook.py").write_text("print('x')\n", encoding="utf-8")
    alias = tmp_path / "alias"
    _plant_symlink(alias, real)

    resolved = generate_hooks_emit._resolve_script_path(
        alias, "python3 .claude/hooks/PreToolUse/hook.py", "PreToolUse"
    )

    assert resolved == (real / "PreToolUse" / "hook.py").resolve()


def test_generate_hooks_end_to_end_refuses_an_in_tree_symlinked_hook(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full generator run: the linked bytes never reach the output tree."""
    import json

    import generate_hooks

    source = tmp_path / "hooks_src"
    (source / "PreToolUse").mkdir(parents=True)
    (source / "private.py").write_text("SECRET = 'leak'\n", encoding="utf-8")
    _plant_symlink(source / "PreToolUse" / "hook.py", Path("..") / "private.py")
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/hooks/PreToolUse/hook.py",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\n'
        'provider: "test"\n'
        "artifacts:\n"
        "  hooks:\n"
        '    settingsSource: "settings.json"\n'
        '    scriptSource: "hooks_src"\n'
        '    outputConfig: "out/hooks.json"\n'
        '    outputScripts: "out"\n'
        "    eventRemap:\n"
        "      PreToolUse: PreToolUse\n"
        '    matcherPolicy: "inline-script-shim"\n'
        "    versionField: 1\n",
        encoding="utf-8",
    )

    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)

    assert rc != 0
    assert "symlinked sources are refused" in capsys.readouterr().err
    assert not any(p.name == "hook.py" for p in (tmp_path / "out").rglob("*"))
