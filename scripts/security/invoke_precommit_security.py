#!/usr/bin/env python3
"""
Pre-commit Security Check Script

Runs security validation on staged PowerShell files before commit.
Integrates PSScriptAnalyzer for static analysis and generates security reports.

Usage:
    python invoke_precommit_security.py
    python invoke_precommit_security.py --dry-run
    python invoke_precommit_security.py --skip-agent-review

Per ADR-042: Python-first for new scripts.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class SecurityFinding:
    """Represents a security finding from static analysis."""

    rule_name: str
    severity: str
    message: str
    file_path: str
    line_number: int
    cwe_id: str | None = None
    source: str = "psscriptanalyzer"  # psscriptanalyzer | codeql


@dataclass
class CodeQLAlert:
    """Represents a CodeQL alert from GitHub API."""

    number: int
    rule_id: str
    severity: str
    security_severity_level: str | None
    description: str
    state: str
    html_url: str
    location_path: str
    location_line: int
    cwe_ids: list[str]


@dataclass
class PreCommitResult:
    """Result of pre-commit security check."""

    passed: bool
    findings: list[SecurityFinding]
    report_path: Path | None
    error_message: str | None = None
    codeql_alerts: list[CodeQLAlert] | None = None


class PreCommitSecurityCheck:
    """Orchestrates pre-commit security validation."""

    # Critical file patterns that require enhanced review
    CRITICAL_PATTERNS = [
        r".*[/\\]Auth[/\\].*",
        r".*[/\\]Security[/\\].*",
        r".*\.env.*",
        r".*[/\\]\.githooks[/\\].*",
        r".*[/\\]secrets[/\\].*",
        r".*[Pp]assword.*",
        r".*[Tt]oken.*",
        r".*[/\\]oauth[/\\].*",
        r".*[/\\]jwt[/\\].*",
        r".*[Cc]redential.*",
    ]

    # PSScriptAnalyzer rule severity mapping
    SEVERITY_MAP = {
        "Error": "CRITICAL",
        "Warning": "HIGH",
        "Information": "MEDIUM",
        "Suggestion": "LOW",
    }

    def __init__(
        self,
        dry_run: bool = False,
        skip_agent_review: bool = False,
        verbose: bool = False,
        skip_codeql: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.skip_agent_review = skip_agent_review
        self.verbose = verbose
        self.skip_codeql = skip_codeql
        self.repo_root = self._find_repo_root()
        self.findings: list[SecurityFinding] = []
        self.codeql_alerts: list[CodeQLAlert] = []

    def _find_repo_root(self) -> Path:
        """Find the git repository root."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def _get_github_context(self) -> tuple[str, str, str] | None:
        """Get GitHub owner, repo, and branch from git remote and current branch.

        Returns:
            Tuple of (owner, repo, branch) or None if not in GitHub context.
        """
        try:
            # Get remote URL
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
            )

            if remote_result.returncode != 0:
                return None

            remote_url = remote_result.stdout.strip()

            # Parse owner/repo from URL
            # Supports: git@github.com:owner/repo.git or https://github.com/owner/repo.git
            match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
            if not match:
                return None

            owner, repo = match.groups()

            # Get current branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,  # Don't raise, check returncode explicitly
            )

            if branch_result.returncode != 0:
                logger.error(
                    "Failed to get current branch: %s",
                    branch_result.stderr.strip(),
                )
                return None

            branch = branch_result.stdout.strip()

            if not branch:
                logger.error("Empty branch name returned from git")
                return None

            return owner, repo, branch

        except subprocess.SubprocessError as e:
            logger.error("Git command failed during context retrieval: %s", e)
            return None

    def _fetch_codeql_alerts(self) -> list[CodeQLAlert]:
        """Fetch CodeQL alerts from GitHub API for current branch.

        Uses gh CLI to fetch code scanning alerts. Filters to open alerts on current ref.
        """
        context = self._get_github_context()
        if not context:
            logger.debug("Not in GitHub context, skipping CodeQL alert fetch")
            return []

        owner, repo, branch = context

        try:
            # Check if gh CLI is available
            gh_check = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if gh_check.returncode != 0:
                logger.debug("gh CLI not available, skipping CodeQL alert fetch")
                return []

            # Fetch code scanning alerts for the branch
            # API: GET /repos/{owner}/{repo}/code-scanning/alerts
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{owner}/{repo}/code-scanning/alerts",
                    "--jq",
                    f"""[.[] | select(.state == "open" and .ref == "refs/heads/{branch}") | {{
                        number: .number,
                        rule_id: .rule.id,
                        severity: .rule.severity,
                        security_severity_level: .rule.security_severity_level,
                        description: .rule.description,
                        state: .state,
                        html_url: .html_url,
                        location_path: .most_recent_instance.location.path,
                        location_line: .most_recent_instance.location.start_line,
                        cwe_ids: [.rule.tags[] | select(startswith("cwe-"))]
                    }}]""",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                # API might return 404 if code scanning not enabled
                if "404" in result.stderr or "Not Found" in result.stderr:
                    logger.info("CodeQL code scanning not enabled for this repository")
                else:
                    logger.warning(
                        "Failed to fetch CodeQL alerts: %s",
                        result.stderr[:200] if result.stderr else "Unknown error",
                    )
                return []

            if not result.stdout.strip() or result.stdout.strip() == "[]":
                logger.info("No open CodeQL alerts for branch: %s", branch)
                return []

            import json

            try:
                alerts_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse CodeQL alerts JSON: %s. This indicates a gh CLI or API issue.",
                    e,
                )
                raise  # Fail hard on JSON decode errors

            alerts = []
            for alert in alerts_data:
                alerts.append(
                    CodeQLAlert(
                        number=alert.get("number", 0),
                        rule_id=alert.get("rule_id", "unknown"),
                        severity=alert.get("severity", "unknown"),
                        security_severity_level=alert.get("security_severity_level"),
                        description=alert.get("description", ""),
                        state=alert.get("state", "open"),
                        html_url=alert.get("html_url", ""),
                        location_path=alert.get("location_path", ""),
                        location_line=alert.get("location_line", 0),
                        cwe_ids=alert.get("cwe_ids", []),
                    )
                )

            logger.info("Fetched %d CodeQL alert(s) for branch: %s", len(alerts), branch)
            return alerts

        except subprocess.SubprocessError as e:
            logger.warning("Failed to fetch CodeQL alerts: %s", e)
            return []

    def run(self) -> int:
        """Execute the pre-commit security check workflow.

        Returns:
            Exit code: 0 for pass, 1 for fail
        """
        logger.info("Starting pre-commit security check")

        if self.dry_run:
            logger.info("[DRY RUN] No actual blocking will occur")

        # Step 0: Fetch CodeQL alerts (if in PR context)
        if not self.skip_codeql:
            self.codeql_alerts = self._fetch_codeql_alerts()
            if self.codeql_alerts:
                logger.info(
                    "[INFO] Found %d open CodeQL alert(s) for review",
                    len(self.codeql_alerts),
                )
                for alert in self.codeql_alerts:
                    cwe_str = ", ".join(alert.cwe_ids) if alert.cwe_ids else "N/A"
                    logger.info(
                        "  - %s:%d [%s] %s (CWE: %s)",
                        alert.location_path,
                        alert.location_line,
                        alert.security_severity_level or alert.severity,
                        alert.rule_id,
                        cwe_str,
                    )

        # Step 1: Get staged PowerShell files
        staged_files = self._get_staged_powershell_files()

        if not staged_files:
            logger.info("[PASS] No PowerShell files staged for commit")
            return 0

        logger.info("Found %d staged PowerShell file(s):", len(staged_files))
        for f in staged_files:
            logger.info("  - %s", f)

        # Step 2: Check for critical file patterns
        critical_files = self._check_critical_patterns(staged_files)
        if critical_files:
            logger.warning(
                "[WARNING] Critical file patterns detected in %d file(s):",
                len(critical_files),
            )
            for f in critical_files:
                logger.warning("  - %s", f)

        # Step 3: Ensure PSScriptAnalyzer is available
        if not self._ensure_psscriptanalyzer():
            logger.error(
                "[FAIL] PSScriptAnalyzer not available. Install with:\n"
                "  Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser"
            )
            return 1

        # Step 4: Run PSScriptAnalyzer on staged files
        analyzer_result = self._run_psscriptanalyzer(staged_files)
        if not analyzer_result.passed:
            logger.error(
                "[FAIL] PSScriptAnalyzer found %d issue(s)",
                len(analyzer_result.findings),
            )
            for finding in analyzer_result.findings:
                logger.error(
                    "  %s:%d [%s] %s",
                    finding.file_path,
                    finding.line_number,
                    finding.severity,
                    finding.message,
                )

            if not self.dry_run:
                return 1

        # Step 5: Generate security report
        report_path = self._generate_security_report(staged_files, critical_files)

        if report_path:
            logger.info("Generated security report: %s", report_path)

            # Step 6: Stage the security report
            if not self.dry_run:
                self._stage_security_report(report_path)

        # Step 7: Verify security report exists
        if not self._verify_security_report(report_path):
            if not self.dry_run:
                logger.error(
                    "[FAIL] Security report missing or empty. "
                    "Run pre-commit hook to generate SR-*.md"
                )
                return 1

        logger.info("[PASS] Pre-commit security check completed")
        return 0

    def _get_staged_powershell_files(self) -> list[Path]:
        """Get list of staged PowerShell files."""
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True,
                text=True,
                check=True,
            )

            files = result.stdout.strip().split("\n") if result.stdout.strip() else []

            # Filter for PowerShell files
            ps_files = [
                self.repo_root / f
                for f in files
                if f.endswith((".ps1", ".psm1", ".psd1"))
            ]

            return ps_files

        except subprocess.SubprocessError as e:
            logger.error("[FAIL] Failed to get staged files: %s", e)
            return []

    def _check_critical_patterns(self, files: list[Path]) -> list[Path]:
        """Check if any staged files match critical security patterns."""
        critical_files = []

        for file_path in files:
            relative_path = str(file_path.relative_to(self.repo_root))
            for pattern in self.CRITICAL_PATTERNS:
                if re.match(pattern, relative_path, re.IGNORECASE):
                    critical_files.append(file_path)
                    break

        return critical_files

    def _ensure_psscriptanalyzer(self) -> bool:
        """Ensure PSScriptAnalyzer is installed."""
        try:
            result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    "Get-Module -ListAvailable PSScriptAnalyzer | Select-Object -First 1",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if "PSScriptAnalyzer" in result.stdout:
                return True

            # Try to install
            logger.info("Installing PSScriptAnalyzer...")
            install_result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    "Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser -AllowClobber",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            return install_result.returncode == 0

        except FileNotFoundError:
            logger.error("[FAIL] PowerShell (pwsh) not found in PATH")
            return False

    def _run_psscriptanalyzer(self, files: list[Path]) -> PreCommitResult:
        """Run PSScriptAnalyzer on the specified files."""
        findings = []
        failed_files = []

        for file_path in files:
            try:
                # Run PSScriptAnalyzer with JSON output
                result = subprocess.run(
                    [
                        "pwsh",
                        "-NoProfile",
                        "-Command",
                        f"""
                        $findings = Invoke-ScriptAnalyzer -Path '{file_path}' -Severity Error,Warning
                        $findings | ConvertTo-Json -Depth 3
                        """,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0 and result.stderr:
                    logger.warning(
                        "PSScriptAnalyzer warning for %s: %s",
                        file_path.name,
                        result.stderr[:200],
                    )
                    continue

                if not result.stdout.strip() or result.stdout.strip() == "null":
                    continue

                # Parse JSON output
                import json

                try:
                    analyzer_findings = json.loads(result.stdout)

                    # Handle single finding (not wrapped in array)
                    if isinstance(analyzer_findings, dict):
                        analyzer_findings = [analyzer_findings]

                    for finding in analyzer_findings:
                        severity = self.SEVERITY_MAP.get(
                            finding.get("Severity", "Information"), "MEDIUM"
                        )
                        findings.append(
                            SecurityFinding(
                                rule_name=finding.get("RuleName", "Unknown"),
                                severity=severity,
                                message=finding.get("Message", "No message"),
                                file_path=str(file_path.relative_to(self.repo_root)),
                                line_number=finding.get("Line", 0),
                                cwe_id=self._map_rule_to_cwe(
                                    finding.get("RuleName", "")
                                ),
                            )
                        )

                except json.JSONDecodeError as e:
                    # PSScriptAnalyzer should always output valid JSON or nothing
                    # If we get invalid JSON, something is wrong with the tool
                    logger.error(
                        "[FAIL] PSScriptAnalyzer returned invalid JSON for %s: %s",
                        file_path.name,
                        e,
                    )
                    failed_files.append(str(file_path))

            except subprocess.SubprocessError as e:
                logger.error(
                    "[FAIL] PSScriptAnalyzer failed for %s: %s",
                    file_path.name,
                    e,
                )
                failed_files.append(str(file_path))

        # Check if any files failed analysis
        if failed_files and not self.dry_run:
            error_msg = (
                f"PSScriptAnalyzer failed for {len(failed_files)} file(s): "
                f"{', '.join(failed_files[:5])}"  # Show first 5 to avoid long messages
            )
            if len(failed_files) > 5:
                error_msg += f" (and {len(failed_files) - 5} more)"
            logger.error(error_msg)
            return PreCommitResult(
                passed=False,
                findings=findings,
                report_path=None,
                error_message=error_msg,
            )

        self.findings.extend(findings)

        # Check for blocking findings (CRITICAL or HIGH)
        blocking_findings = [
            f for f in findings if f.severity in ("CRITICAL", "HIGH")
        ]

        return PreCommitResult(
            passed=len(blocking_findings) == 0,
            findings=findings,
            report_path=None,
        )

    def _map_rule_to_cwe(self, rule_name: str) -> str | None:
        """Map PSScriptAnalyzer rule to CWE ID.

        TRACKING: CWE Mapping Review Required (Issue #756)
        - This mapping is preliminary and requires security review for accuracy
        - PSScriptAnalyzer rules may map to multiple CWEs depending on context
        - Some mappings are approximate and should be validated against CWE definitions
        - Consider: CWE-94 (Invoke-Expression) may also be CWE-77 (Command Injection)
        - Consider: CWE-20 (Input Validation) is broad and may need more specific CWEs
        - TODO: Review with security team and update based on actual vulnerability patterns
        """
        rule_cwe_map = {
            "PSAvoidUsingInvokeExpression": "CWE-94",  # Code Injection
            "PSAvoidUsingPlainTextForPassword": "CWE-798",  # Hardcoded Credentials
            "PSAvoidUsingConvertToSecureStringWithPlainText": "CWE-798",  # Hardcoded Credentials
            "PSAvoidUsingUserNameAndPassWordParams": "CWE-798",  # Hardcoded Credentials
            "PSUseShouldProcessForStateChangingFunctions": "CWE-20",  # Improper Input Validation
            "PSAvoidGlobalVars": "CWE-749",  # Exposed Dangerous Method or Function
            "PSAvoidUsingPositionalParameters": "CWE-20",  # Improper Input Validation
        }
        return rule_cwe_map.get(rule_name)

    def _generate_security_report(
        self,
        staged_files: list[Path],
        critical_files: list[Path],
    ) -> Path | None:
        """Generate a security report for the staged changes."""
        if self.dry_run:
            logger.info("[DRY RUN] Would generate security report")
            return None

        # Get current branch name
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip().replace("/", "-")
        except subprocess.SubprocessError:
            branch = "unknown"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_name = f"SR-{branch}-{timestamp}.md"
        report_path = self.repo_root / ".agents" / "security" / report_name

        # Count findings by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for finding in self.findings:
            severity_counts[finding.severity] = (
                severity_counts.get(finding.severity, 0) + 1
            )

        content = f"""# Security Report: {branch}

> **Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> **Type**: Pre-commit validation
> **Tool**: invoke_precommit_security.py

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | {severity_counts['CRITICAL']} |
| HIGH | {severity_counts['HIGH']} |
| MEDIUM | {severity_counts['MEDIUM']} |
| LOW | {severity_counts['LOW']} |

## Files Reviewed

| File | Status |
|------|--------|
"""

        for f in staged_files:
            status = "[CRITICAL FILE]" if f in critical_files else "[PASS]"
            content += f"| `{f.relative_to(self.repo_root)}` | {status} |\n"

        # CodeQL Findings Section
        content += "\n## CodeQL Findings\n\n"
        content += (
            "> **Division of Labor**: CodeQL detects vulnerabilities automatically. "
            "Security agent interprets findings in project context and recommends mitigations.\n\n"
        )

        if self.codeql_alerts:
            content += "| Alert | Severity | CWE | Location | Description |\n"
            content += "|-------|----------|-----|----------|-------------|\n"
            for alert in self.codeql_alerts:
                cwe_str = ", ".join(alert.cwe_ids) if alert.cwe_ids else "N/A"
                severity = alert.security_severity_level or alert.severity
                desc_short = (
                    alert.description[:50] + "..."
                    if len(alert.description) > 50
                    else alert.description
                )
                content += (
                    f"| [{alert.rule_id}]({alert.html_url}) | {severity} | {cwe_str} "
                    f"| `{alert.location_path}:{alert.location_line}` | {desc_short} |\n"
                )
            content += "\n"
            content += "**Agent Action Required**: Review each CodeQL finding above in the context of:\n"
            content += "- Business impact and data sensitivity\n"
            content += "- Deployment context (CLI tool vs API service)\n"
            content += "- Existing mitigations or compensating controls\n\n"
        else:
            content += "No open CodeQL alerts for this branch.\n\n"

        # PSScriptAnalyzer Findings Section
        content += "## PSScriptAnalyzer Findings\n\n"

        if self.findings:
            for i, finding in enumerate(self.findings, 1):
                cwe_ref = f" ({finding.cwe_id})" if finding.cwe_id else ""
                content += f"""### {finding.severity}-{i:03d}: {finding.rule_name}{cwe_ref}

- **Location**: `{finding.file_path}:{finding.line_number}`
- **Severity**: {finding.severity}
- **Message**: {finding.message}

"""
        else:
            content += "No security findings from PSScriptAnalyzer.\n\n"

        # Determine CodeQL status
        codeql_critical = sum(
            1
            for a in self.codeql_alerts
            if a.security_severity_level in ("critical", "high")
        )
        codeql_status = (
            "SKIPPED"
            if self.skip_codeql
            else ("REVIEW REQUIRED" if codeql_critical > 0 else "PASS")
        )

        content += f"""## Validation Status

- **CodeQL**: {codeql_status} ({len(self.codeql_alerts)} open alert(s), {codeql_critical} critical/high)
- **PSScriptAnalyzer**: {'PASS' if severity_counts['CRITICAL'] == 0 and severity_counts['HIGH'] == 0 else 'FAIL'}
- **Critical File Review**: {'REQUIRED' if critical_files else 'NOT REQUIRED'}
- **Agent Review**: {'SKIPPED' if self.skip_agent_review else 'PENDING'}

## Next Steps

"""

        if severity_counts["CRITICAL"] > 0 or severity_counts["HIGH"] > 0:
            content += "1. Fix CRITICAL/HIGH findings before commit\n"
            content += "2. Re-run pre-commit check\n"
        elif critical_files:
            content += "1. Critical file patterns detected - enhanced review recommended\n"
            content += "2. Consider running full security agent review\n"
        else:
            content += "1. No blocking issues found\n"
            content += "2. Commit can proceed\n"

        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(content, encoding="utf-8")
            return report_path
        except OSError as e:
            logger.error("[FAIL] Failed to write security report: %s", e)
            return None

    def _stage_security_report(self, report_path: Path) -> bool:
        """Stage the security report for commit."""
        try:
            subprocess.run(
                ["git", "add", str(report_path)],
                check=True,
                capture_output=True,
            )
            logger.info("Staged security report: %s", report_path.name)
            return True
        except subprocess.SubprocessError as e:
            logger.warning("Failed to stage security report: %s", e)
            return False

    def _verify_security_report(self, report_path: Path | None) -> bool:
        """Verify that a security report exists and is non-empty."""
        if report_path is None:
            return self.dry_run  # OK in dry run mode

        if not report_path.exists():
            return False

        return report_path.stat().st_size > 100


def main() -> int:
    """Entry point for the pre-commit security check script."""
    parser = argparse.ArgumentParser(
        description="Run security validation on staged PowerShell files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python invoke_precommit_security.py
    python invoke_precommit_security.py --dry-run
    python invoke_precommit_security.py --skip-agent-review
    python invoke_precommit_security.py --skip-codeql

Exit Codes:
    0: Pass (no blocking issues)
    1: Fail (CRITICAL/HIGH findings or missing report)
        """,
    )

    parser.add_argument(
        "--dry-run",
        "--whatif",
        action="store_true",
        help="Simulate all operations without blocking commit",
    )

    parser.add_argument(
        "--skip-agent-review",
        action="store_true",
        help="Skip security agent review (PSScriptAnalyzer only)",
    )

    parser.add_argument(
        "--skip-codeql",
        action="store_true",
        help="Skip CodeQL alert fetching from GitHub API",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    check = PreCommitSecurityCheck(
        dry_run=args.dry_run,
        skip_agent_review=args.skip_agent_review,
        skip_codeql=args.skip_codeql,
        verbose=args.verbose,
    )

    return check.run()


if __name__ == "__main__":
    sys.exit(main())
