#!/usr/bin/env python3
"""Block git commit when prompt/command/skill behavioral changes lack eval evidence.

Claude Code PreToolUse hook that enforces ADR-057: Prompt Behavioral Evaluation.
When staged files include prompt, command, or skill definition changes, checks
for eval evidence before allowing the commit.

Evidence sources (any one satisfies the gate):
    1. Eval results file exists: .agents/eval-results/<date>-*.json
    2. Staged eval results alongside the prompt change
    3. SKIP_PROMPT_EVAL=1 environment variable (with justification)

Hook Type: PreToolUse
Matcher: Bash(git commit*)
Exit Codes (Claude Hook Semantics):
    0 = Always (uses JSON decision payload for deny/allow semantics)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

# Patterns for files that require behavioral eval per ADR-057
_PROMPT_PATTERNS = [
    re.compile(r"^\.claude/commands/.*\.md$"),
    re.compile(r"^\.github/prompts/.*\.md$"),
    re.compile(r"^\.agents/security/prompts/.*\.md$"),
]

_AGENT_PATTERNS = [
    re.compile(r"^\.claude/agents/(?!CLAUDE\.md|README\.md|INDEX\.md).*\.md$"),
]

_SKILL_PATTERNS = [
    re.compile(r"^\.claude/skills/.*/SKILL\.md$"),
]

# Security-critical paths (ADR-057: stricter tier)
_SECURITY_CRITICAL_PATTERNS = [
    re.compile(r"security", re.IGNORECASE),
    re.compile(r"pr-quality-gate-security"),
]


def get_staged_files() -> list[str]:
    """Get list of staged file paths."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def classify_staged_behavioral(files: list[str]) -> dict[str, list[str]]:
    """Classify staged files into behavioral change categories."""
    classified = {"prompts": [], "agents": [], "skills": []}

    for f in files:
        for pattern in _PROMPT_PATTERNS:
            if pattern.match(f):
                classified["prompts"].append(f)
                break
        for pattern in _AGENT_PATTERNS:
            if pattern.match(f):
                classified["agents"].append(f)
                break
        for pattern in _SKILL_PATTERNS:
            if pattern.match(f):
                classified["skills"].append(f)
                break

    return classified


def has_eval_evidence(project_dir: str, staged_files: list[str]) -> bool:
    """Check for behavioral eval evidence.

    Sources:
    1. Eval results file from today in .agents/eval-results/
    2. Staged eval results JSON files
    3. Eval output files in scripts/eval/
    """
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # Check 1: Eval results directory
    eval_dir = Path(project_dir) / ".agents" / "eval-results"
    if eval_dir.is_dir():
        try:
            results = list(eval_dir.glob(f"{today}-*.json"))
            if results:
                return True
        except OSError:
            pass

    # Check 2: Staged eval results
    for f in staged_files:
        if "eval" in f.lower() and f.endswith(".json"):
            return True

    # Check 3: Recent eval output in scripts/eval/
    eval_output_dir = Path(project_dir) / "scripts" / "eval"
    if eval_output_dir.is_dir():
        try:
            for result_file in eval_output_dir.glob("*.json"):
                stat = result_file.stat()
                age_hours = (
                    datetime.now(tz=UTC).timestamp() - stat.st_mtime
                ) / 3600
                if age_hours < 24:
                    return True
        except OSError:
            pass

    return False


def is_security_critical(files: list[str]) -> bool:
    """Check if any matched files are security-critical."""
    for f in files:
        for pattern in _SECURITY_CRITICAL_PATTERNS:
            if pattern.search(f):
                return True
    return False


def main() -> int:
    """Main hook entry point."""
    if skip_if_consumer_repo("prompt-eval-gate"):
        return 0

    # Bypass: environment variable
    if os.environ.get("SKIP_PROMPT_EVAL") == "1":
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        input_data = json.loads(input_json)
        tool_input = input_data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        command = tool_input.get("command", "")
        if "git commit" not in command:
            return 0

        staged = get_staged_files()
        if not staged:
            return 0

        classified = classify_staged_behavioral(staged)
        behavioral_files = (
            classified["prompts"] + classified["agents"] + classified["skills"]
        )

        if not behavioral_files:
            return 0

        project_dir = get_project_directory()
        if has_eval_evidence(project_dir, staged):
            return 0

        # Behavioral files staged without eval evidence
        security_tag = ""
        if is_security_critical(behavioral_files):
            security_tag = " [SECURITY-CRITICAL: requires 5 runs, 100% pass]"

        file_list = "\n".join(f"  - {f}" for f in behavioral_files)
        category_summary = []
        if classified["prompts"]:
            category_summary.append(f"{len(classified['prompts'])} prompt(s)")
        if classified["agents"]:
            category_summary.append(f"{len(classified['agents'])} agent(s)")
        if classified["skills"]:
            category_summary.append(f"{len(classified['skills'])} skill(s)")

        output = {
            "decision": "deny",
            "reason": (
                f"ADR-057 PROMPT EVAL GATE: Behavioral evaluation required "
                f"before committing {', '.join(category_summary)}.{security_tag}\n\n"
                f"Matched files:\n{file_list}\n\n"
                "Run the eval suite:\n"
                "  python3 scripts/eval/eval-suite.py\n\n"
                "Or run targeted prompt eval:\n"
                "  python3 scripts/eval/eval-prompt-change.py "
                "--prompt <file> --scenarios <scenarios.json> --base-ref main\n\n"
                "Bypass: Set SKIP_PROMPT_EVAL=1 (document justification in PR)"
            ),
        }
        print(json.dumps(output, separators=(",", ":")))
        return 0

    except Exception as exc:
        # Fail-open for this gate (eval infrastructure may not be set up)
        print(
            f"Prompt eval gate warning: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
