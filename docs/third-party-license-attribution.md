# Third-Party License Attribution

This document describes the policy and procedure for third-party license
attribution in this project.

## Scope: Shipped Components Only

Attribution applies to components **shipped** as part of the plugins defined
in `.claude-plugin/marketplace.json`. "Shipped" means the component is
redistributed to users when they install a plugin.

**Requires attribution:**

- Forked or vendored source code included in a plugin source path
- Runtime dependencies declared in `requirements.txt` files within shipped paths

**Does not require attribution:**

- Dev-only tools (pytest, ruff, mypy, bandit)
- Build and CI infrastructure (GitHub Actions, Docker images)
- Transitive pip packages users install from PyPI themselves
- Test frameworks and test utilities

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

## Generating the Notices File

Run the generator script:

```bash
uv run python3 scripts/generate_third_party_notices.py
```

The script:

1. Reads `.claude-plugin/marketplace.json` to determine shipped plugin paths
2. Scans those paths for forked/vendored components (matched against
   `FORKED_COMPONENTS` in the script)
3. Scans for `requirements.txt` files in shipped paths to find runtime
   dependencies (matched against `RUNTIME_DEPENDENCIES` in the script)
4. Writes `THIRD-PARTY-NOTICES.TXT` in the dotnet/runtime format

### Check Mode

Verify the file is current without modifying it:

```bash
uv run python3 scripts/generate_third_party_notices.py --check
```

Returns exit code 1 if the file is out of date.

## When to Update

Update `THIRD-PARTY-NOTICES.TXT` when:

- Adding or removing a forked/vendored component in a shipped plugin path
- Adding a runtime dependency to a `requirements.txt` in a shipped path
- Changing the license text for an existing component
- Adding a new plugin to `.claude-plugin/marketplace.json`

## Adding a New Shipped Component

### Forked or Vendored Code

1. **Identify the license.** Check the upstream repository's LICENSE file.
2. **Verify compatibility.** Confirm the license is in the table above.
3. **Add to `FORKED_COMPONENTS`** in `scripts/generate_third_party_notices.py`
   with name, license type, URL, author, local path, and full license text.
4. **Run the generator** to update `THIRD-PARTY-NOTICES.TXT`.
5. **Commit both files** together.

### Runtime Dependencies

1. **Identify the license.** Check PyPI or the package's GitHub repository.
2. **Verify compatibility.** Confirm the license is in the table above.
3. **Add to `RUNTIME_DEPENDENCIES`** in `scripts/generate_third_party_notices.py`
   with name, license type, URL, author, declared-in path, and license text.
4. **Run the generator** to update `THIRD-PARTY-NOTICES.TXT`.
5. **Commit both files** together.

## Attribution Requirements by License

### MIT, BSD-2-Clause, BSD-3-Clause, ISC

- Include copyright notice and license text in THIRD-PARTY-NOTICES.TXT

### Apache-2.0

- Include copyright notice and license text
- Preserve any NOTICE file content from the dependency
- Note: Apache-2.0 includes an explicit patent grant

### MPL-2.0

- Include copyright notice and license text
- MPL-2.0 is file-level copyleft: modifications to MPL-licensed files must
  remain under MPL-2.0, but combining with MIT code in other files is permitted

## Compliance Checklist

When preparing a release:

- [ ] Run `uv run python3 scripts/generate_third_party_notices.py --check`
- [ ] Verify no "Unknown" licenses in the output
- [ ] Confirm no GPL/AGPL dependencies in shipped paths
- [ ] Review any MPL-2.0 dependencies for file-level copyleft implications
- [ ] Verify Apache-2.0 dependencies have NOTICE file content preserved
