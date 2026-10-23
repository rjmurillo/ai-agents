# Bump a vulnerable dependency under the uv 7-day cooldown (90%)

## Statement

Run `uv lock` with `exclude-newer = "7 days"` and a fix newer than 7 days stays invisible. The lock keeps the vulnerable version.

Opt the package out with `[tool.uv.exclude-newer-package] <pkg> = false` in `pyproject.toml`. Add the package to `COOLDOWN_EXEMPT_PACKAGES` in `tests/test_pyproject_dev_deps_parity.py`. Skip either step and `uv lock --check` or the parity test fails.

Pin the exempt package with an exact `override-dependencies` entry. A later `uv lock` then cannot take an unreviewed release.

## Capped by another package

A lock-only bump does nothing when another package caps the version. semgrep 1.181.0 requires `opentelemetry-api<1.38`, so `uv lock` kept 1.37.0.

Pin the whole family with exact `override-dependencies` entries. Each family member pins the exact api release, so all must move together. Add each entry to `SAFE_SEMGREP_OVERRIDES` in the parity test.

## Evidence

- PR #6825 (merged): certifi 2026.7.22 to 2026.10.19 for PYSEC-2026-4320. Touched `pyproject.toml`, the parity test, and `uv.lock`.
- PR #6845 (merged): opentelemetry-api 1.37.0 to 1.45.1 for CVE-2026-114603. Ten family pins, all added to `SAFE_SEMGREP_OVERRIDES`.
- Both PRs read on 2026-10-23.
