#!/usr/bin/env python3
"""Migrate markdown session logs to JSON format.

Parses markdown session log files and converts them to the JSON schema
used by validate_session_json.py for deterministic validation.

Exit codes follow ADR-035:
    0 - Success
    1 - Error: Invalid path or conversion failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate markdown session logs to JSON format.",
    )
    parser.add_argument(
        "path", help="Path to markdown session log file or directory of logs.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing JSON files.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be migrated without writing files.",
    )
    return parser


def _find_checklist_item(content: str, pattern: str) -> dict:
    """Look for table rows with [x] that match the pattern."""
    rx = re.compile(
        r"\|[^|]*\|[^|]*" + pattern + r"[^|]*\|\s*\[x\]\s*\|([^|]*)\|",
        re.IGNORECASE,
    )
    m = rx.search(content)
    if m:
        return {"Complete": True, "Evidence": m.group(1).strip()}
    return {"Complete": False, "Evidence": ""}


def _parse_work_log(content: str) -> list[dict]:
    """Parse work log entries from markdown content."""
    entries: list[dict] = []

    # Pattern 1: ## Work Log section
    m = re.search(r"(?s)##\s*Work\s*Log\s*\n(.+?)(?=\n##\s|\Z)", content)
    if m:
        work_content = m.group(1).strip()
        if not re.match(r"^\s*###\s*\[Task/Topic\]", work_content) and len(work_content) >= 50:
            for sm in re.finditer(r"###\s*(.+?)\n((?:(?!###).)+)", work_content, re.DOTALL):
                title = sm.group(1).strip()
                body = sm.group(2).strip()
                if re.match(r"\[.+?\]", title) or len(body) < 20:
                    continue
                entry: dict = {
                    "action": title,
                    "result": re.sub(r"\n+", " ", body)[:200],
                }
                files = re.findall(
                    r"`([^`]+\.(?:ps1|psm1|md|json|yml|yaml|txt|py))`", body,
                )
                if files:
                    entry["files"] = files
                entries.append(entry)

    # Pattern 2: Common work headings
    if not entries:
        headings = [
            "Changes Made", "Decisions Made", "Files Modified",
            "Files Changed", "Test Results", "Outcomes", "Deliverables",
        ]
        for heading in headings:
            rx = re.compile(
                r"(?s)##\s*" + re.escape(heading) + r"\s*\n(.+?)(?=\n##\s|\Z)",
            )
            hm = rx.search(content)
            if not hm:
                continue
            section = hm.group(1).strip()
            subs = list(re.finditer(r"###\s*(.+?)\n((?:(?!###).)+)", section, re.DOTALL))
            if subs:
                for sub in subs:
                    title = sub.group(1).strip()
                    body = sub.group(2).strip()
                    if len(body) <= 20:
                        continue
                    entry = {
                        "action": f"{heading}: {title}",
                        "result": re.sub(r"\n+", " ", body)[:150],
                    }
                    files = list(dict.fromkeys(
                        re.findall(r"`([^`]+\.(?:ps1|psm1|md|json|yml|yaml|txt|csv|py))`", body),
                    ))
                    if files:
                        entry["files"] = files
                    entries.append(entry)
            elif len(section) > 30:
                entries.append({
                    "action": heading,
                    "result": re.sub(r"\n+", " ", section)[:200],
                })

    return entries


def _convert_markdown_session(content: str, filename: str) -> dict:
    """Convert a markdown session log to JSON structure."""
    # Extract session number from filename
    session_num = 0
    m = re.search(r"session-(\d+)", filename)
    if m:
        session_num = int(m.group(1))

    # Extract date from filename
    session_date = ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", filename)
    if m:
        session_date = m.group(1)

    # Extract branch
    branch = ""
    m = re.search(r"\*?\*?Branch\*?\*?:\s*([^\n\r]+)", content)
    if m:
        branch = m.group(1).strip().replace("`", "")

    # Extract commit
    commit = ""
    m = re.search(r"\*?\*?(?:Starting\s+)?Commit\*?\*?:\s*`?([a-f0-9]{7,40})`?", content)
    if m:
        commit = m.group(1)

    # Extract objective
    objective = ""
    m = re.search(r"##\s*Objective\s*\n+([^\n#]+)", content)
    if m:
        objective = m.group(1).strip()

    # Build session start checks
    _session_log_pat = (
        r"Create.*session.*log|session.*log.*exist|this.*file"
    )
    _branch_pat = r"verify.*branch|branch.*verif|declare.*branch"
    session_start = {
        "serenaActivated": _find_checklist_item(content, "activate_project"),
        "serenaInstructions": _find_checklist_item(
            content, "initial_instructions",
        ),
        "handoffRead": _find_checklist_item(content, r"HANDOFF\.md"),
        "sessionLogCreated": _find_checklist_item(
            content, _session_log_pat,
        ),
        "skillScriptsListed": _find_checklist_item(
            content, "skill.*script",
        ),
        "usageMandatoryRead": _find_checklist_item(
            content, "usage-mandatory",
        ),
        "constraintsRead": _find_checklist_item(content, "CONSTRAINTS"),
        "memoriesLoaded": _find_checklist_item(content, "memor"),
        "branchVerified": _find_checklist_item(content, _branch_pat),
        "notOnMain": _find_checklist_item(
            content, r"not.*main|Confirm.*main",
        ),
        "gitStatusVerified": _find_checklist_item(
            content, "git.*status",
        ),
        "startingCommitNoted": _find_checklist_item(
            content, r"starting.*commit|Note.*commit",
        ),
    }

    must_start = [
        "serenaActivated", "serenaInstructions", "handoffRead",
        "sessionLogCreated", "skillScriptsListed", "usageMandatoryRead",
        "constraintsRead", "memoriesLoaded", "branchVerified", "notOnMain",
    ]
    for key in must_start:
        session_start[key]["level"] = "MUST"
    for key in ["gitStatusVerified", "startingCommitNoted"]:
        session_start[key]["level"] = "SHOULD"

    # Build session end checks
    _checklist_pat = (
        r"Complete.*session.*log|session.*log.*complete|all.*section"
    )
    _handoff_pat = r"HANDOFF.*read-only|Update.*HANDOFF"
    _memory_pat = r"Serena.*memory|Update.*memory|memory.*updat"
    _lint_pat = r"markdownlint|markdown.*lint|Run.*lint"
    _validation_pat = r"Validate.*Session|validation.*pass|Route.*qa"
    session_end = {
        "checklistComplete": _find_checklist_item(
            content, _checklist_pat,
        ),
        "handoffNotUpdated": {
            "level": "MUST NOT",
            "Complete": False,
            "Evidence": _find_checklist_item(
                content, _handoff_pat,
            ).get("Evidence", ""),
        },
        "serenaMemoryUpdated": _find_checklist_item(
            content, _memory_pat,
        ),
        "markdownLintRun": _find_checklist_item(
            content, _lint_pat,
        ),
        "changesCommitted": _find_checklist_item(
            content, r"Commit.*change|change.*commit",
        ),
        "validationPassed": _find_checklist_item(
            content, _validation_pat,
        ),
        "tasksUpdated": _find_checklist_item(
            content, r"PROJECT-PLAN|task.*checkbox",
        ),
        "retrospectiveInvoked": _find_checklist_item(
            content, "retrospective",
        ),
    }

    must_end = ["checklistComplete", "serenaMemoryUpdated", "markdownLintRun",
                "changesCommitted", "validationPassed"]
    for key in must_end:
        session_end[key]["level"] = "MUST"
    for key in ["tasksUpdated", "retrospectiveInvoked"]:
        session_end[key]["level"] = "SHOULD"

    work_log = _parse_work_log(content)

    return {
        "session": {
            "number": session_num,
            "date": session_date,
            "branch": branch,
            "startingCommit": commit,
            "objective": objective if objective else "[Migrated from markdown]",
        },
        "protocolCompliance": {
            "sessionStart": session_start,
            "sessionEnd": session_end,
        },
        "workLog": work_log,
        "endingCommit": "",
        "nextSteps": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.path

    # Get files to migrate
    files: list[str] = []
    if os.path.isdir(path):
        for name in os.listdir(path):
            if name.endswith(".md") and re.match(r"^\d{4}-\d{2}-\d{2}-session", name):
                files.append(os.path.join(path, name))
    elif os.path.isfile(path):
        files = [path]
    else:
        print(f"ERROR: Path not found: {path}", file=sys.stderr)
        return 1

    migrated: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for filepath in files:
        filename = os.path.basename(filepath)
        json_path = re.sub(r"\.md$", ".json", filepath)

        if os.path.exists(json_path) and not args.force:
            skipped.append(filename)
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            session = _convert_markdown_session(content, filename)

            if args.dry_run:
                json_name = os.path.basename(json_path)
                print(f"[DRY RUN] Would migrate: {filename} -> {json_name}")
                migrated.append(json_path)
            else:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(session, f, indent=2)
                json_name = os.path.basename(json_path)
                print(f"[OK] Migrated: {filename} -> {json_name}")
                migrated.append(json_path)
        except Exception as exc:
            print(f"[FAIL] {filename}: {exc}", file=sys.stderr)
            failed.append(filename)

    print("\n=== Migration Summary ===")
    print(f"Migrated: {len(migrated)}")
    print(f"Skipped (JSON exists): {len(skipped)}")
    print(f"Failed: {len(failed)}")

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
