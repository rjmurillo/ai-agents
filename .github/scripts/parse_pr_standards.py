#!/usr/bin/env python3
"""Parse PR description standards validation output for CI workflow.

Runs validate_pr_description.py and writes parsed results to GITHUB_OUTPUT.
Follows ADR-006 (thin workflows) by extracting parsing logic from YAML.

Exit codes follow ADR-035:
    0 - Success (results written to GITHUB_OUTPUT)
    1 - Validator produced no output or invalid JSON
    2 - Usage/environment error
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    title = os.environ.get("PR_TITLE", "")
    body = os.environ.get("PR_BODY", "")
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    if not title:
        print("PR_TITLE environment variable is required", file=sys.stderr)
        return 2

    # Write body to unique temp file to avoid concurrent run collisions
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    temp_dir = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix=f"pr-body-{run_id}-{attempt}-",
        suffix=".txt",
        delete=False,
        dir=temp_dir,
    ) as tmp:
        tmp.write(body)
        body_file = tmp.name

    try:
        validator = Path(
            ".claude/skills/github/scripts/pr/validate_pr_description.py"
        )
        try:
            result = subprocess.run(
                [sys.executable, str(validator), "--title", title, "--body-file", body_file],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            print("Validator timed out after 30 seconds", file=sys.stderr)
            _write_skip_outputs(github_output)
            return 1
        except OSError as exc:
            print(f"Failed to execute validator: {exc}", file=sys.stderr)
            _write_skip_outputs(github_output)
            return 2

        if result.returncode != 0 and result.returncode != 1:
            print(f"Validator failed with exit code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

        output = result.stdout.strip()
        if not output:
            print("Validator produced no output", file=sys.stderr)
            _write_skip_outputs(github_output)
            return 1

        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON from validator: {exc}", file=sys.stderr)
            _write_skip_outputs(github_output)
            return 1

        validations = data.get("Validations", {})
        keywords_status = validations.get("IssueKeywords", {}).get("Status", "SKIP")
        template_status = validations.get("TemplateCompliance", {}).get("Status", "SKIP")
        template_msg = validations.get("TemplateCompliance", {}).get("Message", "")
        warnings = "\n".join(data.get("Warnings", []))

        _write_outputs(github_output, keywords_status, template_status, template_msg, warnings)

        print(f"Issue keywords: {keywords_status}")
        print(f"Template compliance: {template_status} - {template_msg}")
        return 0

    finally:
        Path(body_file).unlink(missing_ok=True)


def _write_outputs(
    github_output: str,
    keywords_status: str,
    template_status: str,
    template_msg: str,
    warnings: str,
) -> None:
    """Write step outputs using heredoc-safe format for multiline values."""
    if not github_output:
        return

    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"keywords_status={keywords_status}\n")
        f.write(f"template_status={template_status}\n")
        # Use heredoc for potentially multiline values
        f.write("template_message<<TEMPLATE_EOF\n")
        f.write(f"{template_msg}\n")
        f.write("TEMPLATE_EOF\n")
        f.write("standards_warnings<<STANDARDS_EOF\n")
        f.write(f"{warnings}\n")
        f.write("STANDARDS_EOF\n")


def _write_skip_outputs(github_output: str) -> None:
    """Write SKIP outputs when validator fails."""
    _write_outputs(github_output, "SKIP", "SKIP", "", "")


if __name__ == "__main__":
    raise SystemExit(main())
