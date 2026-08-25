# taste-lint: ignore file-size, baseline diffability contract needs paired controls in one file.
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

from scripts.validation import portability_baseline, portability_git
from scripts.validation.portability_baseline import (
    refuse_diff_suppressed_baseline,
    refuse_undiffable_baseline,
)
from scripts.validation.portability_common import resolve_checked_baseline


def _git(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
        """`diff=json` picks a hunk-header algorithm; the content still shows.

        A named driver can be made to render as binary, but only by a reader
        who also sets `diff.<name>.binary=true`. That setting lives in git
        config, which is per clone and never committed, so it cannot travel
        with the attack and the forge rendering the review never sees it. The
        committed ways to reach the same effect are `-diff` and the `binary`
        macro, and both are refused above.

        Written down because the local-config route is easy to rediscover and
        reads like a hole. Refusing every named driver on account of it would
        reject a safe, committed configuration on the strength of a setting the
        reviewer's forge does not read. The pair below is the discriminator: the
        driver alone renders text, and only the local setting changes that.
        """
        _attribute(repo, "scripts/validation/baseline.json diff=json")
        baseline = _baseline(repo)
        assert refuse_undiffable_baseline(repo, baseline) is False

        baseline.write_text(json.dumps({"files": {"a/b.py": 1}}) + "\n")
        assert '"a/b.py": 1' in _git(repo, "diff").stdout

        _git(repo, "config", "diff.json.binary", "true")
        assert "Binary files" in _git(repo, "diff").stdout
        assert refuse_undiffable_baseline(repo, baseline) is False

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

    def test_check_attr_timeout_names_the_failed_probe(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def answer(args: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(
                args,
                portability_git.GIT_TIMEOUT_RETURN_CODE,
                stdout=b"",
                stderr=b"git command timed out after 30s",
            )

        _only_check_attr(monkeypatch, answer)

        assert refuse_undiffable_baseline(repo, _baseline(repo)) is True
        error = capsys.readouterr().err
        assert "checking the baseline diff attribute" in error
        assert "timed out" in error

    def test_write_guard_check_attr_timeout_names_the_failed_probe(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        timed_out = subprocess.CompletedProcess(
            ["git", "check-attr"],
            portability_git.GIT_TIMEOUT_RETURN_CODE,
            stdout=b"",
            stderr=b"git command timed out after 30s",
        )
        monkeypatch.setattr(portability_baseline, "_run_git", lambda *_args: timed_out)

        assert refuse_diff_suppressed_baseline(repo, _baseline(repo)) is True
        error = capsys.readouterr().err
        assert "checking the baseline diff attribute" in error
        assert "timed out" in error


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
        # check_skill_md_portability also requires src/copilot-cli/instructions
        # to exist and examine at least one Markdown file (issue #5214,
        # widened by review to reject an existing-but-empty required root
        # too); harmless to the other two checkers here.
        instructions_dir = root / "src" / "copilot-cli" / "instructions"
        instructions_dir.mkdir(parents=True, exist_ok=True)
        (instructions_dir / "_placeholder.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
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


class TestTheAttributeCheckAndTheReadMustLandOnTheSameFile:
    """A symlink splits the file that is vetted from the file that is used.

    The attribute is asked about the pathname handed in. Reading follows the
    link. So hiding the *target* rather than the name leaves the guard looking
    at an unhidden pathname while the checker parses a file review cannot see,
    which is the attribute finding one indirection deeper. The write path had
    refused links for a different reason since before the attribute guard
    existed; the read path had not.
    """

    @staticmethod
    def _split(repo: Path, *, hide_target: bool) -> Path:
        """Replace the baseline with a link to a sibling, optionally hidden."""
        named = _baseline(repo)
        target = named.with_name("hidden.json")
        target.write_text(named.read_text())
        named.unlink()
        named.symlink_to("hidden.json")
        if hide_target:
            _attribute(repo, "scripts/validation/hidden.json -diff")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "split the baseline behind a link")
        return target

    def test_hiding_the_target_hides_the_lowered_count(self, repo: Path) -> None:
        """The asset, pinned. Without this the refusal below protects nothing."""
        target = self._split(repo, hide_target=True)
        target.write_text(json.dumps({"files": {"a/b.py": 1}}) + "\n")

        rendered = _git(repo, "diff").stdout
        assert "Binary files" in rendered
        assert '"a/b.py": 1' not in rendered
        assert json.loads(_baseline(repo).read_text())["files"]["a/b.py"] == 1

    def test_the_read_gate_refuses_a_linked_baseline(self, repo: Path) -> None:
        self._split(repo, hide_target=True)
        assert resolve_checked_baseline(repo, _baseline(repo), "baseline.json") is None

    def test_the_control_without_a_link_is_allowed(self, repo: Path) -> None:
        """Same tree, no link, nothing hidden. A refusal here would prove nothing."""
        assert resolve_checked_baseline(repo, _baseline(repo), "baseline.json") is not None

    def test_a_link_is_refused_even_when_its_target_is_diffable(self, repo: Path) -> None:
        """The link alone is the objection; the guard does not wait to be hidden."""
        self._split(repo, hide_target=False)
        assert resolve_checked_baseline(repo, _baseline(repo), "baseline.json") is None

    @pytest.mark.parametrize(
        ("module", "baseline_name"),
        [
            ("check_skill_portability", "skill_portability_baseline.json"),
            ("check_skill_md_exec_portability", "skill_md_exec_portability_baseline.json"),
            ("check_skill_md_portability", "skill_md_portability_baseline.json"),
        ],
    )
    def test_every_checker_refuses_a_linked_baseline(
        self, tmp_path: Path, module: str, baseline_name: str
    ) -> None:
        """Wiring, not the module. Each checker is its own way through."""
        checker = importlib.import_module(f"scripts.validation.{module}")
        root = tmp_path / module
        root.mkdir()
        baseline = TestEveryCheckerRefusesAHiddenBaseline._tree(root, baseline_name)
        argv = ["--repo-root", str(root), "--baseline", str(baseline)]

        allowed = checker.main(argv)
        assert allowed != 2, f"{module} rejected a clean tree, so its control proves nothing"

        target = baseline.with_name("hidden.json")
        target.write_text(baseline.read_text())
        baseline.unlink()
        baseline.symlink_to("hidden.json")
        assert checker.main(argv) == 2, f"{module} read a baseline through a link"


class TestEnvironmentOnlyWorktreeIsNotVacuouslyAllowed:
    """The guard must refuse when GIT_* vars were scrubbed, not vacuously allow.

    Issue #4258: run_git strips every GIT_* variable. An env-only worktree
    (no .git file, only GIT_DIR + GIT_WORK_TREE) is therefore invisible to
    run_git, which reports no repository. The old guard treated that as
    "not a repo -> allow". This is the vacuity: the guard passed because it
    saw nothing.

    The decisive test: with GIT_DIR in the environment, refuse_undiffable_baseline
    must REFUSE rather than allow when rev-parse cannot find a repo. A guard
    that passes here because it saw nothing is the bug this test catches.
    """

    def test_guard_refuses_when_git_dir_is_set_and_rev_parse_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vacuity check: the guard must fail on a known-bad input.

        A path with no .git file but GIT_DIR set in the environment is a real
        checkout that run_git cannot see. The guard must refuse rather than
        allow, because it was prevented from answering, not because there is
        no repository. Refs #4258.
        """
        # A directory with no .git file -- run_git will find no repository here.
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        baseline = bare_dir / "baseline.json"
        baseline.write_text('{"files": {}}\n')

        # Simulate the env-only worktree: GIT_DIR is set, but run_git strips it.
        monkeypatch.setenv("GIT_DIR", str(tmp_path / "fake.git"))

        result = refuse_undiffable_baseline(bare_dir, baseline)
        assert result is True, (
            "refuse_undiffable_baseline returned False (allowed) when GIT_DIR was "
            "set in the environment but run_git stripped it. "
            "The guard saw no repository because the scrub hid it, not because "
            "there is no repository. This is the vacuity that issue #4258 fixes: "
            "absence must be proven by the tool answering, not by the tool being silenced."
        )

    def test_guard_refuses_when_repository_probe_times_out(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}\n')
        timed_out = subprocess.CompletedProcess(
            ["git", "rev-parse"],
            portability_git.GIT_TIMEOUT_RETURN_CODE,
            b"",
            b"git command timed out after 30s",
        )
        monkeypatch.setattr(portability_baseline, "run_git", lambda *_args: timed_out)

        assert refuse_undiffable_baseline(tmp_path, baseline) is True
        assert "git command timed out after 30s" in capsys.readouterr().err

    def test_guard_allows_when_no_git_pointer_vars_are_set_and_no_repo_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Control: no GIT_DIR + no repo still allows (vendored copy case).

        This is the existing behaviour for genuinely non-repository paths.
        The fix must not change it. A vendored copy, unpacked tarball, or
        fixture directory with no repo and no pointer variables must remain
        allowed. Refs #4258.
        """
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
            monkeypatch.delenv(var, raising=False)

        loose = tmp_path / "loose"
        loose.mkdir()
        baseline = loose / "baseline.json"
        baseline.write_text('{"files": {}}\n')

        result = refuse_undiffable_baseline(loose, baseline)
        assert result is False, (
            "refuse_undiffable_baseline returned True (refused) for a path outside "
            "any repository with no GIT_* pointer variables set. "
            "The fix for issue #4258 must not block vendored copies and unpacked tarballs."
        )

    def test_guard_allows_when_a_pointer_var_is_exported_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty pointer names no repository, so the scrub hid nothing.

        Presence in ``os.environ`` is not the discriminator; a meaningful value
        is. Measured on git 2.51: ``GIT_DIR=""`` in a non-repository yields
        ``fatal: not a git repository: ''`` and resolves no repository, the same
        outcome as an absent variable. Refusing here would block the vendored
        copy and unpacked tarball case the allow branch exists for.
        """
        loose = tmp_path / "loose"
        loose.mkdir()
        baseline = loose / "baseline.json"
        baseline.write_text('{"files": {}}\n')

        monkeypatch.setenv("GIT_DIR", "")

        assert refuse_undiffable_baseline(loose, baseline) is False, (
            "refuse_undiffable_baseline refused on an exported-but-empty GIT_DIR. "
            "An empty pointer names no repository, so the GIT_* scrub cannot have "
            "hidden one, and the refusal is a false positive against vendored "
            "copies and unpacked tarballs. Refs #4258."
        )

    def test_guard_refuses_when_git_work_tree_is_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GIT_WORK_TREE also triggers the refusal, not only GIT_DIR."""
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        baseline = bare_dir / "baseline.json"
        baseline.write_text('{"files": {}}\n')

        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "work"))

        result = refuse_undiffable_baseline(bare_dir, baseline)
        assert result is True, (
            "refuse_undiffable_baseline allowed when GIT_WORK_TREE was set. "
            "GIT_WORK_TREE is also a pointer that run_git strips. Refs #4258."
        )
