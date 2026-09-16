"""Change-class coverage and stdin provenance for gate_latency.py (REQ-027).

Split from ``test_gate_latency.py`` to keep both modules under the project's
500-line taste-lint ceiling, the same reason the CLI and io tests are their
own modules. The concern here is narrower than the core module's: what the
``CHANGE_CLASSES`` table has to contain for AC-08's job coverage to hold, and
whether the ref line git gives a real pre-push hook reaches the subprocess.

``subprocess.run`` is monkeypatched throughout: no test in this module runs a
real lefthook hook.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from wcmatch import glob

from scripts.metrics import gate_latency as gl
from tests.gc_real_git import git

REAL_CAPTURED_STDOUT = (
    "  \x1b[38;2;56;56;56m  ----\x1b[m\n"
    "summary: (done in 0.19 seconds)\n"
    "\u2713 security-suppressions-staged (0.19 seconds)\n"
)


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    _write(root, "lefthook.yml", "pre-commit:\n  jobs:\n    - name: a-job\n      run: 'true'\n")
    for paths in gl.CHANGE_CLASSES.values():
        for rel in paths:
            _write(root, rel, "placeholder\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture repo")
    return root


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

# --- stdin provenance and the hooks change class -----------------------------


def test_positive_change_classes_cover_every_glob_gated_job_issue_5318_names() -> None:
    """AC-08: each of the five pre-push jobs #5318 item 1 names must be reachable.

    ``security-scan`` declares no glob, so it runs on every pre-push and needs
    no class of its own. The other four are glob-gated, and each needs a class
    whose file list matches its glob.
    """
    assert set(gl.CHANGE_CLASSES) >= {"python", "skills", "workflows", "hooks"}
    assert gl.CHANGE_CLASSES["hooks"] == ("build/scripts/generate_hooks.py",)


def _declared_globs(hook: str, job_name: str) -> list[str]:
    """Every glob `job_name` declares under `hook` in the real lefthook.yml."""
    config = yaml.safe_load(Path("lefthook.yml").read_text(encoding="utf-8"))
    globs: list[str] = []

    def _walk(entries: list[Any]) -> None:
        for entry in entries:
            group = entry.get("group")
            if isinstance(group, dict):
                _walk(group.get("jobs", []))
            if entry.get("name") == job_name:
                declared = entry.get("glob", [])
                globs.extend(declared if isinstance(declared, list) else [declared])

    _walk(config[hook]["jobs"])
    return globs


@pytest.mark.parametrize(
    ("change_class", "job_name"),
    [
        ("hooks", "hook-anchoring-e2e"),
        ("python", "python-type-check"),
        ("skills", "plugin-load-e2e"),
        ("workflows", "workflow-local-run"),
    ],
)
def test_positive_each_change_class_file_matches_its_job_glob(
    change_class: str, job_name: str
) -> None:
    """AC-08 holds only while each class's file still matches its job's glob.

    `gate_latency_classes.py` asserts these four mappings in prose, read off
    `lefthook.yml` once. Prose does not fail when the config moves. Without
    this, a glob change would silently stop a class from firing the job it
    exists to measure, and the suite would stay green while the artifact kept
    claiming coverage.
    """
    globs = _declared_globs("pre-push", job_name)
    assert globs, f"{job_name} declares no glob in lefthook.yml"

    files = gl.CHANGE_CLASSES[change_class]
    assert files, f"change class {change_class} names no file"

    # lefthook.yml sets `glob_matcher: doublestar`, so the patterns use `**`
    # and brace alternation. pathlib.PurePath.match understands neither, and
    # would report a false mismatch for `.github/workflows/**/*.{yml,yaml}`.
    flags = glob.GLOBSTAR | glob.BRACE
    for rel in files:
        assert any(
            glob.globmatch(rel, pattern, flags=flags) for pattern in globs
        ), f"{rel} matches none of {job_name}'s globs {globs}"

def test_positive_change_class_file_lists_all_exist_in_this_repository() -> None:
    """AC-08's startup validation over the real, shipped table."""
    from scripts.ci.lefthook_budget_model import REPO_ROOT

    for name, paths in gl.CHANGE_CLASSES.items():
        for rel in paths:
            missing_msg = f"change class {name!r} names a missing path {rel!r}"
            assert (REPO_ROOT / rel).is_file(), missing_msg

def test_negative_missing_change_class_path_exits_2(repo: Path) -> None:
    """A class whose file has been deleted is a configuration problem, not a zero sample."""
    (repo / "README.md").unlink()

    assert gl.main(["--repo", str(repo), "--hook", "pre-commit", "--change-class", "markdown"]) == 2

