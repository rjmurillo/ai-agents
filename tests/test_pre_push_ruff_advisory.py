#!/usr/bin/env python3
"""Tests for Issue #2592: pre-push ruff lint must be advisory (warn, not block).

After PR #2577 fixed Issue #2574, the pre-push hook treats any ruff finding
on a changed `.py` file as a BLOCKING failure. The repository carries a large
pre-existing ruff backlog (the pytest CI ruff step runs with
``continue-on-error: true`` for exactly this reason, see
``.github/workflows/pytest.yml`` Issue #2194). Because the pre-push hook lints
*whole files* (not just diff hunks), editing any legacy file now forces
unrelated cleanup of every pre-existing finding in that file before the push
will succeed, even for a one-line change.

The contract going forward, matching the CI policy until the backlog reaches
zero:

* When ruff is *resolvable* (uv-managed or PATH) and finds violations on the
  changed files, pre-push records a ``record_warn`` (non-blocking). It still
  prints the findings and an actionable fix command so the developer can clean
  them when convenient, but the push is not blocked.
* When ruff is *not* resolvable at all in a uv-managed checkout, pre-push
  still records ``record_fail`` -- this is the original #2574 bug (silent skip
  on missing tooling) and remains BLOCKING. The advisory policy applies only
  to the lint *output*, never to missing tooling.

Once the backlog reaches zero, flip both the CI ``continue-on-error: true``
step in pytest.yml and the pre-push warn back to ``record_fail`` together so
the gate strictness lives in one place.

These tests pin two behaviors:

1. Content-level: the ruff section emits ``record_warn`` (not ``record_fail``)
   on lint output, and the warn message references Issue #2592 so future
   maintainers know why the gate is advisory.
2. Hook-level: a uv-managed checkout whose ruff returns exit 1 (violations
   found) exits 0 from pre-push, prints the ruff output, and records a WARN.

The fixtures intentionally mirror ``test_pre_push_ruff_uv.py`` so the shared
shim convention keeps test infrastructure changes localized.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def _ruff_section() -> str:
    text = _text()
    start = text.index("# 6. Python lint (ruff)")
    end = text.index("# 7. Python type check", start)
    return text[start:end]


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        encoding="utf-8",
        env={**os.environ, "LC_ALL": "C"},
        timeout=30,
    )
    return result.stdout.strip()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _make_hook_repo(
    tmp_path: Path,
    *,
    with_uv: bool,
    with_path_ruff: bool,
    uv_extra_dev_ruff_exit: int = 0,
    path_ruff_exit: int = 0,
) -> tuple[Path, str, str, dict[str, str]]:
    """Build a fixture git repo whose ``PATH`` exposes only the shims we want.

    Mirrors ``test_pre_push_ruff_uv.py::_make_hook_repo``. Kept local rather
    than imported so a future change to the shared fixture cannot accidentally
    invalidate either test file's contract.
    """
    repo = tmp_path / "hook-repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.name", "Pre Push Test")
    _run_git(repo, "config", "user.email", "pre-push-test@example.invalid")

    # Stub the generated-artifact alignment check so the hook reaches the ruff
    # section in fixture repos that do not carry the full repo layout.
    build_scripts = repo / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "generate_pr_quality_prompts.py").write_text(
        "import sys\nsys.exit(0)\n",
        encoding="utf-8",
    )

    hook_dir = repo / ".githooks"
    hook_dir.mkdir()
    _write_executable(hook_dir / "pre-push", _text())

    (repo / "pyproject.toml").write_text(
        "[project]\nname='hook-fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text("# fixture\n", encoding="utf-8")

    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _run_git(repo, "checkout", "-b", "feature/ruff-advisory")

    pkg_dir = repo / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "module.py").write_text("value: int = 1\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: add py file")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_executable(
        bin_dir / "mypy",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    if with_uv:
        _write_executable(
            bin_dir / "uv",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$UV_LOG"
case "$*" in
    "run --frozen python -c "*)
        exit 0
        ;;
    "run --frozen python "*)
        # set_python_cmd resolves PYTHON_CMD=(uv run --frozen python). Later
        # phases (e.g. Phase 5b drift detection) invoke it with a script path.
        # Treat the call as successful so the fixture exits 0 unless the
        # specific ruff branch under test produces a failure.
        exit 0
        ;;
    "run --frozen --extra dev ruff --version"*)
        echo "ruff 0.15.16 (uv-managed)"
        exit 0
        ;;
    "run --frozen --extra dev ruff check"*)
        # Print a representative finding so tests can see ruff output is
        # surfaced to the developer even when the gate is advisory.
        echo "pkg/module.py:1:1: E501 fixture finding for #2592"
        exit {uv_extra_dev_ruff_exit}
        ;;
    *)
        echo "uv shim: unsupported invocation: $*" >&2
        exit 99
        ;;
esac
""",
        )
    if with_path_ruff:
        _write_executable(
            bin_dir / "ruff",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$RUFF_LOG"
if [ "$1" = "--version" ]; then
    echo "ruff 0.15.16 (path)"
    exit 0
fi
echo "pkg/module.py:1:1: E501 fixture finding for #2592"
exit {path_ruff_exit}
""",
        )

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = os.environ.copy()
    sys_python_dir = str(Path(sys.executable).parent)
    env["PATH"] = os.pathsep.join([str(bin_dir), "/usr/bin", "/bin", sys_python_dir])
    env["RUFF_LOG"] = str(repo / "ruff.log")
    env["UV_LOG"] = str(repo / "uv.log")
    env["TMPDIR"] = str(scratch)

    return repo, base_sha, head_sha, env


def _run_pre_push(
    repo: Path,
    base_sha: str,
    head_sha: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / ".githooks" / "pre-push")],
        cwd=repo,
        input=f"refs/heads/feature/ruff-advisory {head_sha} "
        f"refs/heads/feature/ruff-advisory {base_sha}\n",
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 1. Content-level: ruff findings warn (not fail) and message names #2592
# ---------------------------------------------------------------------------


def test_ruff_findings_record_warn_not_fail() -> None:
    """Lint output on changed files must call ``record_warn``, never
    ``record_fail``. The latter blocks the push; matching the CI
    ``continue-on-error: true`` policy (Issue #2194) requires advisory until
    the backlog reaches zero.
    """
    section = _ruff_section()

    # The lint-output branch (after the ruff check fails) must record_warn.
    assert 'record_warn "Python lint/ruff' in section, (
        "Expected the ruff lint-output branch to call record_warn so a "
        "pre-existing finding in a changed file does not force unrelated "
        "cleanup (Issue #2592). The CI step is continue-on-error: true; "
        "pre-push must not be stricter than CI until the backlog is zero."
    )

    # And the lint-output branch must NOT call record_fail. The only
    # record_fail invocation that may remain in this section is the
    # "no ruff at all" branch (Issue #2574), which is missing-tooling, not
    # pre-existing findings. Strip shell comment lines first so a comment
    # such as "Flip back to record_fail when ..." does not false-positive.
    non_comment_lines = [
        line
        for line in section.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    fail_calls = [
        line
        for line in non_comment_lines
        if "record_fail" in line and "no ruff available" not in line
    ]
    assert not fail_calls, (
        f"Expected the ruff section to have no record_fail calls on lint "
        f"output (only on missing tooling). Found: {fail_calls}. "
        f"Issue #2592 requires advisory output."
    )


def test_ruff_warn_message_cites_2592_policy() -> None:
    """The warn message must point future readers at the policy contract.
    Without the cross-reference, the first person to see WARN on lint will
    flip it back to record_fail without realizing the CI step is
    continue-on-error: true.
    """
    section = _ruff_section()

    assert "#2592" in section, (
        "Expected the ruff section to cite Issue #2592 in the rationale so "
        "the advisory policy is discoverable. Without this the next "
        "maintainer will assume the warn is a bug and flip it back to "
        "record_fail without knowing the CI gate is continue-on-error: true."
    )


# ---------------------------------------------------------------------------
# 2. Content-level: missing-ruff branch stays BLOCKING (Issue #2574)
# ---------------------------------------------------------------------------


def test_missing_ruff_still_record_fails() -> None:
    """The #2574 fix (no silent skip when ruff is unreachable) must stay
    BLOCKING. The #2592 fix is narrow: lint *output* is advisory; missing
    *tooling* still fails the push so the developer fixes their environment.
    """
    section = _ruff_section()
    assert 'record_fail "Python lint/ruff (no ruff available)"' in section, (
        "Expected the 'no ruff available' branch to remain record_fail "
        "(Issue #2574). The #2592 advisory fix narrows only to lint output, "
        "never to missing tooling."
    )


# ---------------------------------------------------------------------------
# 3. Hook-level: violations from uv-managed ruff warn but do not block
# ---------------------------------------------------------------------------


def test_uv_managed_checkout_warns_on_violations_does_not_block(tmp_path: Path) -> None:
    """Acceptance: when uv-managed ruff exits non-zero (violations found) on a
    changed file, pre-push must exit 0, surface the findings in output, and
    record a WARNING. This is the central #2592 contract: the push proceeds.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=True,
        with_path_ruff=False,
        uv_extra_dev_ruff_exit=1,  # ruff exit 1 == violations found
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    # The push MUST NOT fail on lint output.
    assert result.returncode == 0, (
        f"Expected pre-push to succeed when uv-managed ruff reports "
        f"violations (advisory per Issue #2592); exit was "
        f"{result.returncode}.\nOutput:\n{output}"
    )

    # Output must still surface the ruff finding so the developer sees what
    # the lint output was (the gate is advisory, not silent).
    assert "E501 fixture finding for #2592" in output, (
        f"Expected ruff finding to be surfaced even when advisory; "
        f"otherwise the developer has no visibility. Output:\n{output}"
    )

    # And it must be recorded as a WARNING (record_warn -> WARNING: prefix).
    assert "WARNING:" in output and "Python lint/ruff" in output, (
        f"Expected a WARNING-level Python lint/ruff line in pre-push "
        f"output; got:\n{output}"
    )


def test_uv_managed_checkout_passes_clean_when_ruff_returns_zero(tmp_path: Path) -> None:
    """Acceptance: when uv-managed ruff exits 0 (clean), pre-push must still
    record a PASS for the ruff step. This guards against an over-broad
    advisory fix that would warn even on clean output.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=True,
        with_path_ruff=False,
        uv_extra_dev_ruff_exit=0,
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"Expected pre-push to succeed on clean ruff output; exit was "
        f"{result.returncode}.\nOutput:\n{output}"
    )
    # PASS must be reported, not WARNING, for the ruff step when output is
    # clean. record_pass emits via echo_success which writes PASS:.
    assert "PASS" in output and "Python lint/ruff" in output, (
        f"Expected a PASS line for Python lint/ruff when ruff exits 0; "
        f"got:\n{output}"
    )
    # And no WARNING should be attached to the ruff step on clean output.
    assert "WARNING" not in output.split("Python lint/ruff")[0].split("\n")[-1], (
        f"Did not expect a WARNING preceding the Python lint/ruff line on "
        f"clean ruff output; got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 4. Hook-level: missing tooling still BLOCKS (Issue #2574 preservation)
# ---------------------------------------------------------------------------


def test_no_ruff_still_fails_loudly(tmp_path: Path) -> None:
    """Acceptance: the #2574 contract -- missing ruff in a uv-managed
    checkout records a failure -- survives the #2592 advisory fix.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=False,
        with_path_ruff=False,
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"Expected pre-push to fail when neither uv nor PATH ruff is "
        f"available in a uv-managed checkout (Issue #2574 contract must "
        f"survive Issue #2592); exit was {result.returncode}.\n"
        f"Output:\n{output}"
    )
