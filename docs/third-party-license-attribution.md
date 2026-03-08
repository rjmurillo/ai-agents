# Third-Party License Attribution

This document describes the procedures for researching, attributing, and maintaining
third-party component licenses in compliance with legal and regulatory requirements.

## Overview

This project uses the MIT license. All third-party components must be tracked in
`THIRD-PARTY-NOTICES.TXT` at the repository root. This file follows the format used
by Microsoft's dotnet/runtime project.

## Component Categories

| Category | Source | Example |
|----------|--------|---------|
| Python direct | `pyproject.toml` dependencies | anthropic, PyYAML |
| Python transitive | `uv.lock` resolved packages | pydantic, httpx |
| GitHub Actions | `.github/workflows/*.yml` uses | actions/checkout, dorny/paths-filter |
| Docker images | `Dockerfile` FROM statements | python:3.14 |

## License Compatibility

This project is MIT-licensed. Compatible inbound licenses:

| License | Compatible | Notes |
|---------|-----------|-------|
| MIT | Yes | Permissive, attribution required |
| BSD-2-Clause | Yes | Permissive, attribution required |
| BSD-3-Clause | Yes | Permissive, no endorsement clause |
| Apache-2.0 | Yes | Patent grant, NOTICE file required |
| ISC | Yes | Permissive, attribution required |
| PSF | Yes | Python Software Foundation license |
| Unlicense | Yes | Public domain dedication |
| MPL-2.0 | Yes (with care) | File-level copyleft, attribution required |
| LGPL | Caution | Dynamic linking only |
| GPL | No | Copyleft incompatible with MIT distribution |
| AGPL | No | Network copyleft, incompatible |

Before adding a dependency with GPL, LGPL, or AGPL, consult legal counsel.

## Attribution Requirements by License

### MIT, BSD-2-Clause, BSD-3-Clause, ISC

- Include copyright notice and license text in THIRD-PARTY-NOTICES.TXT

### Apache-2.0

- Include copyright notice and license text
- Preserve any NOTICE file content from the dependency
- Note: Apache-2.0 includes an explicit patent grant

### MPL-2.0

- Include copyright notice and license text
- MPL-2.0 is file-level copyleft: modifications to MPL-licensed files must remain
  under MPL-2.0, but combining with MIT code in other files is permitted

## Generating the Notices File

Run the generator script:

```bash
uv run python3 scripts/generate_third_party_notices.py
```

The script:

1. Reads `pyproject.toml` to identify direct vs. transitive dependencies
2. Queries `importlib.metadata` for installed package license metadata
3. Extracts embedded license text from package distributions
4. Scans `.github/workflows/` and `.github/actions/` for third-party Actions
5. Looks up known licenses from a curated mapping
6. Writes `THIRD-PARTY-NOTICES.TXT` in the dotnet/runtime format

### Check Mode

Verify the file is current without modifying it:

```bash
uv run python3 scripts/generate_third_party_notices.py --check
```

This returns exit code 1 if the file is out of date.

## When to Update

Update `THIRD-PARTY-NOTICES.TXT` when:

- Adding or removing a dependency in `pyproject.toml`
- Upgrading a dependency version (license text may change)
- Adding a new GitHub Action to any workflow
- Adding a Docker base image
- Renovate bot merges a dependency update PR

## Research Procedure for New Dependencies

Before adding a new third-party component:

1. **Identify the license.** Check the package's PyPI page, GitHub repository,
   or `LICENSE` file. Use `pip show <package>` or `importlib.metadata.metadata()`.

2. **Verify compatibility.** Confirm the license is in the compatible list above.
   If the license is not listed, evaluate before proceeding.

3. **Check transitive dependencies.** A permissive package may pull in a
   copyleft transitive dependency. Run `pip-licenses --packages <pkg> --with-urls`
   or inspect the dependency tree with `uv tree`.

4. **Document in the notices file.** Run the generator script after installing
   the new package. Verify the output includes the new component with correct
   license information.

5. **Handle unknown licenses.** If the generator reports an unknown license,
   manually research and add the license to `KNOWN_LICENSES` in
   `scripts/generate_third_party_notices.py`.

## Maintaining the Known Licenses Map

The generator script contains a `KNOWN_LICENSES` dictionary for packages whose
metadata does not include a machine-readable license field. When updating this map:

- Verify the license from the package's official repository
- Use SPDX identifiers (e.g., "MIT", "Apache-2.0", "BSD-3-Clause")
- Add a comment with the verification source if the license is ambiguous

## GitHub Actions Attribution

GitHub Actions are SHA-pinned for security (per project policy). The generator
maintains an `ACTIONS_LICENSES` dictionary mapping action names to their licenses.
When adding a new action:

1. Check the action's repository for a LICENSE file
2. Add the action to `ACTIONS_LICENSES` in the generator script
3. Re-run the generator

## Compliance Checklist

When preparing a release:

- [ ] Run `uv run python3 scripts/generate_third_party_notices.py --check`
- [ ] Verify no "Unknown" licenses in the output
- [ ] Confirm no GPL/AGPL dependencies were added
- [ ] Review any MPL-2.0 dependencies for file-level copyleft implications
- [ ] Verify Apache-2.0 dependencies have NOTICE file content preserved
