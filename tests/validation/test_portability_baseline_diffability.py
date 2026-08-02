"""The baseline must stay visible in review, or it protects nothing.

The floor forces a lowered count to appear in a diff. `.gitattributes` can
retire that with one line: `-diff` renders the file as binary for git and for
the forges built on it, while the bytes stay readable, so the checker still
parses the lowered count and agrees with it.

Every refusal here is paired with a control that differs only in the attribute,
so a test that starts passing for the wrong reason shows up as its control
passing too. Refs #4244.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import portability_baseline
from scripts.validation.portability_baseline import refuse_undiffable_baseline


def _git(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        input=stdin,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository holding one committed baseline and no attributes."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    # A global attributes file on the developer's machine would otherwise decide
    # the answer, which would make the result depend on who ran the suite.
    _git(tmp_path, "config", "core.attributesFile", str(tmp_path / "absent-global"))
    scripts = tmp_path / "scripts" / "validation"
    scripts.mkdir(parents=True)
    (scripts / "baseline.json").write_text(json.dumps({"files": {"a/b.py": 5}}) + "\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def _baseline(repo: Path) -> Path:
    return repo / "scripts" / "validation" / "baseline.json"


def _attribute(repo: Path, line: str) -> None:
    (repo / ".gitattributes").write_text(line + "\n")


def _hide(repo: Path) -> None:
    """Apply the one line that retires review visibility for the baseline."""
    _attribute(repo, "scripts/validation/*.json -diff")


def _only_check_attr(
    monkeypatch: pytest.MonkeyPatch,
    answer: Callable[[tuple[str, ...]], subprocess.CompletedProcess[bytes] | None],
) -> None:
    """Replace only the `check-attr` call, leaving every other git call real.

    The guard asks git twice: once whether there is a repository at all, then
    what the attribute says. Patching both would make a forced `check-attr`
    failure look like an absent repository, which is the allow case, so the
    test would pass without exercising the branch it names.
    """
    real = portability_baseline.run_git

    def fake(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
        if args and args[0] == "check-attr":
            return answer(args)
        return real(root, *args)

    monkeypatch.setattr(portability_baseline, "run_git", fake)


def _patch_check_attr(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int = 0, stdout: bytes = b""
) -> None:
    """Make `check-attr` answer with a process carrying the given result."""

    def answer(args: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=["git", *args], returncode=returncode, stdout=stdout, stderr=b""
        )

    _only_check_attr(monkeypatch, answer)


def _unanswerable_check_attr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `check-attr` fail to produce a process at all."""
    _only_check_attr(monkeypatch, lambda _args: None)


class TestABaselineGitWillNotDiffIsRefused:
    def test_a_minus_diff_attribute_is_refused(self, repo: Path) -> None:
        _attribute(repo, "scripts/validation/baseline.json -diff")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True

    def test_the_binary_macro_is_refused_because_it_expands_to_minus_diff(
        self, repo: Path
    ) -> None:
        """`binary` is not a separate spelling to remember, it is the same hole.

        It expands to `-diff -merge -text`, so a guard that only matched the
        literal `-diff` would be walked straight around.
        """
        _attribute(repo, "scripts/validation/baseline.json binary")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True

    def test_a_directory_wide_attribute_reaches_the_baseline(self, repo: Path) -> None:
        """The attribute does not have to name the baseline to silence it."""
        _attribute(repo, "*.json -diff")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True


class TestADiffableBaselineIsAllowed:
    def test_no_attribute_at_all_is_allowed(self, repo: Path) -> None:
        """The control for every refusal above.

        Git reports `unspecified` here and `unset` for `-diff`. If this test
        ever fails, the guard is reading the two as one and would refuse every
        ordinary repository.
        """
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is False

    def test_an_explicitly_set_diff_attribute_is_allowed(self, repo: Path) -> None:
        _attribute(repo, "scripts/validation/baseline.json diff")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is False

    def test_a_named_diff_driver_is_allowed(self, repo: Path) -> None:
        """`diff=json` picks a hunk-header algorithm; the content still shows."""
        _attribute(repo, "scripts/validation/baseline.json diff=json")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is False

    def test_a_driver_literally_named_false_is_allowed(self, repo: Path) -> None:
        """`diff=false` reads like a refusal and is not one.

        `git check-attr` reports the value `false`, which invites a guard to
        treat it as `-diff`. It is a driver name, and git still emits a textual
        diff for it, so refusing here would reject a safe configuration.
        """
        _attribute(repo, "scripts/validation/baseline.json diff=false")
        baseline = _baseline(repo)
        assert refuse_undiffable_baseline(repo, baseline) is False

        baseline.write_text(json.dumps({"files": {"a/b.py": 1}}) + "\n")
        assert '"a/b.py": 1' in _git(repo, "diff").stdout

    def test_an_attribute_aimed_at_a_different_file_does_not_refuse(self, repo: Path) -> None:
        _attribute(repo, "scripts/validation/other.json -diff")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is False


class TestOutsideARepositoryTheGuardHasNoAsset:
    def test_a_path_outside_any_repository_is_allowed(self, tmp_path: Path) -> None:
        """No repository means no diff to hide a number in, so nothing to defend.

        Refusing here would block vendored copies and unpacked tarballs while
        protecting nothing: there is no branch to land a lowered count on. The
        two tests below show the guard is still live wherever a repository is.
        """
        loose = tmp_path / "loose"
        loose.mkdir()
        target = loose / "baseline.json"
        target.write_text("{}\n")
        assert refuse_undiffable_baseline(loose, target) is False

    def test_a_repository_is_established_by_git_answering_not_by_the_path(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The allowance is keyed on git's verdict, so it cannot be assumed.

        Inside a real repository whose baseline is hidden, the guard refuses.
        Paired with the test above, this pins that the escape hatch is the
        absence of a repository and not the absence of an attribute.
        """
        _hide(repo)
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True


class TestAnUnanswerableAttributeIsRefused:
    def test_a_failed_git_call_is_refused_even_when_it_prints_an_answer(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tool that answers can still have failed, and the answer is worthless.

        `check-attr` is made to exit non-zero while emitting well-formed output
        saying the baseline diffs normally. Parsing that would read a failure as
        a clean bill of health.
        """
        _patch_check_attr(monkeypatch, returncode=128, stdout=b"baseline.json\0diff\0set\0")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True

    def test_a_successful_git_call_that_says_nothing_is_refused(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exit zero with no attribute reported is silence, not permission."""
        _patch_check_attr(monkeypatch, returncode=0, stdout=b"")
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True

    def test_check_attr_being_unrunnable_is_refused(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _unanswerable_check_attr(monkeypatch)
        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True


class TestTheAttributeActuallyHidesTheNumber:
    def test_the_lowered_count_is_invisible_once_the_attribute_lands(self, repo: Path) -> None:
        """The reason the guard exists, pinned rather than asserted in a comment.

        Without the attribute the diff carries the two counts. With it, the same
        edit renders as a binary difference and the number is gone, while the
        file still parses to the lowered value.
        """
        baseline = _baseline(repo)
        lowered = json.dumps({"files": {"a/b.py": 1}}) + "\n"

        baseline.write_text(lowered)
        visible = _git(repo, "diff").stdout
        assert '"a/b.py": 1' in visible
        assert "Binary files" not in visible

        _git(repo, "checkout", "-q", "--", ".")
        _attribute(repo, "scripts/validation/baseline.json -diff")
        _git(repo, "add", ".gitattributes")
        _git(repo, "commit", "-qm", "mark baseline binary")
        baseline.write_text(lowered)

        hidden = _git(repo, "diff").stdout
        assert "Binary files" in hidden
        assert '"a/b.py": 1' not in hidden
        assert json.loads(baseline.read_text())["files"]["a/b.py"] == 1


class TestEveryCheckerRefusesAHiddenBaseline:
    """The guard is worth nothing in the module it lives in; it has to be wired.

    All three ratchets read a baseline of their own, so a guard reaching two of
    them leaves the third as the way through. Each checker is run twice against
    the same tree, differing only in the attribute, so a checker that exits 2
    for an unrelated reason fails its own control.
    """

    @staticmethod
    def _tree(root: Path, name: str) -> Path:
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "core.attributesFile", str(root / "absent-global"))
        for tree in (".claude/skills", "src/copilot-cli/skills"):
            (root / tree).mkdir(parents=True, exist_ok=True)
        target = root / "scripts" / "validation" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"files": {}, "marker_files": {}}) + "\n")
        return target

    @pytest.mark.parametrize(
        ("module", "baseline_name"),
        [
            ("check_skill_portability", "skill_portability_baseline.json"),
            ("check_skill_md_exec_portability", "skill_md_exec_portability_baseline.json"),
            ("check_skill_md_portability", "skill_md_portability_baseline.json"),
        ],
    )
    def test_the_checker_refuses_only_when_the_baseline_is_hidden(
        self, tmp_path: Path, module: str, baseline_name: str
    ) -> None:
        checker = importlib.import_module(f"scripts.validation.{module}")
        root = tmp_path / module
        root.mkdir()
        baseline = self._tree(root, baseline_name)
        argv = ["--repo-root", str(root), "--baseline", str(baseline)]

        allowed = checker.main(argv)
        assert allowed != 2, f"{module} rejected a clean tree, so its control proves nothing"

        _attribute(root, "scripts/validation/*.json -diff")
        assert checker.main(argv) == 2, f"{module} accepted a baseline review cannot see"
