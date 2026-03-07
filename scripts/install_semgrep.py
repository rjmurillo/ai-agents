#!/usr/bin/env python3
"""
Semgrep Installation Script

Installs semgrep for local security scanning. Checks for existing installation
and provides platform-specific guidance.

Usage:
    python3 scripts/Install-Semgrep.py
    python3 scripts/Install-Semgrep.py --check  # Check installation only

Exit Codes:
    0: Success (already installed or installation succeeded)
    1: Installation failed
    2: Unsupported platform or missing dependencies

Per ADR-042: Python-first for new scripts.
"""

from __future__ import annotations

import argparse
import logging
import platform
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


class SemgrepInstaller:
    """Handles semgrep installation across platforms."""

    def __init__(self, check_only: bool = False) -> None:
        self.check_only = check_only
        self.system = platform.system()

    def is_installed(self) -> bool:
        """Check if semgrep is already installed."""
        try:
            result = subprocess.run(
                ["semgrep", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info("✓ Semgrep already installed: %s", version)
                return True
            return False
        except FileNotFoundError:
            return False

    def install(self) -> bool:
        """Install semgrep using pip."""
        logger.info("Installing semgrep via pip...")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "semgrep"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info("✓ Semgrep installed successfully")
                return True

            logger.error("Installation failed: %s", result.stderr)
            return False

        except subprocess.SubprocessError as e:
            logger.error("Installation error: %s", e)
            return False

    def show_manual_instructions(self) -> None:
        """Show platform-specific manual installation instructions."""
        logger.info("")
        logger.info("Manual installation options:")
        logger.info("")

        if self.system == "Darwin":
            logger.info("macOS:")
            logger.info("  brew install semgrep")
        elif self.system == "Linux":
            logger.info("Linux:")
            logger.info("  pip install semgrep")
        elif self.system == "Windows":
            logger.info("Windows:")
            logger.info("  pip install semgrep")
        else:
            logger.info("Generic:")
            logger.info("  pip install semgrep")

        logger.info("")
        logger.info("Or use pip directly:")
        logger.info("  %s -m pip install semgrep", sys.executable)

    def run(self) -> int:
        """Execute installation workflow."""
        if self.is_installed():
            return 0

        if self.check_only:
            logger.error("✗ Semgrep not installed")
            self.show_manual_instructions()
            return 1

        if not self.install():
            logger.error("")
            logger.error("Automatic installation failed")
            self.show_manual_instructions()
            return 1

        if not self.is_installed():
            logger.error("✗ Installation verification failed")
            return 1

        return 0


def main() -> int:
    """Entry point for semgrep installation script."""
    parser = argparse.ArgumentParser(
        description="Install semgrep for local security scanning"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if semgrep is installed without installing",
    )

    args = parser.parse_args()

    installer = SemgrepInstaller(check_only=args.check)
    return installer.run()


if __name__ == "__main__":
    sys.exit(main())
