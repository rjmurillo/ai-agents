# Skill Observations: environment

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 3

## Purpose

This memory captures learnings from environment setup, platform compatibility, and runtime configuration patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Python 3.13.x SystemError breaks CodeQL and skill validation - use Python 3.12.8 via pyenv for compatibility (Session 05, 2026-01-15)
  - Evidence: Batch 37 - Python 3.13.7 SystemError during CodeQL database creation and skill validation on Ubuntu 25.10
  - Root cause: Python 3.13.7 SystemError: failed to join paths during CodeQL Python database creation
  - Solution: `pyenv install 3.12.8` + create `.python-version` file with `3.12.8` to pin version for CodeQL
  - Impact: Affected CodeQL Python database creation, skill validation, Python script execution
- Serena MCP tools fallback to file-based memory when unavailable - implement graceful degradation for MCP tool failures (Session 2, 2026-01-15)
  - Evidence: Batch 37 - Serena MCP unavailability triggered fallback to file-based memory operations

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-15 | Session 05 | HIGH | Python 3.13.x SystemError breaks CodeQL and skill validation |
| 2026-01-15 | Session 2 | HIGH | Serena MCP tools fallback to file-based memory |

## Related

- [ci-infrastructure-environment-simulation](ci-infrastructure-environment-simulation.md)
