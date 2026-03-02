#!/usr/bin/env python3
"""Migrate markdown session logs to JSON format.

Parses markdown session logs and converts them to structured JSON.

Exit Codes:
    0  - Success: Migration completed
    1  - Error: Invalid path or conversion failed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path


def find_checklist_item(content: str, pattern: str) -> dict:
    """Look for table rows with [x] matching the pattern."""
    regex = re.compile(
        r"\|[^|]*\|[^|]*" + pattern + r"[^|]*\|\s*\[x\]\s*\|([^|]*)\|",
        re.IGNORECASE,
    )
    match = regex.search(content)
    if match:
        return {"Complete": True, "Evidence": match.group(1).strip()}
    return {"Complete": False, "Evidence": ""}


def parse_work_log(content: str) -> list[dict]:
    """Extract work log entries from markdown content."""
    entries: list[dict] = []

    # Pattern 1: Work Log section
    wl_match = re.search(
        r"##\s*Work\s*Log\s*\n(.+?)(?=\n##\s|\Z)", content, re.DOTALL
    )
    if wl_match:
        wl_content = wl_match.group(1).strip()
        if not re.match(r"^\s*###\s*\[Task/Topic\]", wl_content) and len(wl_content) >= 50:
            for section in re.finditer(
                r"###\s*(.+?)\n((?:(?!###).)+)", wl_content, re.DOTALL
            ):
                title = section.group(1).strip()
                body = section.group(2).strip()
                if re.match(r"\[.+?\]", title) or len(body) < 20:
                    continue
                result_text = re.sub(r"\n+", " ", body)[:200]
                entry: dict = {"action": title, "result": result_text}
                files = re.findall(
                    r"`([^`]+\.(?:ps1|psm1|md|json|yml|yaml|txt))`", body
                )
                if files:
                    entry["files"] = files
                entries.append(entry)

    # Pattern 2: Common work-related headings
    if not entries:
        headings = [
            "Changes Made",
            "Decisions Made",
            "Files Modified",
            "Files Changed",
            "Test Results",
            "Outcomes",
            "Deliverables",
        ]
        for heading in headings:
            h_match = re.search(
                rf"##\s*{heading}\s*\n(.+?)(?=\n##\s|\Z)", content, re.DOTALL
            )
            if not h_match:
                continue
            section_content = h_match.group(1).strip()
            subsections = list(
                re.finditer(
                    r"###\s*(.+?)\n((?:(?!###).)+)", section_content, re.DOTALL
                )
            )
            if subsections:
                for sub in subsections:
                    title = sub.group(1).strip()
                    body = sub.group(2).strip()
                    if len(body) <= 20:
                        continue
                    result_text = re.sub(r"\n+", " ", body)[:150]
                    entry = {"action": f"{heading}: {title}", "result": result_text}
                    files = list(
                        dict.fromkeys(
                            re.findall(
                                r"`([^`]+\.(?:ps1|psm1|md|json|yml|yaml|txt|csv))`",
                                body,
                            )
                        )
                    )
                    if files:
                        entry["files"] = files
                    entries.append(entry)
            elif len(section_content) > 30:
                result_text = re.sub(r"\n+", " ", section_content)[:200]
                entries.append({"action": heading, "result": result_text})

    return entries


def convert_from_markdown(content: str, file_name: str) -> dict:
    """Convert markdown session log to JSON structure."""
    # Session number
    session_num = 0
    m = re.search(r"session-(\d+)", file_name)
    if m:
        session_num = int(m.group(1))

    # Date
    session_date = ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", file_name)
    if m:
        session_date = m.group(1)

    # Branch
    branch = ""
    m = re.search(r"\*?\*?Branch\*?\*?:\s*([^\n\r]+)", content)
    if m:
        branch = m.group(1).strip().replace("`", "")

    # Commit
    commit = ""
    m = re.search(
        r"\*?\*?(?:Starting\s+)?Commit\*?\*?:\s*`?([a-f0-9]{7,40})`?", content
    )
    if m:
        commit = m.group(1)

    # Objective
    objective = ""
    m = re.search(r"##\s*Objective\s*\n+([^\n#]+)", content)
    if m:
        objective = m.group(1).strip()

    # Session start checks
    session_start = {
        "serenaActivated": find_checklist_item(content, "activate_project"),
        "serenaInstructions": find_checklist_item(content, "initial_instructions"),
        "handoffRead": find_checklist_item(content, r"HANDOFF\.md"),
        "sessionLogCreated": find_checklist_item(
            content, r"Create.*session.*log|session.*log.*exist|this.*file"
        ),
        "skillScriptsListed": find_checklist_item(content, r"skill.*script"),
        "usageMandatoryRead": find_checklist_item(content, "usage-mandatory"),
        "constraintsRead": find_checklist_item(content, "CONSTRAINTS"),
        "memoriesLoaded": find_checklist_item(content, "memor"),
        "branchVerified": find_checklist_item(
            content, r"verify.*branch|branch.*verif|declare.*branch"
        ),
        "notOnMain": find_checklist_item(content, r"not.*main|Confirm.*main"),
        "gitStatusVerified": find_checklist_item(content, r"git.*status"),
        "startingCommitNoted": find_checklist_item(
            content, r"starting.*commit|Note.*commit"
        ),
    }

    must_keys = [
        "serenaActivated", "serenaInstructions", "handoffRead",
        "sessionLogCreated", "skillScriptsListed", "usageMandatoryRead",
        "constraintsRead", "memoriesLoaded", "branchVerified", "notOnMain",
    ]
    should_keys = ["gitStatusVerified", "startingCommitNoted"]
    for k in must_keys:
        session_start[k]["level"] = "MUST"
    for k in should_keys:
        session_start[k]["level"] = "SHOULD"

    # Session end checks
    session_end = {
        "checklistComplete": find_checklist_item(
            content, r"Complete.*session.*log|session.*log.*complete|all.*section"
        ),
        "handoffNotUpdated": {
            "level": "MUST NOT",
            "Complete": False,
            "Evidence": find_checklist_item(
                content, r"HANDOFF.*read-only|Update.*HANDOFF"
            ).get("Evidence", ""),
        },
        "serenaMemoryUpdated": find_checklist_item(
            content, r"Serena.*memory|Update.*memory|memory.*updat"
        ),
        "markdownLintRun": find_checklist_item(
            content, r"markdownlint|markdown.*lint|Run.*lint"
        ),
        "changesCommitted": find_checklist_item(
            content, r"Commit.*change|change.*commit"
        ),
        "validationPassed": find_checklist_item(
            content, r"Validate.*Session|validation.*pass|Route.*qa"
        ),
        "tasksUpdated": find_checklist_item(
            content, r"PROJECT-PLAN|task.*checkbox"
        ),
        "retrospectiveInvoked": find_checklist_item(content, "retrospective"),
    }

    end_must = [
        "checklistComplete", "serenaMemoryUpdated", "markdownLintRun",
        "changesCommitted", "validationPassed",
    ]
    end_should = ["tasksUpdated", "retrospectiveInvoked"]
    for k in end_must:
        session_end[k]["level"] = "MUST"
    for k in end_should:
        session_end[k]["level"] = "SHOULD"

    work_log = parse_work_log(content)

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate markdown session logs to JSON format."
    )
    parser.add_argument(
        "path", help="Path to markdown session log or directory of logs."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing.",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Path not found: {path}", file=sys.stderr)
        sys.exit(1)

    files: list[Path] = []
    if path.is_dir():
        session_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-session")
        files = [
            f for f in sorted(path.glob("*.md")) if session_pattern.match(f.name)
        ]
    else:
        files = [path]

    migrated: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for file in files:
        json_path = file.with_suffix(".json")
        if json_path.exists() and not args.force:
            skipped.append(file.name)
            continue

        try:
            content = file.read_text(encoding="utf-8")
            session = convert_from_markdown(content, file.name)

            if args.dry_run:
                print(f"[DRY RUN] Would migrate: {file.name} -> {json_path.name}")
            else:
                json_path.write_text(
                    json.dumps(session, indent=2), encoding="utf-8"
                )
                print(f"[OK] Migrated: {file.name} -> {json_path.name}")

            migrated.append(str(json_path))
        except Exception as e:
            print(f"[FAIL] {file.name}: {e}")
            failed.append(file.name)

    print(f"\n=== Migration Summary ===")
    print(f"Migrated: {len(migrated)}")
    print(f"Skipped (JSON exists): {len(skipped)}")
    print(f"Failed: {len(failed)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
