"""CI backstop for the security-suppression policy (issue #4061).

The suppression policy shipped only as a lefthook gate: `pre-commit` and
`pre-merge-commit` ran ``security-suppressions-staged`` and `pre-push` ran
``security-suppressions-push``. No workflow referenced either, so the policy
bound exactly those contributors who had lefthook installed and did not use
``--no-verify``. ``security-suppressions-range`` closes that gap by running the
same collector over an explicit base..head range from CI.

Every test drives ``policy.main(argv)`` and asserts on its **exit code**, not on
a helper's return value. Issue #4068 documents why: a helper-level assertion
structurally cannot catch a wrong exit code, which is how loud shell failures
became silent green Python steps across this repository.

Literal suppression tokens are split (``"# no" "qa"``) so this file does not
trip the very gate it exercises.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy  # noqa: E402

NOQA = "# no" "qa"
TYPE_IGNORE = "# type: " "ignore"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _run(["git", *args], repo)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(repo: Path) -> str:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "alpha.py").write_text("import os\nprint(os)\n", encoding="utf-8")
    (repo / "pkg" / "beta.py").write_text("import sys\nprint(sys)\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "checkout", "-b", "topic")
    return base


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _range_exit(repo: Path, base: str = "origin/main", head: str = "HEAD") -> int:
    return policy.main(
        [
            "--repo-root",
            str(repo),
            "security-suppressions-range",
            "--base",
            base,
            "--head",
            head,
        ]
    )


class TestRangeSuppressionGate:
    """The four policy properties the local hook enforces, now enforced in CI."""

    def test_clean_range_exits_zero(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            "import os\nprint(os)\nprint('added')\n", encoding="utf-8"
        )
        _commit(tmp_path, "no suppressions")
        assert _range_exit(tmp_path) == 0

    def test_net_new_suppression_fails(self, tmp_path: Path, capsys) -> None:
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "add a suppression")
        assert _range_exit(tmp_path) == 1
        assert "pkg/alpha.py" in capsys.readouterr().err

    def test_intra_file_move_passes(self, tmp_path: Path) -> None:
        """Relocating an existing suppression inside one file is not an addition."""
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "seed a suppression")
        _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"print('reordered')\nimport os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "move it down")
        assert _range_exit(tmp_path) == 0

    def test_cross_file_removal_earns_no_credit(self, tmp_path: Path) -> None:
        """Deleting a suppression in beta.py must not pay for adding one in alpha.py."""
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "beta.py").write_text(
            f"import sys  {NOQA}\nprint(sys)\n", encoding="utf-8"
        )
        _commit(tmp_path, "seed beta suppression")
        _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
        (tmp_path / "pkg" / "beta.py").write_text("import sys\nprint(sys)\n", encoding="utf-8")
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "trade beta for alpha")
        assert _range_exit(tmp_path) == 1

    def test_one_removal_cannot_pay_for_two_additions(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "seed one suppression")
        _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os\nprint(os)  {NOQA}\nprint('x')  {NOQA}\n",
            encoding="utf-8",
        )
        _commit(tmp_path, "remove one, add two")
        assert _range_exit(tmp_path) == 1

    def test_typing_suppressions_are_out_of_scope_by_design(self, tmp_path: Path) -> None:
        """The gate is a *security* suppression gate, not a suppression gate.

        SECURITY_SUPPRESSION_RE matches nosec, nosemgrep, noqa, lgtm[, codeql[,
        and cwe-suppress. It does not match ``type: ignore``, which is a typing
        suppression carrying no security signal and governed by its own counter
        at ``scripts/ci/type_ignore_count_ratchet.py``. Pinning the boundary
        here so a future reader does not mistake this pass for a hole, and so
        widening the regex cannot happen silently.
        """
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os\nprint(os)\nprint('x')  {TYPE_IGNORE}\n", encoding="utf-8"
        )
        _commit(tmp_path, "add a typing suppression")
        assert _range_exit(tmp_path) == 0


class TestRangeResolutionFailsClosed:
    """A gate that cannot read history must not report success (issue #4068)."""

    def test_unresolvable_head_is_a_config_error_not_a_pass(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        assert _range_exit(tmp_path, head="refs/heads/does-not-exist") == 2

    def test_no_merge_base_is_a_config_error_not_a_pass(self, tmp_path: Path) -> None:
        """Two unrelated histories share no merge base; a shallow clone looks the same."""
        _init_repo(tmp_path)
        _git(tmp_path, "checkout", "--orphan", "unrelated")
        _git(tmp_path, "rm", "-rf", "--cached", ".")
        (tmp_path / "solo.py").write_text("print('solo')\n", encoding="utf-8")
        orphan = _commit(tmp_path, "unrelated root")
        assert _range_exit(tmp_path, base="origin/main", head=orphan) == 2

    def test_config_error_names_the_remedy(self, tmp_path: Path, capsys) -> None:
        _init_repo(tmp_path)
        _range_exit(tmp_path, base="refs/heads/missing-base")
        assert "fetch-depth: 0" in capsys.readouterr().err


    def test_collector_failure_exits_config_error_not_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A git failure inside the collector must not read as "no violations".

        ``_added_suppression_violations`` returns None (not an empty list) when
        it cannot read rename data from git. Treating that None as clean is the
        #4068 silent-pass shape exactly: the gate reports success on a run where
        it inspected nothing.
        """
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "add a suppression")
        monkeypatch.setattr(policy, "_collect_suppression_violations", lambda *_: None)
        assert _range_exit(tmp_path) == 2

    def test_reporter_is_the_only_source_of_the_failing_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pin the reporter as load-bearing: neutering it must not go green."""
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text(
            f"import os  {NOQA}\nprint(os)\n", encoding="utf-8"
        )
        _commit(tmp_path, "add a suppression")
        seen: list[list[str]] = []
        real = policy._report_suppression_violations

        def spy(violations, subject):
            seen.append(list(violations))
            return real(violations, subject)

        monkeypatch.setattr(policy, "_report_suppression_violations", spy)
        assert _range_exit(tmp_path) == 1
        assert seen and seen[0], "the reporter must receive the collected violations"


class TestRangeAndPushShareOneImplementation:
    """Both entry points must decide with the same collector, or they can disagree."""

    def test_range_resolution_uses_a_two_dot_merge_base_spec(self, tmp_path: Path) -> None:
        base = _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text("import os\nprint(os)\n#x\n", encoding="utf-8")
        head = _commit(tmp_path, "advance topic")
        update = policy.resolve_range_update("origin/main", head, tmp_path)
        assert update.base == base
        assert update.head == head
        assert update.range_spec == f"{base}..{head}"

    def test_collector_returns_empty_list_for_a_clean_range(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "pkg" / "alpha.py").write_text("import os\nprint(os)\n#y\n", encoding="utf-8")
        head = _commit(tmp_path, "clean change")
        update = policy.resolve_range_update("origin/main", head, tmp_path)
        assert policy._collect_suppression_violations([update], tmp_path) == []


class TestWorkflowWiring:
    """The gate is worthless if CI never calls it, which was the whole of #4061.

    These assertions parse the workflow rather than substring-matching it. A
    substring assertion passes when the step name is deleted and only the
    ``run:`` line survives, which is a step that no longer exists as far as
    Actions is concerned. Structure is the only honest check.
    """

    @pytest.fixture(scope="class")
    def workflow(self) -> dict:
        text = (_ROOT / ".github" / "workflows" / "pr-validation.yml").read_text(encoding="utf-8")
        return yaml.safe_load(text)

    @staticmethod
    def _gate_steps(workflow: dict) -> list[dict]:
        steps = workflow["jobs"]["validate-pr"]["steps"]
        return [
            step
            for step in steps
            if "security-suppressions-range" in str(step.get("run", ""))
        ]

    def test_validate_pr_runs_the_range_subcommand(self, workflow: dict) -> None:
        gate_steps = self._gate_steps(workflow)
        assert len(gate_steps) == 1, "expected exactly one suppression-range step"
        assert gate_steps[0].get("name"), "a step with no name is not a step"

    def test_gate_passes_both_pull_request_shas_via_env(self, workflow: dict) -> None:
        """A range gate given the wrong endpoints silently scans nothing.

        The SHAs bind through ``env:`` rather than interpolating into the shell.
        ``scripts/validate_workflows.py`` rejects the inline form as an
        expression-injection risk, and it is right to: the uniform rule is
        cheaper to enforce than case-by-case reasoning about which context
        values happen to be hex today.
        """
        step = self._gate_steps(workflow)[0]
        env = step.get("env") or {}
        assert env.get("BASE_SHA") == "${{ github.event.pull_request.base.sha }}"
        assert env.get("HEAD_SHA") == "${{ github.event.pull_request.head.sha }}"
        run = step["run"]
        assert '--base "$BASE_SHA"' in run
        assert '--head "$HEAD_SHA"' in run
        assert "${{" not in run, "interpolating into the run block reopens the injection path"

    def test_gate_runs_outside_the_bot_skip_guard(self, workflow: dict) -> None:
        """Bots push code too; exempting them would defeat the gate."""
        step = self._gate_steps(workflow)[0]
        assert "should-run" not in str(step.get("if", ""))

    def test_every_checkout_in_the_job_fetches_full_history(self, workflow: dict) -> None:
        """A merge base needs history; depth-1 makes the gate exit 2 on every PR."""
        checkouts = [
            step
            for step in workflow["jobs"]["validate-pr"]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert checkouts, "validate-pr must check out the repository"
        for checkout in checkouts:
            depth = (checkout.get("with") or {}).get("fetch-depth")
            assert depth == 0, f"checkout {checkout.get('name')!r} has fetch-depth {depth!r}"
