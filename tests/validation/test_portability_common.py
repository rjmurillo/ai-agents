from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation import portability_common as common


def _message(rel: str, count: int, allowed: int) -> str:
    return f"{rel}: {count} refs (baseline {allowed})"


def test_load_baseline_accepts_wrapped_files_object(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": "2"}}), encoding="utf-8")

    assert common.load_baseline(baseline) == {"skills/a.py": 2}


def test_load_baseline_rejects_null_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"skills/a.py": None}}), encoding="utf-8")

    with pytest.raises(ValueError, match="null"):
        common.load_baseline(baseline)


def test_diff_against_baseline_reports_regression_and_improvement() -> None:
    regressions, improvements = common.diff_against_baseline(
        {"a.py": 3, "b.py": 1},
        {"a.py": 2, "b.py": 2},
        _message,
    )

    assert regressions == ["a.py: 3 refs (baseline 2)"]
    assert improvements == ["b.py: 1 refs (baseline 2)"]


def test_resolve_baseline_rejects_path_outside_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "baseline.json"
    outside.write_text("{}", encoding="utf-8")

    assert (
        common.resolve_baseline_path(
            root,
            outside,
            "default.json",
            reject_outside_root=True,
        )
        == Path("")
    )


def test_git_lines_strips_git_overrides_case_insensitively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_env: dict[str, str] = {}

    def run_git(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        captured_env.update(env)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("git_index_file", "/wrong/index")
    monkeypatch.setenv("Git_Dir", "/wrong/repo")
    monkeypatch.setenv("PORTABILITY_TEST_SENTINEL", "kept")
    monkeypatch.setattr(common.subprocess, "run", run_git)

    assert common._git_lines(tmp_path, ["status"]) == []
    assert "git_index_file" not in captured_env
    assert "Git_Dir" not in captured_env
    assert captured_env["PORTABILITY_TEST_SENTINEL"] == "kept"


class TestTheGuardCannotBeSkippedByForgettingAnArgument:
    """`write_baseline` used to default its way out of its own protection.

    `repo_root` defaulted to None and was then read as `baseline_path.parent`,
    which is the directory the baseline sits in rather than the repository. The
    committed copy is looked up by a repository-relative path, so that default
    silently found nothing and the guard lost its floor. `allow_shrink`
    defaulted to False, which meant a checker that forgot to forward its own
    `--allow-baseline-shrink` flag left contributors with no way through.

    Neither failure announced itself. The signature is the fix: both arguments
    are required and keyword-only, so the same omission is a TypeError at the
    call site instead of a guard that quietly stops guarding.
    """

    @pytest.mark.parametrize("name", ["repo_root", "allow_shrink"])
    def test_the_argument_is_required(self, name: str) -> None:
        parameter = inspect.signature(common.write_baseline).parameters[name]

        assert parameter.default is inspect.Parameter.empty

    @pytest.mark.parametrize("name", ["repo_root", "allow_shrink"])
    def test_the_argument_cannot_be_passed_positionally(self, name: str) -> None:
        """Positional passing is how the required-ness gets refactored away.

        The signature is asserted rather than a TypeError caught, because a
        call written to raise is a call a type checker is right to reject, and
        silencing it there would hide the same class of mistake elsewhere.
        """
        parameter = inspect.signature(common.write_baseline).parameters[name]

        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_the_repository_root_actually_reaches_the_committed_lookup(
        self, tmp_path: Path
    ) -> None:
        """Forwarding the root is what gives the write its committed floor.

        Passing the baseline's own directory, which is what the old default
        computed, must not be enough to satisfy the guard: the shrink below is
        only visible to a lookup rooted at the repository.
        """
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)
        for args in (
            ["init", "-q"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "t"],
        ):
            subprocess.run(
                ["git", "-C", str(root), *args], check=True, capture_output=True
            )
        path = root / "scripts" / "validation" / "b.json"
        path.write_text(json.dumps({"files": {"a.py": 4, "b.py": 2}}), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", "-A"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "seed"],
            check=True,
            capture_output=True,
        )
        path.write_text("{}", encoding="utf-8")

        rc = common.write_baseline(
            path, {"a.py": 1}, "c", "refs", repo_root=root, allow_shrink=False
        )

        assert rc == 2
        assert path.read_text(encoding="utf-8") == "{}"


class TestAnOverrideKeepsTheEvidenceTheSymlinkGuardNeeds:
    """`resolve()` follows links, so resolving before the guard runs blinds it.

    The containment test needs the resolved form. The guard needs the lexical
    one. Returning the resolved path satisfies the first and silently defeats
    the second, which is how an in-repository symlink passes as a baseline.
    """

    def test_a_symlinked_override_is_returned_unresolved(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)
        target = root / "scripts" / "validation" / "other.json"
        target.write_text("{}", encoding="utf-8")
        link = root / "scripts" / "validation" / "link.json"
        link.symlink_to(target)

        resolved = common.resolve_baseline_path(
            root, Path("scripts/validation/link.json"), "d.json", reject_outside_root=True
        )

        assert resolved.name == "link.json"
        assert resolved.is_symlink()

    def test_an_override_outside_the_root_is_still_rejected(
        self, tmp_path: Path
    ) -> None:
        """Keeping the lexical path must not weaken the containment test."""
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")

        resolved = common.resolve_baseline_path(
            root, outside, "d.json", reject_outside_root=True
        )

        assert resolved == Path("")

    def test_a_link_pointing_out_of_the_root_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = root / "scripts" / "validation" / "escape.json"
        link.symlink_to(outside)

        resolved = common.resolve_baseline_path(
            root, link, "d.json", reject_outside_root=True
        )

        assert resolved == Path("")

    def test_a_plain_override_still_resolves(self, tmp_path: Path) -> None:
        """The refusals above are only correct if this stays permitted."""
        root = tmp_path / "repo"
        (root / "scripts" / "validation").mkdir(parents=True)

        resolved = common.resolve_baseline_path(
            root, Path("scripts/validation/b.json"), "d.json", reject_outside_root=True
        )

        assert resolved == root / "scripts" / "validation" / "b.json"
