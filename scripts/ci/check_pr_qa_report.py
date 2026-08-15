#!/usr/bin/env python3
"""Check whether code changes in a PR have a matching QA report."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIB_DIR = _REPO_ROOT / ".claude" / "lib"
sys.path.insert(0, str(_LIB_DIR))

from paths import artifact_dir  # noqa: E402
from qa_report import (  # noqa: E402
    load_qa_report,
    post_qa_code_changes,
    resolve_session_log_path,
    session_qa_binding,
    validate_qa_report,
)

CONFIG_ERROR = 2
EXTERNAL_ERROR = 3
LOGIC_ERROR = 1
CODE_EXTENSIONS = {".ps1", ".cs", ".ts", ".js", ".py", ".yml", ".yaml", ".json"}

# The closing and reference keywords a PR body uses to link an issue. A bare
# "#123" is not a link under this pattern: an issue number is only read from a
# keyword, so a passing mention of another issue cannot pull in its QA report.
LINKED_ISSUE = re.compile(r"(?i)\b(?:close[sd]?|fixe?[sd]?|fix|resolve[sd]?|refs?)\s+#(\d+)")


def _append_output(name: str, value: str) -> int:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return CONFIG_ERROR
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")
    return 0


def _changed_files(repository: str, pr_number: str) -> list[str] | None:
    """Current and previous PR filenames, or None when the API call failed.

    Issue #4068: this ran with ``check=False`` and never read the return code,
    so a `gh` failure produced empty stdout, ``_has_code_changes([])`` was
    False, and the step wrote ``has_code_changes=False`` and exited 0. A PR full
    of code then graded as "no code changes, QA report not required". Returning
    None rather than an empty list keeps "the API broke" distinguishable from
    "the PR genuinely touches nothing", which is the distinction the caller
    needs to fail loudly.

    Renames include both paths so moving code under ``.agents/`` cannot hide it
    from the QA requirement.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{pr_number}/files",
            "--paginate",
            "--jq",
            ".[] | .filename, (.previous_filename // empty)",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _has_code_changes(changed_files: list[str]) -> bool:
    for filename in changed_files:
        if filename.startswith(".agents/"):
            continue
        if Path(filename).suffix in CODE_EXTENSIONS:
            return True
    return False


def _find_qa_report(pr_number: str) -> Path | None:
    reports = sorted(
        artifact_dir("qa", base=Path.cwd()).glob(f"*pr-{pr_number}*.md")
    )
    return reports[0] if reports else None


def _pr_body(repository: str, pr_number: str) -> str | None:
    """The PR body text, or None when the API call failed.

    Mirrors ``_pr_head_sha`` above: same ``gh api`` shape, same ``check=False``,
    same read of ``returncode`` before the output is trusted. It returns None
    instead of raising because the caller reports a failed lookup as
    EXTERNAL_ERROR, the way ``_changed_files`` does, rather than as an invalid
    report.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{pr_number}",
            "--jq",
            ".body",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _linked_issues(body: str) -> list[str]:
    """Issue numbers the body links, deduplicated and in numeric order."""
    return sorted({match.group(1) for match in LINKED_ISSUE.finditer(body)}, key=int)


def _find_issue_qa_report(issue_numbers: list[str]) -> Path | None:
    qa_dir = artifact_dir("qa", base=Path.cwd())
    for issue_number in issue_numbers:
        reports = sorted(qa_dir.glob(f"*issue-{issue_number}*.md"))
        if reports:
            return reports[0]
    return None


def _resolve_qa_report(
    repository: str,
    pr_number: str,
) -> tuple[Path | None, int | None]:
    """The QA report for this PR, plus an exit code when the lookup itself failed.

    Issue #5096: a report named for the PR number cannot be written before the
    PR exists, so the first push of every code PR failed this gate and paid a
    rename commit plus a second full push cycle. A report named for an issue the
    PR body links can be written up front, so it is accepted when no PR-numbered
    report exists. The PR-numbered name stays preferred, and whichever report
    resolves goes through ``_validate_report`` unchanged.
    """
    report = _find_qa_report(pr_number)
    if report is not None:
        return report, None
    body = _pr_body(repository, pr_number)
    if body is None:
        print(
            f"::error::gh api failed for repos/{repository}/pulls/{pr_number}",
            file=sys.stderr,
        )
        return None, EXTERNAL_ERROR
    return _find_issue_qa_report(_linked_issues(body)), None


def _resolve_commit(commit: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=_REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    resolved = result.stdout.strip()
    return resolved or None


def _load_session_log(session_log: str) -> tuple[Path, dict[str, Any]]:
    configured_root = artifact_dir("sessions", base=Path.cwd()).resolve()
    default_root = (Path.cwd() / ".agents" / "sessions").resolve()
    roots = dict.fromkeys((configured_root, default_root))
    path = next(
        (
            candidate
            for root in roots
            if (candidate := resolve_session_log_path(
                session_log,
                sessions_root=root,
            )).is_file()
        ),
        resolve_session_log_path(
            session_log,
            sessions_root=configured_root,
        ),
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"QA report session log not found: {session_log}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"QA report session log is invalid JSON: {session_log}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"QA report session log is not a JSON object: {session_log}")
    return path, data


def _pr_head_sha(repository: str, pr_number: str) -> str:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{pr_number}",
            "--jq",
            ".head.sha",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ValueError("Could not resolve PR head SHA for QA validation")
    head = result.stdout.strip()
    if len(head) != 40:
        raise ValueError(f"PR head SHA is not a full commit: {head!r}")
    return head


def _validate_report(repository: str, pr_number: str, report: Path) -> None:
    metadata = load_qa_report(report)
    _session_path, session_data = _load_session_log(metadata.session_log)
    binding = session_qa_binding(
        session_data,
        session_log=metadata.session_log,
        resolve_commit=_resolve_commit,
    )
    validate_qa_report(report, binding)
    changed_after_qa = post_qa_code_changes(
        metadata.commit,
        _pr_head_sha(repository, pr_number),
        repo_root=_REPO_ROOT,
    )
    if changed_after_qa:
        raise ValueError(
            "QA report is stale; code changed after its commit: "
            + ", ".join(changed_after_qa)
        )


def _write_output_or_error(name: str, value: str) -> int | None:
    output_result = _append_output(name, value)
    return None if output_result == 0 else output_result


def _record_qa_report_found(qa_report: Path) -> int:
    output_error = _write_output_or_error("qa_report_exists", "true")
    if output_error is not None:
        return output_error
    output_error = _write_output_or_error("qa_report", qa_report.name)
    if output_error is not None:
        return output_error
    print(f"✓ QA report found: {qa_report.name}")
    return 0


def _record_invalid_qa_report(exc: ValueError) -> int:
    output_error = _write_output_or_error("qa_report_exists", "false")
    if output_error is not None:
        return output_error
    print(f"::error::Invalid QA report: {exc}")
    return LOGIC_ERROR


def _record_no_qa_required() -> int:
    output_error = _write_output_or_error("qa_report_exists", "N/A")
    if output_error is not None:
        return output_error
    print("No code changes, QA report not required")
    return 0


def _record_missing_qa_report() -> int:
    output_error = _write_output_or_error("qa_report_exists", "false")
    if output_error is not None:
        return output_error
    print("::error::No QA report found for code changes")
    return LOGIC_ERROR


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    print("Checking for QA report...")
    changed_files = _changed_files(repository, pr_number)
    if changed_files is None:
        print(
            f"::error::gh api failed for repos/{repository}/pulls/{pr_number}/files",
            file=sys.stderr,
        )
        return EXTERNAL_ERROR
    has_code_changes = _has_code_changes(changed_files)
    output_error = _write_output_or_error(
        "has_code_changes",
        str(has_code_changes),
    )
    if output_error is not None:
        return output_error
    if not has_code_changes:
        return _record_no_qa_required()
    qa_report, lookup_error = _resolve_qa_report(repository, pr_number)
    if lookup_error is not None:
        return lookup_error
    if qa_report:
        try:
            _validate_report(repository, pr_number, qa_report)
        except ValueError as exc:
            return _record_invalid_qa_report(exc)
        return _record_qa_report_found(qa_report)
    return _record_missing_qa_report()


if __name__ == "__main__":
    raise SystemExit(main())
