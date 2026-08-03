#!/usr/bin/env python3
# taste-lint: ignore file-size
# run_semgrep.py is a single-responsibility scanner; splitting it would scatter
# the scan orchestration across files. The file grew past 500 lines when pinned
# resolution helpers were added in issue #4190. File size is monitored but
# splitting is not warranted until the scan logic itself becomes multi-concern.
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
    3: External tool failure (semgrep timed out before completing)

Per ADR-042: Python-first for new scripts.
Per issue #939: Recommended semgrep over CodeQL for faster local feedback (<1 minute).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.github_core.repo import get_repo_root

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

SEMGREP_OUTPUT_SNIPPET_CHARS = 500


class SemgrepScanError(Exception):
    """Raised when the semgrep scan cannot complete (e.g. timeout).

    Signals a fail-closed condition: unlike a clean empty-findings return, this
    means the scan did not run to completion and its result must not be treated
    as "no findings". ``run()`` maps it to exit code 3 (external tool failure).
    """


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


def _scan_failure_finding(message: str) -> SemgrepFinding:
    """Blocking finding for a scan that could not complete.

    A security scan that dies must fail closed: an empty findings list
    reads as PASS in run(), silently bypassing the gate. An ERROR-severity
    finding rides the existing blocking path instead.
    """
    return SemgrepFinding(
        check_id="semgrep-scan-failure",
        path="global",
        line=0,
        severity="ERROR",
        message=message,
        cwe=[],
        owasp=[],
    )


def _semgrep_output_snippet(value: str, *, fallback: str) -> str:
    """Return a bounded one-line diagnostic from semgrep output."""
    if not value:
        return fallback

    prefix = value[:SEMGREP_OUTPUT_SNIPPET_CHARS]
    text = prefix.strip()
    if not text:
        if len(value) <= SEMGREP_OUTPUT_SNIPPET_CHARS:
            return fallback
        return "[output begins with whitespace; truncated]"

    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(value) <= SEMGREP_OUTPUT_SNIPPET_CHARS:
        return text
    return f"{text}... [truncated]"


def _semgrep_failure_context(stdout: str, stderr: str) -> str:
    return (
        "stderr="
        f"{_semgrep_output_snippet(stderr, fallback='no stderr')}; "
        "stdout="
        f"{_semgrep_output_snippet(stdout, fallback='no stdout')}"
    )


class _SemgrepExecutableError(RuntimeError):
    """Raised when the pinned semgrep executable cannot be resolved.

    A scanner that silently falls back to a wrong version is worse than one
    that is absent: it reports green against rules from the wrong ruleset.
    Fail loudly so the caller knows the gate did not run.
    """


# Canonical remediation for a missing or mismatched semgrep. pyproject.toml
# pins semgrep in [project.optional-dependencies].dev and mirrors that pin in
# [dependency-groups].dev; uv installs exactly those pins from uv.lock.
# scripts/install_semgrep.py runs `pip install semgrep` with no version, so it
# can install a build this resolver rejects; it is deliberately not offered.
_INSTALL_HINT = "uv sync --frozen --extra dev"


def _semgrep_pinned_version(repo_root: Path) -> str:
    """Read the semgrep version pin from pyproject.toml.

    Fails loudly if the pin is missing or ambiguous: a scanner whose
    version is unknown has no reproducibility guarantee.
    """
    pyproject = repo_root / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError as exc:
        raise _SemgrepExecutableError(
            f"cannot read semgrep pin from {pyproject}: {exc}"
        ) from exc
    matches: list[str] = re.findall(
        r'^\s*"semgrep==([^"]+)",\s*$',
        text,
        re.MULTILINE,
    )
    versions = set(matches)
    if len(versions) != 1:
        raise _SemgrepExecutableError(
            f"pyproject.toml must declare exactly one semgrep pin, "
            f"found: {sorted(versions)!r}"
        )
    return versions.pop()


def _probe_semgrep_version(executable: str) -> str:
    """Return the version string reported by the semgrep binary."""
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise _SemgrepExecutableError(
            f"semgrep version probe failed for {executable}: {exc}"
        ) from exc
    if result.returncode != 0:
        raise _SemgrepExecutableError(
            f"semgrep version probe exited {result.returncode} "
            f"for {executable}: {result.stderr.strip()}"
        )
    version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not version:
        raise _SemgrepExecutableError(
            f"semgrep version probe returned no output for {executable}"
        )
    return version


def _verify_pinned_version(executable: str, repo_root: Path) -> str:
    """Return ``executable`` once it reports the pyproject.toml pin.

    Raises ``_SemgrepExecutableError`` on any mismatch: a scanner running an
    unpinned build reports findings from a different ruleset than CI does.
    """
    version = _probe_semgrep_version(executable)
    pinned = _semgrep_pinned_version(repo_root)
    if version != pinned:
        raise _SemgrepExecutableError(
            f"semgrep version mismatch: pyproject.toml pins {pinned!r}, "
            f"but {executable} reports {version!r}. "
            f"Reinstall the pin with: {_INSTALL_HINT}"
        )
    return executable


def _resolve_semgrep_executable(repo_root: Path) -> str:
    """Return the path to a pinned semgrep binary.

    Preference order, both verified against the pyproject.toml pin:
    1. A ``semgrep`` sibling of the current interpreter (inside the venv).
    2. The first ``semgrep`` on PATH.

    Raises ``_SemgrepExecutableError`` if no matching binary is found, and
    ``FileNotFoundError`` if semgrep is not on PATH at all.  Both map to a
    loud failure rather than a silent fallback.

    Stricter/looser/different than canonical: the sibling branch of
    ``scripts/validation/git_hook_policy.py::_resolve_semgrep_executable``
    returns the venv sibling with no version probe (its
    ``test_semgrep_uses_sibling_binary_without_version_probe`` in
    ``tests/test_lefthook_integration.py`` asserts ``args[1] != "--version"``).
    This resolver is stricter: it probes the sibling too, because a venv built
    by anything other than ``uv sync`` (a manual ``pip install semgrep``, or a
    venv left over from an older pin) puts an unpinned binary in that exact
    slot and the scan then passes against the wrong ruleset. The extra probe
    costs one ``semgrep --version`` call per resolution.
    """
    sibling_name = "semgrep.exe" if os.name == "nt" else "semgrep"
    sibling = Path(sys.executable).parent / sibling_name
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return _verify_pinned_version(str(sibling), repo_root)

    resolved = shutil.which("semgrep")
    if resolved is None:
        raise FileNotFoundError("semgrep not found on PATH")

    return _verify_pinned_version(resolved, repo_root)


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

    # Wall-clock ceiling for a single semgrep invocation. A wedged scan must not
    # hang the pre-push hook indefinitely; on timeout the scan fails closed
    # (exit 3) rather than reporting a clean pass.
    SCAN_TIMEOUT_SECONDS = 300

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
        root = get_repo_root()
        if root is None:
            raise subprocess.CalledProcessError(1, "git rev-parse")
        return root

    def _check_semgrep_installed(self) -> bool:
        """Check if the pinned semgrep binary is resolvable.

        Resolves via ``_resolve_semgrep_executable``, which verifies the version
        against the pyproject.toml pin. Returns False (with a logged error) for
        any resolution failure so the caller can report the exact reason.
        """
        try:
            _resolve_semgrep_executable(self.repo_root)
            return True
        except FileNotFoundError:
            logger.error("ERROR: semgrep not found on PATH")
            logger.error("")
            logger.error("Install the pinned version with:")
            logger.error("  %s", _INSTALL_HINT)
            return False
        except _SemgrepExecutableError as exc:
            logger.error("ERROR: semgrep resolution failed: %s", exc)
            return False

    def _get_changed_files(self) -> list[Path]:
        """Get files changed in the current branch vs main."""
        try:
            merge_base_result = subprocess.run(
                ["git", "merge-base", "origin/main", "HEAD"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if merge_base_result.returncode != 0:
                logger.warning("Could not find merge-base with origin/main, scanning all files")
                result = subprocess.run(
                    ["git", "ls-files"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                )
            else:
                merge_base = merge_base_result.stdout.strip()
                result = subprocess.run(
                    ["git", "diff", "--name-only", f"{merge_base}...HEAD"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                )

            files = result.stdout.strip().split("\n") if result.stdout.strip() else []

            filtered = [
                self.repo_root / f
                for f in files
                if Path(f).suffix in self.SUPPORTED_EXTENSIONS and (self.repo_root / f).exists()
            ]

            return filtered

        except subprocess.SubprocessError as e:
            logger.error("Failed to get changed files: %s", e)
            return []

    def _run_semgrep(self, files: list[Path]) -> list[SemgrepFinding]:
        """Run semgrep on the specified files using the pinned executable."""
        if not files:
            return []

        try:
            executable = _resolve_semgrep_executable(self.repo_root)
        except (FileNotFoundError, _SemgrepExecutableError) as exc:
            return [_scan_failure_finding(f"semgrep resolution failed: {exc}")]

        cmd = [
            executable,
            "scan",
            "--config",
            self.config,
            "--json",
            "--no-git-ignore",
            # requires-python = ">=3.14" (pyproject.toml). The python36 and
            # python37 compatibility families warn about arguments unavailable
            # before those versions, which are eight and seven minor versions
            # below the project floor. Every finding they produce is a
            # guaranteed false positive here, and their own metadata classifies
            # them as "compatibility", not security. Excluding the family keeps
            # them from blocking PRs that comply with the encoding convention
            # that tests/test_subprocess_text_encoding.py mandates (issue #4223).
            "--exclude-rule",
            "python.lang.compatibility.python36",
            "--exclude-rule",
            "python.lang.compatibility.python37",
        ]

        if self.severity:
            cmd.extend(["--severity", self.severity.upper()])

        for f in files:
            cmd.append(str(f))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.repo_root,
                check=False,
                timeout=self.SCAN_TIMEOUT_SECONDS,
            )

            if result.returncode not in (0, 1):
                context = _semgrep_failure_context(result.stdout, result.stderr)
                logger.error("Semgrep execution error: %s", context)
                return [
                    _scan_failure_finding(
                        f"Semgrep exited {result.returncode}: {context}"
                    )
                ]

            if not result.stdout.strip():
                logger.error("Semgrep produced no JSON output")
                return [_scan_failure_finding("Semgrep produced no JSON output")]

            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                context = _semgrep_failure_context(result.stdout, result.stderr)
                logger.error("Semgrep JSON parse failed: %s; %s", e, context)
                return [
                    _scan_failure_finding(
                        f"Semgrep JSON parse failed: {e}; {context}"
                    )
                ]
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

        except subprocess.TimeoutExpired as e:
            logger.error(
                "Semgrep timed out after %ds; failing scan",
                self.SCAN_TIMEOUT_SECONDS,
            )
            raise SemgrepScanError(
                f"Semgrep timed out after {self.SCAN_TIMEOUT_SECONDS}s"
            ) from e
        except (subprocess.SubprocessError, OSError) as e:
            # OSError is listed explicitly: it is NOT a subclass of
            # subprocess.SubprocessError (verified in this session:
            # issubclass(subprocess.SubprocessError, OSError) is False; the two
            # hierarchies are siblings under Exception). subprocess.run raises
            # OSError, not SubprocessError, when the exec itself faults: the
            # binary was deleted between _resolve_semgrep_executable's version
            # probe and this call (TOCTOU -> FileNotFoundError), lost its exec
            # bit (PermissionError), or the kernel refused the spawn (OSError).
            # Without this arm the exception escapes _run_semgrep, run() catches
            # only SemgrepScanError, and the gate dies on a traceback instead of
            # the structured blocking finding below.
            logger.error("Semgrep scan failed: %s", e)
            message = _semgrep_output_snippet(str(e), fallback=type(e).__name__)
            return [_scan_failure_finding(f"Semgrep scan failed: {message}")]

    def run(self) -> int:
        """Execute the semgrep scan workflow."""
        if not self._check_semgrep_installed():
            return 2

        logger.info("Semgrep security scan starting")

        if self.dry_run:
            logger.info("[DRY RUN] No blocking will occur")

        changed_files = self._get_changed_files()

        if not changed_files:
            logger.info("PASS: No files to scan")
            return 0

        logger.info("Scanning %d file(s)", len(changed_files))

        try:
            findings = self._run_semgrep(changed_files)
        except SemgrepScanError as e:
            logger.error("FAIL: %s", e)
            return 3

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
