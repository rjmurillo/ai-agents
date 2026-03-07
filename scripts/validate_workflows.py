#!/usr/bin/env python3
"""
Validate GitHub Actions workflows locally before pushing.

This script validates:
1. YAML syntax correctness
2. Workflow file structure
3. Action SHA pinning (security requirement)
4. Workflow size (ADR-006: thin orchestration)
5. Required fields and common issues

Usage:
    python scripts/validate_workflows.py                    # Validate all workflows
    python scripts/validate_workflows.py path/to/file.yml   # Validate specific file
    python scripts/validate_workflows.py --changed          # Validate only changed files
    python scripts/validate_workflows.py --act              # Run with act (if installed)

Exit codes:
    0: All validations passed
    1: Validation errors found
    2: Script error (missing dependencies, etc.)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: PyYAML not found. Install with: uv pip install PyYAML", file=sys.stderr)
    sys.exit(2)


class WorkflowValidator:
    """Validates GitHub Actions workflow files."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.workflows_dir = repo_root / ".github" / "workflows"
        self.actions_dir = repo_root / ".github" / "actions"
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """Validate YAML syntax."""
        try:
            with open(file_path, encoding="utf-8") as f:
                yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.errors.append(f"{file_path}: YAML syntax error: {e}")
            return False

    def validate_workflow_structure(self, file_path: Path, content: dict[str, Any]) -> None:
        """Validate workflow has required fields and structure."""
        if "name" not in content:
            self.errors.append(f"{file_path}: Missing 'name' field")

        # YAML 1.1 quirk: 'on:' is parsed as True (boolean)
        # Check for both 'on' string and True boolean key
        if "on" not in content and True not in content:
            self.errors.append(f"{file_path}: Missing 'on' trigger")

        if "jobs" not in content:
            self.errors.append(f"{file_path}: Missing 'jobs' section")
        elif not isinstance(content["jobs"], dict):
            self.errors.append(f"{file_path}: 'jobs' must be a dictionary")
        elif not content["jobs"]:
            self.errors.append(f"{file_path}: 'jobs' section is empty")

    def validate_action_pinning(self, file_path: Path, content: dict[str, Any]) -> None:
        """Validate that actions use SHA pinning (security requirement)."""
        jobs = content.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step_idx, step in enumerate(steps):
                if "uses" in step:
                    uses = step["uses"]
                    # Skip local actions (start with ./)
                    if uses.startswith("./"):
                        continue

                    # Check for SHA pinning (format: owner/repo@sha # vX.Y.Z)
                    if "@" not in uses:
                        self.errors.append(
                            f"{file_path}: Job '{job_name}' step {step_idx + 1}: "
                            f"Action '{uses}' is not pinned"
                        )
                        continue

                    action_ref = uses.split("@")[1].split()[0]
                    # SHA is 40 characters hex
                    is_sha = len(action_ref) == 40
                    is_hex = all(c in "0123456789abcdef" for c in action_ref)
                    if not (is_sha and is_hex):
                        self.errors.append(
                            f"{file_path}: Job '{job_name}' step {step_idx + 1}: "
                            f"Action '{uses}' must use SHA pinning (found: {action_ref})"
                        )

    def validate_workflow_size(self, file_path: Path) -> None:
        """Validate workflow file size (ADR-006: thin orchestration)."""
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Filter out comments and empty lines for accurate count
        code_lines = [
            line for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

        if len(code_lines) > 100:
            self.warnings.append(
                f"{file_path}: Workflow has {len(code_lines)} lines of code "
                f"(ADR-006 recommends ≤100 for thin orchestration)"
            )

    def validate_concurrency(self, file_path: Path, content: dict[str, Any]) -> None:
        """Validate concurrency configuration."""
        if "concurrency" in content:
            concurrency = content["concurrency"]
            if isinstance(concurrency, dict):
                if "group" not in concurrency:
                    self.warnings.append(
                        f"{file_path}: Concurrency block missing 'group' field"
                    )
            elif not isinstance(concurrency, str):
                self.errors.append(
                    f"{file_path}: Concurrency must be a string or dict"
                )

    def validate_permissions(self, file_path: Path, content: dict[str, Any]) -> None:
        """Validate permissions are explicitly set (security requirement).

        Workflows without any permissions declaration run with broad default
        permissions. This is a security error, not just a best practice.
        """
        has_top_level = "permissions" in content

        if not has_top_level:
            # Check if every job declares its own permissions
            jobs = content.get("jobs", {})
            all_jobs_have_perms = jobs and all(
                "permissions" in job for job in jobs.values()
                if isinstance(job, dict)
            )
            if not all_jobs_have_perms:
                self.errors.append(
                    f"{file_path}: Missing 'permissions' declaration. "
                    f"Set top-level or per-job permissions to follow least-privilege."
                )

    # Patterns for attacker-controlled GitHub context data.
    # These can be set by external contributors via PR titles, branch names, etc.
    # See: https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/
    _DANGEROUS_PATTERNS: list[str] = [
        r"github\.event\.issue\.title",
        r"github\.event\.issue\.body",
        r"github\.event\.pull_request\.title",
        r"github\.event\.pull_request\.body",
        r"github\.event\.comment\.body",
        r"github\.event\.review\.body",
        r"github\.event\.review_comment\.body",
        r"github\.event\.discussion\.title",
        r"github\.event\.discussion\.body",
        r"github\.event\.pages\.\S*\.page_name",
        r"github\.event\.commits\.\S*\.message",
        r"github\.event\.commits\.\S*\.author\.name",
        r"github\.event\.commits\.\S*\.author\.email",
        r"github\.head_ref",
    ]

    def validate_expression_injection(
        self, file_path: Path, content: dict[str, Any]
    ) -> None:
        """Detect expression injection in run blocks.

        Flags ${{...}} in run: blocks when the expression references
        attacker-controlled data (issue titles, branch names, commit
        messages, comment bodies).
        """
        combined = re.compile("|".join(self._DANGEROUS_PATTERNS))
        jobs = content.get("jobs", {})
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps", [])
            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                run_block = step.get("run")
                if not isinstance(run_block, str):
                    continue
                for match in re.finditer(r"\$\{\{(.+?)\}\}", run_block):
                    expr = match.group(1).strip()
                    if combined.search(expr):
                        self.errors.append(
                            f"{file_path}: Job '{job_name}' step {step_idx + 1}: "
                            f"Expression injection risk: '${{{{ {expr} }}}}' in run block. "
                            f"Use an environment variable instead."
                        )

    def validate_file(self, file_path: Path) -> bool:
        """Validate a single workflow or action file."""
        try:
            display_path = file_path.relative_to(self.repo_root)
        except ValueError:
            # File is outside repo root
            display_path = file_path
        print(f"Validating: {display_path}")

        # Step 1: YAML syntax
        if not self.validate_yaml_syntax(file_path):
            return False

        # Step 2: Load and parse
        try:
            with open(file_path, encoding="utf-8") as f:
                content = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"{file_path}: Failed to parse: {e}")
            return False

        if not isinstance(content, dict):
            self.errors.append(f"{file_path}: Root element must be a dictionary")
            return False

        # Step 3: Structure validation
        if file_path.parent == self.workflows_dir:
            self.validate_workflow_structure(file_path, content)
            self.validate_workflow_size(file_path)
            self.validate_concurrency(file_path, content)
            self.validate_permissions(file_path, content)

        # Step 4: Action pinning (both workflows and actions)
        self.validate_action_pinning(file_path, content)

        # Step 5: Expression injection detection (security)
        self.validate_expression_injection(file_path, content)

        return len(self.errors) == 0

    def get_changed_workflows(self) -> list[Path]:
        """Get workflows/actions changed in current git working tree."""
        try:
            # Get uncommitted changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            changed_files = result.stdout.strip().split("\n")

            # Get untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip():
                changed_files.extend(result.stdout.strip().split("\n"))

            # Filter for workflow/action files
            workflow_files = []
            for file in changed_files:
                if not file:
                    continue
                file_path = self.repo_root / file
                if (
                    file.startswith(".github/workflows/") and file.endswith((".yml", ".yaml"))
                    or file.startswith(".github/actions/") and file.endswith("action.yml")
                ):
                    if file_path.exists():
                        workflow_files.append(file_path)

            return workflow_files
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to get changed files: {e}", file=sys.stderr)
            return []

    def run_act(self, workflow_path: Path) -> bool:
        """Run workflow with act (if installed)."""
        try:
            result = subprocess.run(
                ["act", "--list", "-W", str(workflow_path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                self.errors.append(
                    f"{workflow_path}: act validation failed:\n{result.stderr}"
                )
                return False
            return True
        except FileNotFoundError:
            self.warnings.append("act not found. Install from: https://github.com/nektos/act")
            return True  # Don't fail if act is not installed

    def print_results(self) -> None:
        """Print validation results."""
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  {warning}")

        if self.errors:
            print("\n❌ Errors:")
            for error in self.errors:
                print(f"  {error}")
            print(f"\nValidation failed with {len(self.errors)} error(s)")
        else:
            print("\n✅ All validations passed")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate GitHub Actions workflows")
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific workflow files to validate (default: all)"
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Only validate changed files in git working tree"
    )
    parser.add_argument(
        "--act",
        action="store_true",
        help="Run validation with act (if installed)"
    )
    args = parser.parse_args()

    # Find repo root
    repo_root = Path(__file__).parent.parent
    validator = WorkflowValidator(repo_root)

    # Determine which files to validate
    if args.changed:
        files = validator.get_changed_workflows()
        if not files:
            print("No workflow or action files changed")
            return 0
    elif args.files:
        files = [Path(f).resolve() for f in args.files]
    else:
        # Validate all workflows and actions
        files = list(validator.workflows_dir.glob("*.yml"))
        files.extend(list(validator.workflows_dir.glob("*.yaml")))
        files.extend(list(validator.actions_dir.glob("*/action.yml")))

    if not files:
        print("No workflow files found")
        return 0

    # Validate each file
    all_valid = True
    for file_path in files:
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            all_valid = False
            continue

        if not validator.validate_file(file_path):
            all_valid = False

        # Run act if requested
        if args.act and file_path.parent == validator.workflows_dir:
            if not validator.run_act(file_path):
                all_valid = False

    # Print results
    validator.print_results()

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
