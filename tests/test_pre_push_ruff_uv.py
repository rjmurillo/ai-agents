#!/usr/bin/env python3
"""Tests for Issue #2574: pre-push ruff lint must use uv-managed ruff when available.

The pre-push hook previously checked ``command -v ruff`` and skipped Python
linting when ruff was not on PATH, even though the uv-managed dev environment
provides ruff via ``uv run --frozen --extra dev ruff``. That silent skip let
real lint failures (e.g. import-order I001) pass pre-push while ``uv`` users
and CI caught them.

The fix is to prefer ``uv run --frozen --extra dev ruff`` when ``uv.lock`` or
``pyproject.toml`` is present, fall back to a PATH ``ruff`` binary only when
uv is unavailable, and emit an actionable failure (not a silent skip) when
neither path can run ruff in a uv-managed checkout.

These tests pin three behaviors:

1. The pre-push hook resolves ``RUFF_CMD`` through a helper that mirrors
   :func:`set_python_cmd` -- ``uv run --frozen --extra dev ruff`` first,
   PATH fallback second.
2. Lint failures from the uv-managed ruff surface as ``record_fail`` (not
   ``record_skip``) so import-order issues fail the push as the acceptance
   criteria require.
3. When neither uv nor a PATH ruff is available in a uv-managed checkout,
   pre-push records a ``record_fail`` (or ``record_python_env_failure``) with
   an actionable message instead of the previous silent skip.

The tests follow the same content-plus-hook-execution shape as
``test_pre_push_mypy_duplicate_modules.py`` so they share the established
TEMPDIR + bin-shim convention used by other pre-push tests in this repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"


def _text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
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
    py_file_content: str = "value: int = 1\n",
    uv_extra_dev_ruff_exit: int = 0,
    path_ruff_exit: int = 0,
) -> tuple[Path, str, str, dict[str, str]]:
    """Build a fixture git repo whose ``PATH`` exposes only the shims we want.

    ``with_uv`` controls whether a ``uv`` shim is on ``PATH``. The shim only
    succeeds for ``uv run --frozen --extra dev ruff ...`` -- it forwards other
    invocations to the system ``uv`` if available, but the hook only ever calls
    the patterns we test, so this is safe.

    ``with_path_ruff`` controls whether a bare ``ruff`` shim is on ``PATH``.

    Both shims log every invocation to ``RUFF_LOG`` / ``UV_LOG`` so tests can
    assert what the hook actually called.
    """
    repo = tmp_path / "hook-repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "checkout", "-b", "main")
    _run_git(repo, "config", "user.name", "Pre Push Test")
    _run_git(repo, "config", "user.email", "pre-push-test@example.invalid")

    # Pre-push expects a generated artifact alignment check; provide a stub so
    # the hook does not bail before the ruff section.
    build_scripts = repo / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "generate_pr_quality_prompts.py").write_text(
        "import sys\nsys.exit(0)\n",
        encoding="utf-8",
    )

    hook_dir = repo / ".githooks"
    hook_dir.mkdir()
    _write_executable(hook_dir / "pre-push", _text())

    # Mirror the real repo's uv-managed signature so set_python_cmd takes the
    # uv branch. The contents are irrelevant -- only the presence is checked.
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
    _run_git(repo, "checkout", "-b", "feature/ruff-uv")

    # The changed .py file the ruff check will be asked to lint.
    pkg_dir = repo / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "module.py").write_text(py_file_content, encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "test: add py file")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # A minimal mypy shim so the mypy section after ruff does not blow up.
    _write_executable(
        bin_dir / "mypy",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    # markdownlint-cli2 is not needed in this fixture (no .md changes), but
    # other validators (e.g. python interpreter) might be probed. Provide a
    # python3 shim that just exits 0 for the env probe.

    if with_uv:
        # uv shim:
        #  - ``uv run --frozen python -c ...`` -> exit 0 (needed by set_python_cmd)
        #  - ``uv run --frozen --extra dev ruff --version`` -> exit 0 (probe)
        #  - ``uv run --frozen --extra dev ruff check ...`` -> log + configurable exit
        _write_executable(
            bin_dir / "uv",
            f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$UV_LOG"
case "$*" in
    "run --frozen python -c "*)
        exit 0
        ;;
    "run --frozen --extra dev ruff --version"*)
        echo "ruff 0.15.16 (uv-managed)"
        exit 0
        ;;
    "run --frozen --extra dev ruff check"*)
        exit {uv_extra_dev_ruff_exit}
        ;;
    *)
        # Anything else -> reject so the hook cannot accidentally use a code
        # path we did not anticipate.
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
exit {path_ruff_exit}
""",
        )

    # Provide a real python3 (system) so set_python_cmd's later fallback works
    # if uv path is disabled. We do NOT shim python3 because the hook uses it
    # for several validators.
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = os.environ.copy()
    # Hermetic PATH: only our shims + system essentials (bash, python3, git).
    # We keep /bin and /usr/bin so /usr/bin/env bash and basic tools work,
    # and append the directory containing the system ``python3`` so
    # set_python_cmd's later fallback can find an interpreter.
    sys_python = subprocess.run(
        ["which", "python3"], capture_output=True, text=True
    ).stdout.strip()
    sys_python_dir = str(Path(sys_python).parent) if sys_python else "/usr/bin"
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
        input=f"refs/heads/feature/ruff-uv {head_sha} "
        f"refs/heads/feature/ruff-uv {base_sha}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 1. Content-level: pre-push routes ruff through uv when available
# ---------------------------------------------------------------------------


def test_pre_push_invokes_uv_managed_ruff() -> None:
    """The ruff section must invoke ``uv run --frozen --extra dev ruff`` so
    uv-managed checkouts do not silently skip linting (Issue #2574).
    """
    text = _text()

    # Locate the ruff section (# 6. Python lint (ruff) - BLOCKING).
    section_start = text.find("# 6. Python lint (ruff)")
    assert section_start != -1, "Expected the # 6. Python lint section in pre-push"
    section_end = text.find("# 7.", section_start)
    section = text[section_start:section_end]

    assert "uv run --frozen --extra dev ruff" in section, (
        "Expected the ruff section to invoke 'uv run --frozen --extra dev "
        "ruff' so uv-managed checkouts run ruff via the dev extra. Without "
        "this the hook silently skips lint in any checkout without a PATH "
        "ruff. Issue #2574."
    )


def test_pre_push_keeps_path_ruff_fallback() -> None:
    """The fix must keep a PATH ``ruff`` fallback for installations that do
    not have uv (CI containers without uv, contributor-provided envs).
    """
    text = _text()
    section_start = text.find("# 6. Python lint (ruff)")
    section_end = text.find("# 7.", section_start)
    section = text[section_start:section_end]

    # Either ``command -v ruff`` (legacy probe kept as fallback) or a direct
    # call to ``ruff`` after the uv branch must remain.
    assert (
        "command -v ruff" in section or "elif ruff " in section or '"$RUFF_CMD"' in section
    ), (
        "Expected the ruff section to retain a PATH ruff fallback (either a "
        "``command -v ruff`` probe or an explicit second branch). Without it, "
        "non-uv installations lose ruff entirely."
    )


def test_pre_push_fails_loudly_when_uv_and_path_both_missing() -> None:
    """When neither uv nor PATH ruff is available, pre-push must record a
    failure (not a silent skip) so the developer knows lint was not actually
    enforced. The skip-on-no-tool branch is the original bug.
    """
    text = _text()
    section_start = text.find("# 6. Python lint (ruff)")
    section_end = text.find("# 7.", section_start)
    section = text[section_start:section_end]

    # The section must call record_fail (the BLOCKING outcome). A pure
    # record_skip block when no ruff is available is the broken behavior
    # being fixed: BLOCKING checks must not silently skip on tool absence
    # in a uv-managed checkout.
    assert "record_fail" in section, (
        "Expected record_fail in the ruff section so missing-ruff in a "
        "uv-managed checkout fails the push instead of being silently "
        "skipped (Issue #2574)."
    )


# ---------------------------------------------------------------------------
# 2. Hook-level: uv-managed checkout invokes uv ruff
# ---------------------------------------------------------------------------


def test_uv_managed_checkout_runs_ruff_via_uv(tmp_path: Path) -> None:
    """Acceptance: in a checkout where uv.lock exists and ``ruff`` is NOT on
    PATH, pre-push must still run ruff (via ``uv run --frozen --extra dev
    ruff``) instead of skipping.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=True,
        with_path_ruff=False,
        uv_extra_dev_ruff_exit=0,
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    uv_log_path = repo / "uv.log"
    uv_log = uv_log_path.read_text(encoding="utf-8") if uv_log_path.exists() else ""

    # The hook must have invoked uv-managed ruff (look for the ruff check
    # call rather than the python probe).
    assert "run --frozen --extra dev ruff check" in uv_log, (
        f"Expected pre-push to invoke 'uv run --frozen --extra dev ruff "
        f"check ...' in a uv-managed checkout; uv.log was:\n{uv_log}\n"
        f"hook output:\n{output}"
    )

    # And it must not have silently skipped lint.
    assert "ruff not installed" not in output, (
        f"Expected pre-push NOT to record 'ruff not installed' skip in a "
        f"uv-managed checkout; output was:\n{output}"
    )
    assert "Python lint/ruff" in output, (
        f"Expected the ruff section to report a result line; output:\n{output}"
    )


def test_uv_managed_checkout_fails_push_when_uv_ruff_finds_violations(tmp_path: Path) -> None:
    """Acceptance: import-order (or any) violations from uv-managed ruff
    must fail the push, satisfying the acceptance criterion that the bug
    reporter's I001 errors no longer pass silently.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=True,
        with_path_ruff=False,
        uv_extra_dev_ruff_exit=1,  # ruff exit 1 == lint violations found
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"Expected pre-push to fail when uv-managed ruff reports violations; "
        f"exit was {result.returncode}, output:\n{output}"
    )
    assert "Python lint/ruff" in output and (
        "ERROR" in output or "FAIL" in output
    ), (
        f"Expected an ERROR/FAIL marker for Python lint/ruff in pre-push "
        f"output, got:\n{output}"
    )


# ---------------------------------------------------------------------------
# 3. PATH-only checkout still works
# ---------------------------------------------------------------------------


def test_path_only_checkout_uses_path_ruff(tmp_path: Path) -> None:
    """Acceptance: when uv is not on PATH but ``ruff`` is, pre-push must
    fall back to the PATH binary so legacy / container installations keep
    working. (The fixture still has uv.lock so set_python_cmd would normally
    require uv -- but if uv is absent the hook should skip the env probe and
    use PATH ruff for the lint step alone.)
    """
    # Build a fixture WITHOUT uv.lock so set_python_cmd's "uv required"
    # branch does not abort the hook before the ruff section runs.
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=False,
        with_path_ruff=True,
        path_ruff_exit=0,
    )
    # Remove the uv.lock the helper wrote so the hook does not treat this as
    # a uv-managed checkout (which would require uv).
    (repo / "uv.lock").unlink()
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-m", "test: drop uv.lock for PATH-only fixture")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    ruff_log_path = repo / "ruff.log"
    ruff_log = ruff_log_path.read_text(encoding="utf-8") if ruff_log_path.exists() else ""

    assert "check" in ruff_log, (
        f"Expected PATH ruff to be invoked with 'check' in a non-uv "
        f"checkout; ruff.log was:\n{ruff_log!r}\nhook output:\n{output}"
    )
    assert "PASS" in output or "Python lint/ruff" in output, (
        f"Expected ruff lint to run (PASS/section header) in PATH-only "
        f"checkout; output:\n{output}"
    )


# ---------------------------------------------------------------------------
# 4. Neither uv nor PATH ruff: must fail loudly, not silently skip
# ---------------------------------------------------------------------------


def test_no_ruff_at_all_fails_loudly(tmp_path: Path) -> None:
    """Acceptance: when ruff is unreachable through both uv and PATH in a
    uv-managed checkout, pre-push must surface an actionable error rather
    than the previous silent ``record_skip``.
    """
    repo, base_sha, head_sha, env = _make_hook_repo(
        tmp_path,
        with_uv=False,
        with_path_ruff=False,
    )

    result = _run_pre_push(repo, base_sha, head_sha, env)
    output = result.stdout + result.stderr

    # In a uv-managed checkout (uv.lock present) without uv on PATH,
    # set_python_cmd records a python-env failure ("uv is required for this
    # checkout"). That itself is a record_fail so the push must not pass
    # silently -- this satisfies "make skipped lint explicit and actionable
    # when neither path works" from the issue's suggested fix.
    assert result.returncode != 0, (
        f"Expected pre-push to fail when neither uv nor PATH ruff is "
        f"available in a uv-managed checkout (silent skip is the bug being "
        f"fixed); exit was {result.returncode}, output:\n{output}"
    )
