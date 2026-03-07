"""Validation scripts package for CI and manual validation workflows.

Migrated from PowerShell Validate-*.ps1 scripts per ADR-042.
"""

from scripts.validation.models import ValidationResult

__all__ = ["ValidationResult"]
