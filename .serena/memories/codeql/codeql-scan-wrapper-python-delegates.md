# codeql-scan Wrapper Delegates (Issue #4921)

**Importance**: HIGH
**Date**: 2026-08-13
**Session**: 14705
**Issue**: #4921

## What was broken

The `codeql-scan` skill wrappers resolved PowerShell scripts deleted during the
ADR-042 Python migration. Every operation failed before scanning:

```text
python3 .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation validate
[x] Configuration script not found: .codeql/scripts/Test-CodeQLConfig.ps1
exit 3
```

## Canonical delegate contracts

`.codeql/scripts/` ships Python only. Verified from each `build_parser()`:

| Delegate | Flags used by the wrapper | Exit codes |
|----------|---------------------------|------------|
| `test_codeql_config.py` | (none; cwd anchors `--config-path`) | 0 valid, 1 invalid, 2 config file absent |
| `invoke_codeql_scan.py` | `--use-cache`, `--languages`, `--ci` | 0 ok, 1 findings in CI, 2 config, 3 external |
| `install_codeql.py` | `--add-to-path` | 0/1/2/3 |

PowerShell-to-Python flag translation: `-UseCache` to `--use-cache`,
`-Languages` to `--languages`, `-CI` to `--ci`, `-AddToPath` to `--add-to-path`.

## Patterns worth reusing

1. **Launch delegates with `sys.executable`**, never a bare `python3`. The child
   then runs in the same interpreter and virtual environment as the parent.
   Fall back to `"python3"` only when `sys.executable` is empty (frozen builds).
2. **Pass `cwd=repo_root` instead of restating default paths.** All three
   delegates resolve their relative defaults against the working directory, so
   one `cwd` argument fixes validate and scan from a linked worktree and from
   any subdirectory, without duplicating `.github/codeql/codeql-config.yml`.
3. **A fixture cannot disagree with the code that names it.** Every pre-existing
   test fabricated the delegate under `tmp_path` using whatever name the wrapper
   asked for, so the suite stayed green for as long as the skill was broken.
   Tests that bind to reality live in
   `tests/skills/codeql-scan/test_codeql_delegate_paths.py`: assert declared
   names exist in the real `.codeql/scripts/`, feed emitted flags to the real
   delegate `build_parser()`, and run the wrapper as a subprocess in the checkout.

## Sibling defects with the same shape

Broadening a fix to one caller leaves the rest broken. Fixed in the same PR:

- `invoke_codeql_scan_skill.py`: an undocumented second wrapper with the same
  PowerShell paths.
- `invoke_codeql_scan.py`: a `shutil.which("pwsh")` gate that returned 0 with
  `[SKIP] pwsh not found`, reporting success without scanning.
- `.codeql/scripts/install_codeql_integration.py`: verified the removed
  `Invoke-CodeQLScanSkill.ps1`, so it reported the skill missing when installed.
- `.vscode/tasks.json`: five tasks invoking the removed `.ps1` files.

## Gotchas

- `build_all.py --check` is the drift gate for `src/copilot-cli/skills/`. Never
  hand-edit the generated tree. Capture its exit code directly: `cmd | tail`
  makes `$?` report `tail`, which silently reads as a pass.
- CodeQL has no PowerShell support, and `detect_languages()` emits only `python`
  and `actions`. A `powershell` option in any language picklist is dead.

## Open follow-ups

- `invoke_codeql_scan_skill.py` duplicates `invoke_codeql_scan.py` and is
  undocumented in SKILL.md (skillforge warns). Consider consolidating.
- `test_codeql_config.py` derives repo root as `Path(config_path).parent.parent`,
  which yields `.github` and emits spurious "Path does not exist" warnings.

## Related

- `mem:codeql/codeql-security-integration`
- ADR-042 (Python migration), ADR-035 (exit codes)
- `.agents/governance/GENERATOR-FILES.md`
