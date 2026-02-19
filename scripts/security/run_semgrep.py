#!/usr/bin/env python3
"""
Semgrep Security Scanner for Local Pre-Push Validation

Runs semgrep security rules on Python, PowerShell, JavaScript, and YAML files.
Blocks push on HIGH/CRITICAL findings. Integrates with pre-push hook.

Usage:
    python3 scripts/security/run_semgrep.py
    python3 scripts/security/run_semgrep.py --config auto  # Use semgrep registry rules
    python3 scripts/security/run_semgrep.py --severity high  # Only high/critical
    python3 scripts/security/run_semgrep.py --dry-run  # Show findings without blocking

Exit Codes:
    0: Pass (no blocking findings)
    1: Fail (HIGH/CRITICAL findings or errors)
    2: Configuration error

Per ADR-042: Python-first for new scripts.
Per issue #939: Recommended semgrep over CodeQL for faster local feedback (<1 minute).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SemgrepFinding:
    """Represents a semgrep security finding."""

    check_id: str
    path: str
    line: int
    severity: str
    message: str
    cwe: list[str]
    owasp: list[str]


class SemgrepScanner:
    """Orchestrates semgrep security scanning."""

    SUPPORTED_EXTENSIONS = {
        ".py",
        ".ps1",
        ".psm1",
        ".js",
        ".ts",
        ".yaml",
        ".yml",
    }

    SEVERITY_PRIORITY = {
        "ERROR": 1,
        "WARNING": 2,
        "INFO": 3,
    }

    def __init__(
        self,
        dry_run: bool = False,
        config: str = "auto",
        severity: str | None = None,
        verbose: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.config = config
        self.severity = severity
        self.verbose = verbose
        self.repo_root = self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find the git repository root."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def _check_semgrep_installed(self) -> bool:
        """Check if semgrep is installed and accessible."""
        try:
            result = subprocess.run(
                ["semgrep", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _get_changed_files(self) -> list[Path]:
        """Get files changed in the current branch vs main."""
        try:
            merge_base_result = subprocess.run(
                ["git", "merge-base", "origin/main", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )

            if merge_base_result.returncode != 0:
                logger.warning("Could not find merge-base with origin/main, scanning all files")
                result = subprocess.run(
                    ["git", "ls-files"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            else:
                merge_base = merge_base_result.stdout.strip()
                result = subprocess.run(
                    ["git", "diff", "--name-only", f"{merge_base}...HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )

            files = result.stdout.strip().split("\n") if result.stdout.strip() else []

            filtered = [
                self.repo_root / f
                for f in files
                if Path(f).suffix in self.SUPPORTED_EXTENSIONS and Path(f).exists()
            ]

            return filtered

        except subprocess.SubprocessError as e:
            logger.error("Failed to get changed files: %s", e)
            return []

    def _run_semgrep(self, files: list[Path]) -> list[SemgrepFinding]:
        """Run semgrep on the specified files."""
        if not files:
            return []

        cmd = [
            "semgrep",
            "scan",
            "--config",
            self.config,
            "--json",
            "--no-git-ignore",
        ]

        if self.severity:
            cmd.extend(["--severity", self.severity])

        for f in files:
            cmd.append(str(f))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                check=False,
            )

            if result.returncode not in (0, 1):
                logger.error("Semgrep execution error: %s", result.stderr)
                return []

            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            findings = []

            for finding in data.get("results", []):
                extra = finding.get("extra", {})
                metadata = extra.get("metadata", {})

                cwe = metadata.get("cwe", [])
                if isinstance(cwe, str):
                    cwe = [cwe]

                owasp = metadata.get("owasp", [])
                if isinstance(owasp, str):
                    owasp = [owasp]

                findings.append(
                    SemgrepFinding(
                        check_id=finding.get("check_id", "unknown"),
                        path=finding.get("path", ""),
                        line=finding.get("start", {}).get("line", 0),
                        severity=extra.get("severity", "INFO"),
                        message=extra.get("message", ""),
                        cwe=cwe,
                        owasp=owasp,
                    )
                )

            return findings

        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            logger.error("Semgrep scan failed: %s", e)
            return []

    def run(self) -> int:
        """Execute the semgrep scan workflow."""
        if not self._check_semgrep_installed():
            logger.error("ERROR: semgrep not installed")
            logger.error("")
            logger.error("Install with:")
            logger.error("  pip install semgrep")
            logger.error("  OR")
            logger.error("  python3 scripts/Install-Semgrep.py")
            return 2

        logger.info("Semgrep security scan starting")

        if self.dry_run:
            logger.info("[DRY RUN] No blocking will occur")

        changed_files = self._get_changed_files()

        if not changed_files:
            logger.info("PASS: No files to scan")
            return 0

        logger.info("Scanning %d file(s)", len(changed_files))

        findings = self._run_semgrep(changed_files)

        if not findings:
            logger.info("PASS: No security findings")
            return 0

        blocking_findings = [f for f in findings if f.severity == "ERROR"]
        warning_findings = [f for f in findings if f.severity == "WARNING"]
        info_findings = [f for f in findings if f.severity == "INFO"]

        if blocking_findings:
            logger.error("")
            logger.error("FAIL: Found %d HIGH/CRITICAL finding(s)", len(blocking_findings))
            logger.error("")
            for f in sorted(blocking_findings, key=lambda x: (x.path, x.line)):
                cwe_str = f"CWE-{','.join(f.cwe)}" if f.cwe else "N/A"
                logger.error(
                    "  %s:%d [%s] %s (%s)",
                    f.path,
                    f.line,
                    f.severity,
                    f.check_id,
                    cwe_str,
                )
                logger.error("    %s", f.message)

        if warning_findings:
            logger.warning("")
            logger.warning("WARNING: Found %d medium finding(s)", len(warning_findings))
            for f in sorted(warning_findings, key=lambda x: (x.path, x.line))[:5]:
                logger.warning("  %s:%d %s", f.path, f.line, f.check_id)

        if info_findings and self.verbose:
            logger.info("")
            logger.info("INFO: Found %d low finding(s)", len(info_findings))

        if blocking_findings and not self.dry_run:
            logger.error("")
            logger.error("Fix HIGH/CRITICAL findings before pushing")
            return 1

        return 0


def main() -> int:
    """Entry point for semgrep security scanner."""
    parser = argparse.ArgumentParser(
        description="Run semgrep security scan on changed files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        default="auto",
        help="Semgrep config (auto, p/security-audit, p/owasp-top-ten)",
    )

    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        help="Minimum severity to report",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show findings without blocking",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all findings including INFO",
    )

    args = parser.parse_args()

    scanner = SemgrepScanner(
        dry_run=args.dry_run,
        config=args.config,
        severity=args.severity,
        verbose=args.verbose,
    )

    return scanner.run()


if __name__ == "__main__":
    sys.exit(main())
