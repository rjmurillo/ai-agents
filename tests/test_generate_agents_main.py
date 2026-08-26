"""Tests for generate_agents.py's CLI entry point (main()).

Split out of test_generate_agents.py (issue: taste-lint file-size ratchet)
to keep TestMain's CLI-argument-parsing concerns separate from
TestGenerateAgents' direct-call orchestration tests and
TestReadPlatformConfig's config-parsing tests, which stay in
test_generate_agents.py. Shares that file's `_create_test_structure`
fixture helper by importing it directly, so the on-disk test-structure
shape has exactly one definition.

This is a Python port of Generate-Agents.ps1 tests following ADR-042 migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from generate_agents import main  # noqa: E402

from tests.test_generate_agents import _create_test_structure  # noqa: E402
from tests.test_generate_agents_manifest import _write_keep_pin_manifest  # noqa: E402


class TestMain:
    """Tests for main entry point."""

    def test_missing_templates_path(self, tmp_path: Path) -> None:
        exit_code = main(["--templates-path", str(tmp_path / "nonexistent")])
        assert exit_code == 2

    def test_help_flag(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_relative_output_root_does_not_hang(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative --output-root (e.g. `--output-root src`) must not
        hang: generate_agents() walks output_dir up via .parent comparing
        to the absolute repo_root (the symlink-ancestor check), and a
        relative output_dir never equals repo_root at any ancestor
        including "." (Path(".").parent == Path(".")), so an unresolved
        relative output_root spins forever instead of erroring. Bounded
        with pytest-timeout at the suite level as a backstop; this
        assertion is the real regression signal."""
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        monkeypatch.chdir(repo_root)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", "src",
        ])
        assert exit_code == 0

    def test_output_root_outside_repo_root_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An ABSOLUTE --output-root that still resolves outside repo_root
        (e.g. `--templates-path /repo/templates --output-root src` run from
        `/tmp`, which resolves to `/tmp/src`) hits the same infinite-loop
        hazard as the relative-path case above, one step later: main()'s
        .resolve() makes it absolute, but absolute is not the same as
        "inside repo_root". Without generate_agents()'s own is_relative_to
        guard, the symlink-ancestor walk climbs from /tmp/src up through
        /tmp and / looking for repo_root and never finds it, because / is
        its own parent. Must exit 2 promptly, not hang."""
        repo_root, templates_path, _ = _create_test_structure(tmp_path)
        outside_dir = tmp_path / "elsewhere"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", "src",
        ])
        assert exit_code == 2

    def test_full_run(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
        ])
        assert exit_code == 0

    def test_relative_templates_path_resolves_manifest_pins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI regression for a relative --templates-path (the normal
        invocation shape, e.g. `--templates-path templates`).

        main() must resolve templates_path to absolute alongside repo_root:
        generate_agents() computes each shared file's manifest unit key via
        shared_file.relative_to(repo_root), which raises ValueError
        (silently caught, source_unit=None) when templates_path stays
        relative while repo_root is absolute. Before the fix, a relative
        --templates-path always ignored every valid manifest KEEP_PIN
        entry with no error and no test catching it, because every other
        test in this file passes an already-absolute tmp_path."""
        repo_root, templates_path, output_root = _create_test_structure(
            tmp_path, with_model_tiers=True
        )
        _write_keep_pin_manifest(repo_root)

        monkeypatch.chdir(repo_root)
        # --output-root stays absolute here on purpose: this test isolates
        # the relative --templates-path bug the review flagged. A relative
        # --output-root hits a separate, pre-existing bug in the
        # symlink-ancestor walk a few lines below (an infinite loop, not
        # this test's subject); see the follow-up fix in this same commit.
        exit_code = main([
            "--templates-path", "templates",
            "--output-root", str(output_root),
        ])
        assert exit_code == 0

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "model: Claude Opus 4.6 (copilot)" in content

    def test_what_if_flag(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
            "--what-if",
        ])
        assert exit_code == 0

    def test_validate_flag(self, tmp_path: Path) -> None:
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)

        # Generate first, then validate
        main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
        ])
        exit_code = main([
            "--templates-path", str(templates_path),
            "--output-root", str(output_root),
            "--validate",
        ])
        assert exit_code == 0
