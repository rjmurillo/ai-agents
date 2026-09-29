"""Base/head delta and git plumbing for the byte report (issue #5400)."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import IO, Any

import pytest

from scripts.validation.instruction_bytes_delta import (
    DEFAULT_GROWTH_THRESHOLD_BYTES,
    GitError,
    compute_delta,
    materialize_base,
    resolve_ref,
)
from tests.validation._instruction_bytes_helpers import commit_all, git, init_git, write


def _report(**overrides: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "canonical": {
            "total": {"bytes": 1000, "tokens": 250},
            "paths": {"templates/a.md": 600, "templates/b.md": 400},
        },
        "generated": {"total": {"bytes": 5000, "tokens": 1250}},
        "always_on": {"claude_code": {"bytes": 100, "tokens": 25}},
        "fixtures": {"F1": {"bytes": 300, "tokens": 75}},
    }
    report.update(overrides)
    return report


def _grown(
    base: dict[str, Any], *, always: int = 0, fixture: int = 0, canonical: int = 0
) -> dict[str, Any]:
    head = copy.deepcopy(base)
    head["always_on"]["claude_code"]["bytes"] += always
    head["fixtures"]["F1"]["bytes"] += fixture
    head["canonical"]["total"]["bytes"] += canonical
    return head


def _metric(delta: dict[str, Any], name: str) -> dict[str, Any]:
    return next(m for m in delta["metrics"] if m["name"] == name)


class TestComputeDelta:
    def test_identical_reports_show_zero_change_and_no_growth(self) -> None:
        base = _report()
        delta = compute_delta(base, copy.deepcopy(base))
        assert all(m["delta"] == 0 for m in delta["metrics"])
        assert delta["material_growth"] == []
        assert delta["changed_paths"] == []

    def test_growth_past_the_threshold_is_material(self) -> None:
        base = _report()
        head = _grown(
            base,
            always=DEFAULT_GROWTH_THRESHOLD_BYTES + 1,
            fixture=DEFAULT_GROWTH_THRESHOLD_BYTES + 1,
        )
        delta = compute_delta(base, head)
        assert delta["material_growth"] == [
            "always_on.claude_code.bytes",
            "fixtures.F1.bytes",
        ]

    def test_growth_exactly_at_the_threshold_is_not_material(self) -> None:
        base = _report()
        head = _grown(base, always=DEFAULT_GROWTH_THRESHOLD_BYTES)
        assert compute_delta(base, head)["material_growth"] == []

    def test_a_custom_threshold_is_honored(self) -> None:
        base = _report()
        head = _grown(base, fixture=11)
        assert compute_delta(base, head, threshold_bytes=10)["material_growth"] == [
            "fixtures.F1.bytes"
        ]
        assert compute_delta(base, head, threshold_bytes=11)["material_growth"] == []

    def test_shrinking_is_reported_but_never_material(self) -> None:
        base = _report()
        head = _grown(base, always=-50, fixture=-50)
        delta = compute_delta(base, head)
        assert _metric(delta, "always_on.claude_code.bytes")["delta"] == -50
        assert delta["material_growth"] == []

    def test_canonical_total_growth_is_reported_but_not_gated(self) -> None:
        base = _report()
        head = _grown(base, canonical=DEFAULT_GROWTH_THRESHOLD_BYTES * 10)
        delta = compute_delta(base, head)
        assert (
            _metric(delta, "canonical.total.bytes")["delta"] == DEFAULT_GROWTH_THRESHOLD_BYTES * 10
        )
        assert delta["material_growth"] == []

    def test_token_growth_is_reported_but_not_gated(self) -> None:
        base = _report()
        head = copy.deepcopy(base)
        head["fixtures"]["F1"]["tokens"] += 10 * DEFAULT_GROWTH_THRESHOLD_BYTES
        delta = compute_delta(base, head)
        assert _metric(delta, "fixtures.F1.tokens")["delta"] == 10 * DEFAULT_GROWTH_THRESHOLD_BYTES
        assert delta["material_growth"] == []

    def test_a_fixture_absent_at_base_is_skipped_and_named(self) -> None:
        base = _report(fixtures={"F1": {"error": "skill `x` has no file", "name": "n"}})
        head = _report()
        delta = compute_delta(base, head)
        assert not any(m["name"].startswith("fixtures.") for m in delta["metrics"])
        assert delta["unmeasured_at_base"] == ["fixtures.F1.bytes", "fixtures.F1.tokens"]
        assert delta["material_growth"] == []

    def test_an_errored_head_fixture_is_skipped(self) -> None:
        base = _report()
        head = _report(fixtures={"F1": {"error": "boom", "name": "n"}})
        delta = compute_delta(base, head)
        assert not any(m["name"].startswith("fixtures.") for m in delta["metrics"])

    def test_changed_paths_rank_by_absolute_change_and_respect_the_limit(self) -> None:
        base = _report()
        head = copy.deepcopy(base)
        head["canonical"]["paths"] = {
            "templates/a.md": 610,
            "templates/b.md": 100,
            "templates/new.md": 50,
        }
        rows = compute_delta(base, head, limit=2)["changed_paths"]
        assert [(r["path"], r["delta"]) for r in rows] == [
            ("templates/b.md", -300),
            ("templates/new.md", 50),
        ]

    def test_a_removed_path_reports_head_as_zero(self) -> None:
        base = _report()
        head = copy.deepcopy(base)
        del head["canonical"]["paths"]["templates/b.md"]
        row = compute_delta(base, head)["changed_paths"][0]
        assert (row["path"], row["base"], row["head"], row["delta"]) == (
            "templates/b.md",
            400,
            0,
            -400,
        )

    def test_equal_deltas_break_ties_by_path(self) -> None:
        base = _report()
        head = copy.deepcopy(base)
        head["canonical"]["paths"] = {"templates/a.md": 601, "templates/b.md": 401}
        assert [r["path"] for r in compute_delta(base, head)["changed_paths"]] == [
            "templates/a.md",
            "templates/b.md",
        ]


class TestResolveRef:
    def test_a_leading_dash_is_refused_as_an_option(self, tmp_path: Path) -> None:
        with pytest.raises(GitError, match="refusing base ref"):
            resolve_ref(tmp_path, "--output=/tmp/x")

    @pytest.mark.parametrize("ref", ["", "   "])
    def test_a_blank_ref_is_refused(self, tmp_path: Path, ref: str) -> None:
        with pytest.raises(GitError, match="refusing base ref"):
            resolve_ref(tmp_path, ref)

    def test_an_unknown_ref_is_an_error(self, tmp_path: Path) -> None:
        init_git(tmp_path)
        write(tmp_path, "a.md", "x\n")
        commit_all(tmp_path)
        with pytest.raises(GitError, match="does not resolve to a commit"):
            resolve_ref(tmp_path, "no-such-branch")

    def test_a_valid_ref_resolves_to_the_commit_sha(self, tmp_path: Path) -> None:
        init_git(tmp_path)
        write(tmp_path, "a.md", "x\n")
        sha = commit_all(tmp_path)
        assert resolve_ref(tmp_path, "HEAD") == sha

    def test_a_non_repository_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(GitError, match="does not resolve"):
            resolve_ref(tmp_path, "HEAD")


class TestMaterializeBase:
    def test_extracts_markdown_and_templates_only(self, tmp_path: Path) -> None:
        repo, dest = tmp_path / "repo", tmp_path / "dest"
        repo.mkdir()
        dest.mkdir()
        init_git(repo)
        write(repo, "docs/a.md", "doc\n")
        write(repo, "templates/skills/x.SKILL.md.tmpl", "tmpl\n")
        write(repo, "scripts/run.py", "print(1)\n")
        write(repo, "data.json", "{}\n")
        sha = commit_all(repo)
        materialize_base(repo, sha, dest)
        found = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
        assert found == ["docs/a.md", "templates/skills/x.SKILL.md.tmpl"]

    def test_reads_the_revision_not_the_working_tree(self, tmp_path: Path) -> None:
        repo, dest = tmp_path / "repo", tmp_path / "dest"
        repo.mkdir()
        dest.mkdir()
        init_git(repo)
        write(repo, "a.md", "committed\n")
        sha = commit_all(repo)
        write(repo, "a.md", "edited after the commit\n")
        materialize_base(repo, sha, dest)
        assert (dest / "a.md").read_text(encoding="utf-8") == "committed\n"

    def test_a_revision_with_no_measured_files_extracts_nothing(self, tmp_path: Path) -> None:
        repo, dest = tmp_path / "repo", tmp_path / "dest"
        repo.mkdir()
        dest.mkdir()
        init_git(repo)
        write(repo, "a.py", "x = 1\n")
        materialize_base(repo, commit_all(repo), dest)
        assert list(dest.iterdir()) == []

    def test_an_unknown_sha_is_a_git_error(self, tmp_path: Path) -> None:
        repo, dest = tmp_path / "repo", tmp_path / "dest"
        repo.mkdir()
        dest.mkdir()
        init_git(repo)
        write(repo, "a.md", "x\n")
        commit_all(repo)
        with pytest.raises(GitError, match="git archive"):
            materialize_base(repo, "0" * 40, dest)

    def test_a_nonzero_exit_after_a_readable_tar_is_a_git_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_popen = subprocess.Popen
        script = (
            "import sys, tarfile\n"
            "tarfile.open(fileobj=sys.stdout.buffer, mode='w|').close()\n"
            "sys.stderr.write('fatal: simulated failure')\n"
            "sys.exit(128)\n"
        )

        def fake_popen(
            _args: list[str], stdout: int | IO[bytes] | None, stderr: int | IO[bytes] | None
        ) -> subprocess.Popen[bytes]:
            return real_popen([sys.executable, "-c", script], stdout=stdout, stderr=stderr)

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        dest = tmp_path / "dest"
        dest.mkdir()
        with pytest.raises(GitError, match="fatal: simulated failure"):
            materialize_base(tmp_path, "0" * 40, dest)

    def test_the_head_is_untouched_by_materializing(self, tmp_path: Path) -> None:
        repo, dest = tmp_path / "repo", tmp_path / "dest"
        repo.mkdir()
        dest.mkdir()
        init_git(repo)
        write(repo, "a.md", "x\n")
        sha = commit_all(repo)
        materialize_base(repo, sha, dest)
        assert git(repo, "status", "--porcelain") == ""
