"""Tests for the workflow wiring of scripts/ci/validate_session_protocol.py.

Split out of test_validate_session_protocol.py, which held both the script's own
behaviour and the workflow-graph assertions and crossed the 500-line taste limit.
These are the graph tests: which jobs run the script, and whether each job
installs what its entrypoints import.
"""


from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github/workflows/ai-session-protocol.yml"
_STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}
_SETUP_UV = "astral-sh/setup-uv"
_INSTALLERS = (_SETUP_UV, "actions/setup-python")
_PY_ENTRYPOINT = re.compile(r"python3?\s+(\S+\.py)")


def _jobs() -> dict[str, dict]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _installs_dependencies(job: dict) -> bool:
    for step in job.get("steps", []):
        if str(step.get("uses", "")).startswith(_INSTALLERS):
            return True
        if "pip install" in str(step.get("run") or ""):
            return True
    return False


def _entrypoints(job: dict) -> list[Path]:
    found: list[Path] = []
    for step in job.get("steps", []):
        for match in _PY_ENTRYPOINT.findall(str(step.get("run") or "")):
            script = _repo_file(match)
            if script is not None and script not in found:
                found.append(script)
    return found


def _repo_file(candidate: str) -> Path | None:
    """Resolve a repo-relative script reference, rejecting anything outside."""
    path = (_REPO_ROOT / candidate.removeprefix("./")).resolve()
    if not path.is_file() or not path.is_relative_to(_REPO_ROOT):
        return None
    return path


def _imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module]
    return []


def _local_module_path(module: str) -> Path | None:
    base = _REPO_ROOT / module.replace(".", "/")
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _spawned_script(node: ast.AST) -> Path | None:
    """A subprocess argv entry names its script as a plain string literal."""
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    if not node.value.endswith(".py"):
        return None
    return _repo_file(node.value)


def _closure(entry: Path) -> tuple[set[Path], set[str]]:
    """Every repo file the entrypoint reaches, and the third-party roots it needs."""
    pending = [entry.resolve()]
    files: set[Path] = set()
    third_party: set[str] = set()
    while pending:
        current = pending.pop()
        if current in files:
            continue
        files.add(current)
        tree = ast.parse(current.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if module.split(".")[0] in _STDLIB:
                    continue
                local = _local_module_path(module)
                if local is None:
                    third_party.add(module.split(".")[0])
                else:
                    pending.append(local.resolve())
            spawned = _spawned_script(node)
            if spawned is not None:
                pending.append(spawned)
    return files, third_party


class TestWorkflowWiring:
    def test_the_workflow_invokes_this_script(self) -> None:
        from pathlib import Path

        text = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath(".github/workflows/ai-session-protocol.yml")
            .read_text(encoding="utf-8")
        )
        assert "scripts/ci/validate_session_protocol.py" in text

    def test_the_upload_step_still_reads_the_artifact_name_output(self) -> None:
        from pathlib import Path

        text = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath(".github/workflows/ai-session-protocol.yml")
            .read_text(encoding="utf-8")
        )
        assert "steps.validate.outputs.artifact-name" in text


class TestEachJobInstallsWhatItsScriptsNeed:
    """A job that installs nothing may only run stdlib-only scripts.

    Issue #3806: the ``validate`` job called bare ``python3``, and the script
    chain it starts ends at ``scripts/validate_session_json.py``, which imports
    ``jsonschema`` at module level. That resolved only because
    ``ubuntu-24.04-arm`` happened to carry the package; it appears nowhere in
    that image's manifest, so an image re-roll turns the verdict into a
    traceback. The job now installs uv, and the guard below is derived from the
    workflow rather than a hand-kept script list, so the pairing cannot go
    stale the way the previous literal list did.

    The chain is a subprocess spawn, not an import, which is why an
    import-only scan missed it. ``_closure`` follows both.
    """

    def test_the_validate_job_installs_dependencies_through_uv(self) -> None:
        job = _jobs()["validate"]

        setup = [s for s in job["steps"] if str(s.get("uses", "")).startswith(_SETUP_UV)]
        runs = " ".join(str(s.get("run") or "") for s in job["steps"])

        assert setup, "the validate job needs setup-uv; its scripts import jsonschema"
        assert re.fullmatch(r"[0-9a-f]{40}", setup[0]["uses"].split("@", 1)[1]), (
            "pin the action to a commit SHA, not a floating tag"
        )
        assert "uv run --frozen python3 scripts/ci/validate_session_protocol.py" in runs

    def test_the_detect_changes_job_still_installs_nothing(self) -> None:
        """The fix is scoped: only the job with a third-party need pays for uv."""
        job = _jobs()["detect-changes"]

        assert not _installs_dependencies(job)
        assert "python3 scripts/ci/detect_session_logs.py" in " ".join(
            str(s.get("run") or "") for s in job["steps"]
        )

    def test_no_job_without_an_install_step_runs_a_third_party_script(self) -> None:
        offenders: list[str] = []
        for name, job in _jobs().items():
            if _installs_dependencies(job):
                continue
            for entry in _entrypoints(job):
                _, third_party = _closure(entry)
                if third_party:
                    rel = entry.relative_to(_REPO_ROOT)
                    offenders.append(f"{name} -> {rel} needs {sorted(third_party)}")

        assert not offenders, (
            "these jobs run bare python3 but reach a third-party package: "
            f"{offenders}. Add setup-uv to the job or make the script stdlib-only."
        )

    def test_every_job_that_shells_out_to_uv_installs_uv(self) -> None:
        """`uv run` without setup-uv is `uv: command not found`, not a verdict."""
        offenders: list[str] = []
        for name, job in _jobs().items():
            steps = job.get("steps", [])
            shells_out = any("uv run" in str(step.get("run") or "") for step in steps)
            installs_uv = any(str(step.get("uses", "")).startswith(_SETUP_UV) for step in steps)
            if shells_out and not installs_uv:
                offenders.append(name)

        assert not offenders, f"these jobs call uv without installing it: {offenders}"

    def test_the_third_party_guard_is_not_vacuous(self) -> None:
        """Both halves can empty out silently: the entrypoint regex and the closure."""
        scanned = [
            entry
            for job in _jobs().values()
            if not _installs_dependencies(job)
            for entry in _entrypoints(job)
        ]
        files, third_party = _closure(_REPO_ROOT / "scripts/ci/validate_session_protocol.py")

        assert scanned, "the entrypoint regex found nothing to scan"
        # Reached only through a line-continued run block, the shape most likely
        # to slip past the regex.
        assert _REPO_ROOT / ".github/scripts/post_issue_comment.py" in scanned
        # Reached only through a subprocess spawn, not an import.
        assert _REPO_ROOT / "scripts/validate_session_json.py" in files
        assert "jsonschema" in third_party
