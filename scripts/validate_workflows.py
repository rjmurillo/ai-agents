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


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of last-wins."""


def _no_duplicate_keys(
    loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in seen
        except TypeError:  # unhashable key; YAML permits it, GitHub does not use it
            continue
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        seen.add(key)
    mapping: dict[Any, Any] = loader.construct_mapping(node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


class WorkflowValidator:
    """Validates GitHub Actions workflow files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.workflows_dir = repo_root / ".github" / "workflows"
        self.actions_dir = repo_root / ".github" / "actions"
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """Validate YAML syntax, rejecting duplicate keys.

        ``yaml.safe_load`` silently keeps the last value for a duplicated key,
        so a workflow that defines ``jobs:`` twice loads clean here and then
        runs only half of itself. GitHub rejects it; the loader below makes this
        check agree with the service.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                # ADR-006 line 293 bans the module-level generic loader entry
                # point outright, SafeLoader subclass or not: the next edit that
                # drops the Loader argument silently reaches the unsafe default.
                # This is that function's body, with no such argument to lose.
                loader = _StrictLoader(f)
                try:
                    loader.get_single_data()
                finally:
                    loader.dispose()
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
        else:
            self._validate_jobs_are_runnable(file_path, content["jobs"])

    def _validate_jobs_are_runnable(self, file_path: Path, jobs: dict[str, Any]) -> None:
        """Every job must say where it runs, or call a reusable workflow.

        A job with neither is accepted by every YAML parser and rejected by
        GitHub at dispatch time, which turns a typo into a red run rather than
        a red check.
        """
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                self.errors.append(f"{file_path}: Job '{job_name}' must be a mapping")
                continue
            # Presence is not enough. A bare `runs-on:` parses as None and an
            # empty matrix label list parses as [], both of which GitHub
            # rejects at dispatch. Testing the value turns that into a red
            # check instead of a red run.
            if not job.get("runs-on") and not job.get("uses"):
                self.errors.append(
                    f"{file_path}: Job '{job_name}' has no 'runs-on' value and no 'uses' value"
                )

    def validate_action_pinning(self, file_path: Path, content: dict[str, Any]) -> None:
        """Validate that actions use SHA pinning (security requirement)."""
        jobs = content.get("jobs", {})
        # validate_workflow_structure already reports a non-mapping `jobs`.
        # Repeating the error here would double-count it, but iterating it
        # would raise and abort the pass over every remaining file, so the
        # wrong type is skipped and stays reported exactly once.
        if not isinstance(jobs, dict):
            return
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            # A job-level 'uses' calls a reusable workflow. It carries the same
            # supply-chain risk as a step-level action and was previously
            # unchecked, so an unpinned reusable workflow passed the gate.
            if "uses" in job:
                self._check_pinned(file_path, f"Job '{job_name}'", job["uses"])
            steps = job.get("steps", [])
            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                if "uses" in step:
                    self._check_pinned(
                        file_path, f"Job '{job_name}' step {step_idx + 1}", step["uses"]
                    )

    def _check_pinned(self, file_path: Path, where: str, uses: object) -> None:
        """Record an error unless ``uses`` is a local path or a 40-hex SHA.

        ``uses`` arrives straight from ``yaml.safe_load``, so its type is
        whatever the author typed. ``uses: 1.2`` is a float and a bare
        ``uses:`` is ``None``. Both used to raise ``AttributeError`` out of
        this method and abort the run, which turned a one-line workflow typo
        into a validator crash that reported nothing about the other files.
        A non-string is now its own error, so the pass keeps going and names
        every problem it found.
        """
        if not isinstance(uses, str):
            self.errors.append(
                f"{file_path}: {where}: 'uses' must be a string, "
                f"found {type(uses).__name__} ({uses!r})"
            )
            return

        # Skip local actions (start with ./)
        if uses.startswith("./"):
            return

        # Check for SHA pinning (format: owner/repo@sha # vX.Y.Z)
        if "@" not in uses:
            self.errors.append(f"{file_path}: {where}: Action '{uses}' is not pinned")
            return

        action_ref = uses.split("@")[1].split()[0]
        # SHA is 40 characters hex (case-insensitive)
        is_sha = len(action_ref) == 40
        is_hex = all(c in "0123456789abcdefABCDEF" for c in action_ref)
        if not (is_sha and is_hex):
            self.errors.append(
                f"{file_path}: {where}: Action '{uses}' must use SHA pinning (found: {action_ref})"
            )

    def validate_workflow_size(self, file_path: Path) -> None:
        """Validate workflow file size (ADR-006: thin orchestration)."""
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Filter out comments and empty lines for accurate count
        code_lines = [line for line in lines if line.strip() and not line.strip().startswith("#")]

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
                    self.warnings.append(f"{file_path}: Concurrency block missing 'group' field")
            elif not isinstance(concurrency, str):
                self.errors.append(f"{file_path}: Concurrency must be a string or dict")

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
                "permissions" in job for job in jobs.values() if isinstance(job, dict)
            )
            if not all_jobs_have_perms:
                self.errors.append(
                    f"{file_path}: Missing 'permissions' declaration. "
                    f"Set top-level or per-job permissions to follow least-privilege."
                )

    # Expression heads that cannot carry attacker-supplied free text.
    #
    # This is an allowlist, not a blocklist. The previous shape enumerated
    # dangerous contexts, which meant every context nobody had thought of
    # yet defaulted to "safe". `inputs.*` from `workflow_dispatch` was one
    # such gap and produced a live command-injection hole in two workflows
    # (issue #3664). Unknown now defaults to "unsafe".
    #
    # Each entry is admitted for a stated reason:
    #   github.event_name        GitHub-generated enum of event names.
    #   github.job               Job id from the workflow file itself.
    #   github.run_*             Integers GitHub assigns.
    #   github.repository*       Slug; GitHub constrains the charset.
    #   github.actor*, triggering_actor   Login; GitHub constrains the charset.
    #   github.sha, *_url, workspace, action_path, api_url, graphql_url
    #                            GitHub-generated, not user text.
    #   github.event.*.number    Integers GitHub assigns.
    #   github.workflow_ref, github.repository_id, github.repository_owner_id
    #                            GitHub-generated identifiers.
    #
    # Deliberately absent: github.ref, github.ref_name, github.head_ref, and
    # github.base_ref all carry a branch name, which a fork author chooses.
    # secrets.* is absent because a secret in a `run:` block is a separate
    # exposure question, not a safe default.
    _SAFE_EXPRESSION_HEADS: frozenset[str] = frozenset(
        {
            "github.event_name",
            "github.job",
            "github.run_id",
            "github.run_number",
            "github.run_attempt",
            "github.repository",
            "github.repository_id",
            "github.repository_owner",
            "github.repository_owner_id",
            "github.actor",
            "github.actor_id",
            "github.triggering_actor",
            "github.sha",
            "github.server_url",
            "github.api_url",
            "github.graphql_url",
            "github.workspace",
            "github.action_path",
            "github.workflow",
            "github.workflow_ref",
            "github.event.number",
            "github.event.issue.number",
            "github.event.pull_request.number",
            "github.event.discussion.number",
        }
    )

    # Prefixes whose safety depends on what produced the value, so they are
    # resolved by the taint pass in `validate_expression_injection` rather
    # than by the head allowlist above.
    #
    # `secrets.` sits here because a secret is not attacker-supplied: the
    # threat this check models is an outsider steering the shell, and an
    # outsider who can already set a secret has write access and does not
    # need an injection. Leaking a secret into a log is a real but separate
    # concern with its own gate.
    _DERIVED_EXPRESSION_PREFIXES: tuple[str, ...] = (
        "needs.",
        "matrix.",
        "env.",
        "vars.",
        "secrets.",
        "runner.",
        "strategy.",
        "job.",
    )

    # Every context reference inside an expression, regardless of how many
    # function calls or operators wrap it. Working from the references
    # rather than from the leading token means `hashFiles('**/lock')` is
    # safe (it names no context) while `fromJSON(inputs.blob)` is not (the
    # argument still reaches the shell).
    _CONTEXT_REFERENCE: re.Pattern[str] = re.compile(
        r"\b(?:github|inputs|steps|needs|matrix|env|vars|secrets|runner|strategy|job)"
        r"(?:\.[A-Za-z0-9_-]+|\[[^\]]*\])*"
    )

    def _classify_expression(self, expression: str, tainted_steps: set[str]) -> str | None:
        """Return a reason string when the expression is unsafe in a run block.

        Returns None when every context the expression names resolves to a
        value GitHub generates, or to a step output no attacker-controlled
        input reached.
        """
        for match in self._CONTEXT_REFERENCE.finditer(expression):
            # `a[0].b` and `a.0.b` name the same thing to GitHub. Normalizing
            # the index syntax keeps one spelling from slipping past a check
            # written against the other.
            reference = re.sub(r"\[['\"]?([^\]'\"]*)['\"]?\]", r".\1", match.group(0))
            if reference in self._SAFE_EXPRESSION_HEADS:
                continue
            if reference.startswith("steps."):
                parts = reference.split(".")
                producer = parts[1] if len(parts) > 1 else ""
                if producer in tainted_steps:
                    return (
                        f"'{producer}' derives its output from attacker-controlled "
                        f"input, so this value carries the same taint"
                    )
                continue
            if reference.startswith(self._DERIVED_EXPRESSION_PREFIXES):
                continue
            return f"'{reference}' is not a GitHub-generated value"
        return None

    def validate_expression_injection(self, file_path: Path, content: dict[str, Any]) -> None:
        """Detect expression injection in run blocks.

        Flags any ``${{ }}`` interpolated straight into a ``run:`` block
        unless the expression resolves to a value GitHub generates. Taint
        propagates one hop: a step that reads an unsafe expression and
        writes to ``$GITHUB_OUTPUT`` marks its own outputs unsafe for every
        later step in the same job, because binding the value through
        ``env:`` at the producer stops the injection there but does not
        sanitize what the producer publishes.
        """
        jobs = content.get("jobs", {})
        # validate_workflow_structure already reports a non-mapping `jobs`.
        # Repeating the error here would double-count it, but iterating it
        # would raise and abort the pass over every remaining file, so the
        # wrong type is skipped and stays reported exactly once.
        if not isinstance(jobs, dict):
            return
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            self._check_job_expressions(file_path, job_name, job)

    def _check_job_expressions(self, file_path: Path, job_name: str, job: dict[str, Any]) -> None:
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            return
        tainted_steps: set[str] = set()
        for step_idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            run_block = step.get("run")
            step_env = step.get("env") if isinstance(step.get("env"), dict) else {}
            reads_unsafe = False

            if isinstance(run_block, str):
                for match in re.finditer(r"\$\{\{(.+?)\}\}", run_block):
                    expr = match.group(1).strip()
                    reason = self._classify_expression(expr, tainted_steps)
                    if reason is None:
                        continue
                    reads_unsafe = True
                    self.errors.append(
                        f"{file_path}: Job '{job_name}' step {step_idx + 1}: "
                        f"Expression injection risk: '${{{{ {expr} }}}}' in run block "
                        f"({reason}). Bind it through the step's 'env:' and "
                        f"reference the quoted shell variable instead."
                    )

            for env_value in step_env.values():
                if not isinstance(env_value, str):
                    continue
                for match in re.finditer(r"\$\{\{(.+?)\}\}", env_value):
                    if self._classify_expression(match.group(1).strip(), tainted_steps):
                        reads_unsafe = True

            step_id = step.get("id")
            if (
                reads_unsafe
                and isinstance(step_id, str)
                and isinstance(run_block, str)
                and "GITHUB_OUTPUT" in run_block
            ):
                tainted_steps.add(step_id)

    # A plain (unquoted) YAML scalar ends at an unescaped ` #`, which starts a
    # comment. GitHub renders the truncated remainder as the step name and
    # reports nothing, so a name carrying an issue reference silently loses
    # everything from the `#` onward (issue #3652).
    _UNQUOTED_HASH_SCALAR: re.Pattern[str] = re.compile(
        r"^\s*-?\s*(name|description):\s+(?![\"'|>&*])(?P<value>\S.*\s#.*)$"
    )

    def validate_name_truncation(self, file_path: Path) -> None:
        """Flag plain scalars whose value is cut short by an inline comment.

        Operates on raw text. By the time the YAML loader has run, the
        truncation has already happened and left no trace to compare
        against.
        """
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - surfaced by the caller
            self.errors.append(f"{file_path}: Failed to read: {exc}")
            return
        for line_no, line in enumerate(raw.splitlines(), 1):
            match = self._UNQUOTED_HASH_SCALAR.match(line)
            if not match:
                continue
            value = match.group("value").rstrip()
            kept, _, dropped = value.partition(" #")
            self.errors.append(
                f"{file_path}:{line_no}: Unquoted '#' truncates this "
                f"{match.group(1)} at the YAML comment marker. GitHub sees "
                f"'{kept.rstrip()}' and drops '#{dropped}'. Wrap the value in "
                f'double quotes: {match.group(1)}: "{value}"'
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

        # Step 6: Silent name truncation at an unquoted comment marker
        self.validate_name_truncation(file_path)

        return len(self.errors) == 0

    def get_changed_workflows(self) -> list[Path]:
        """Get workflows/actions changed in current git working tree."""
        try:
            # Get uncommitted changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            changed_files = result.stdout.strip().split("\n")

            # Get untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
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
                    file.startswith(".github/workflows/")
                    and file.endswith((".yml", ".yaml"))
                    or file.startswith(".github/actions/")
                    and file.endswith("action.yml")
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
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                self.errors.append(f"{workflow_path}: act validation failed:\n{result.stderr}")
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
        "files", nargs="*", help="Specific workflow files to validate (default: all)"
    )
    parser.add_argument(
        "--changed", action="store_true", help="Only validate changed files in git working tree"
    )
    parser.add_argument("--act", action="store_true", help="Run validation with act (if installed)")
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
