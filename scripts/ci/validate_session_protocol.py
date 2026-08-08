"""Validate one session log and record its verdict for aggregation.

Runs as one leg of a matrix, one leg per changed session log. Writes three
files under ``validation-results/`` that the aggregate job globs, and exits
with the validator's own exit code so the leg turns red on a failure.

The artifact name is derived from the parent directory as well as the file
stem, because ``sessions/x.json`` and ``archive/x.json`` would otherwise
collide in the merged artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.session_scope import (  # noqa: E402  (path set above)
    committed_session_validation_modes,
)

_RESULTS = Path("validation-results")
_SUMMARY = Path("validation-summary.json")
_RESULT_MD = Path("validation-result.md")

_MARKDOWN_UNSUPPORTED = (
    "Markdown session logs are no longer supported.",
    "session-init now emits JSON; convert this file to JSON or remove it from the PR.",
    "See PR #2359 and issue #2384 for context.",
)


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def escapes_workspace(session_file: str) -> bool:
    """True when the path resolves outside the checkout.

    The matrix feeds this from ``detect_session_logs.py``, whose pattern is
    anchored under ``.agents/sessions/``, and git will not store a path with an
    unnormalised ``..`` segment, so a traversal cannot reach here today. Both
    of those are invariants owned elsewhere. This is the local one.
    """
    root = Path.cwd().resolve()
    candidate = (root / session_file).resolve()
    return candidate != root and root not in candidate.parents


def artifact_name(session_file: str) -> str:
    """Return a name unique across directories, not just across file stems."""
    path = Path(session_file)
    return f"{path.parent.name}-{path.stem}"


def must_failure_count(exit_code: int) -> int:
    """Read the MUST-failure count the validator reported.

    No summary file means the validator died before writing one. Report 1
    rather than a confident 0, because the enforcement step tests ``> 0`` and
    would read any lower sentinel as "nothing to enforce" (issue #3365).
    """
    if _SUMMARY.is_file():
        try:
            summary = json.loads(_SUMMARY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("::warning::Validation summary is unreadable; assuming a MUST failure")
            return 1
        try:
            return int(summary["must_failures"])
        except (KeyError, TypeError, ValueError):
            print("::warning::Validation summary has no MUST count; assuming a MUST failure")
            return 1
    if exit_code != 0:
        print("::warning::No validation summary produced; assuming a MUST failure")
        return 1
    return 0


def _validation_mode_args(session_file: str) -> tuple[list[str] | None, str | None]:
    normalized = Path(session_file).as_posix()
    modes = committed_session_validation_modes([normalized], Path.cwd())
    if modes is None:
        return None, (
            "ERROR: unable to determine which committed session logs were added by HEAD; "
            "refusing to guess creation-mode"
        )
    mode = modes.get(normalized, "full")
    if mode == "creation":
        return ["--creation-mode"], None
    if mode == "existing":
        return ["--existing-log"], None
    return [], None


def _write_results(name: str, verdict: str, must_failures: int, findings: str) -> None:
    _RESULTS.mkdir(parents=True, exist_ok=True)
    (_RESULTS / f"{name}-verdict.txt").write_text(f"{verdict}\n", encoding="utf-8")
    (_RESULTS / f"{name}-must-failures.txt").write_text(f"{must_failures}\n", encoding="utf-8")
    (_RESULTS / f"{name}-findings.txt").write_text(findings, encoding="utf-8")


def _emit_output(name: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"artifact-name={name}\n")


def validate(session_file: str) -> tuple[int, str]:
    """Run the validator. Returns (exit_code, findings)."""
    if Path(session_file).suffix != ".json":
        return 1, "\n".join(_MARKDOWN_UNSUPPORTED)
    mode_args, error = _validation_mode_args(session_file)
    if error is not None or mode_args is None:
        return 1, error or "ERROR: could not determine validation mode"
    completed = _run(
        [
            sys.executable,
            "./scripts/validate_session_json.py",
            session_file,
            *mode_args,
            "--json-output",
            str(_SUMMARY),
        ]
    )
    return completed.returncode, completed.stdout + completed.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", default=os.environ.get("SESSION_FILE", ""))
    args = parser.parse_args(argv)

    session_file = args.session_file
    if not session_file:
        print("::error::session-file is required", file=sys.stderr)
        return 2

    if escapes_workspace(session_file):
        print(
            f"::error::Refusing a session path outside the checkout: {session_file}",
            file=sys.stderr,
        )
        return 2

    name = artifact_name(session_file)
    _emit_output(name)

    if not Path(session_file).exists():
        print(f"File {session_file} was deleted - skipping validation")
        findings = f"# Session Validation: {session_file}\n\nResult: SKIPPED (file deleted)\n"
        _RESULT_MD.write_text(findings, encoding="utf-8")
        _write_results(name, "SKIPPED", 0, findings)
        return 0

    exit_code, findings = validate(session_file)
    verdict = "COMPLIANT" if exit_code == 0 else "NON_COMPLIANT"
    must_failures = must_failure_count(exit_code)

    if exit_code != 0:
        print(f"::group::Session validation findings for {Path(session_file).name}")
        print(findings)
        print("::endgroup::")

    _RESULT_MD.write_text(findings, encoding="utf-8")
    _write_results(name, verdict, must_failures, findings)

    print(f"Validation complete for {session_file}")
    print(f"  Verdict: {verdict}")
    print(f"  MUST failures: {must_failures}")
    print(f"  Exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
