---
id: ADR-047
status: accepted
date: 2026-11-24
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-047: Plugin-Mode Hook Behavior

## Status

Accepted. See the 2026-04-29, 2026-11-19, and 2026-11-24 amendments.

## Date

2026-02-16

## Context

This project is distributed as a Claude Code marketplace plugin installed by hundreds of engineers. When installed, the `.claude/` directory is copied to a cache directory, and `.agents/` directories are created in the consumer's project root.

Two environment variables govern plugin execution:

| Variable | Set When | Points To |
|----------|----------|-----------|
| `CLAUDE_PLUGIN_ROOT` | Running as installed plugin | Plugin cache directory |
| `CLAUDE_PROJECT_DIR` | Always (all hooks) | Consumer's project root |

The codebase has 10+ hooks and 30+ skill scripts that need to work in both contexts:

1. **Source repo**: Developer working on this project directly
2. **Plugin mode**: Consumer who installed via marketplace

An initial approach used `sys.exit(0)` at the top of every hook when `CLAUDE_PLUGIN_ROOT` was set, skipping all enforcement in consumer repos. This was wrong. The plugin IS the system. Hooks like ADR review enforcement, skill-first guards, session protocol, and QA validation are the product. Skipping them defeats the purpose of installing the plugin.

Similarly, scripts that checked for `.agents/` existence and skipped when absent were incorrect. The plugin creates `.agents/` on installation, and if somehow missing, the correct behavior is to create it, not silently skip.

## Decision

All hooks and skills run in plugin mode. No hook uses `CLAUDE_PLUGIN_ROOT` as a skip signal.

### Path Resolution

Hooks and skill scripts resolve library imports using a standard pattern. Skill scripts that import `hook_utilities.frontmatter_block` use the shape in the 2026-11-24 amendment instead.

```python
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
```

This resolves to:
- **Plugin mode**: `$CLAUDE_PLUGIN_ROOT/lib/` (shared libraries bundled with plugin)
- **Source repo**: `.claude/lib/` (relative to script location)

### Project Directory Resolution

All hooks use `CLAUDE_PROJECT_DIR` (via `get_project_directory()`) for consumer project paths. Never assume the project root is the plugin install directory.

### Directory Creation

When a required directory (e.g., `.agents/`, `.project-toolkit/sessions/`) does not exist, create it with `os.makedirs(path, exist_ok=True)`. Do not skip operations due to missing directories.

### Standard Import Boilerplate

Every hook or skill script that imports from `.claude/lib/` MUST use this pattern with path validation, except the skill scripts the 2026-11-19 and 2026-11-24 amendments cover. The pattern checks `CLAUDE_PLUGIN_ROOT` first, then walks up from `__file__` looking for the `.claude-plugin/plugin.json` manifest marker:

```python
# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
```

The path validation prevents importing from non-existent directories, which would cause confusing ImportError messages later. To prevent drift across 40+ files, a shared test validates the pattern (see Implementation Notes).

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Skip all hooks in plugin mode | Simple, safe | Defeats purpose of the plugin | Plugin IS the enforcement system |
| Classify hooks as skip/run | Granular control | Complex, error-prone categorization | All hooks provide value to consumers |
| Environment-variable-based feature flags | Selective enforcement | Configuration burden on consumers | YAGNI, adds maintenance cost |

### Trade-offs

- **Duplication**. An ordinary import needs the library directory on `sys.path` first. Keep the hook bootstrap inline. The 2026-11-19 amendment records the shared resolver for two skill entry points.
- **Directory creation**: `os.makedirs(exist_ok=True)` is safe and idempotent, but creates directories that may not be expected by all consumers. The plugin documentation should describe the `.agents/` directory.

## Consequences

### Positive

- Plugin consumers get full enforcement (ADR review, skill-first, session protocol, QA validation)
- No silent degradation in plugin mode
- Single code path reduces testing surface

### Negative

- Every hook must handle both path resolution modes
- 7 lines of boilerplate in every file that imports from lib
- Consumer projects get `.agents/` directories created automatically

### Neutral

- `CLAUDE_PLUGIN_ROOT` is used ONLY for path resolution, never for behavior gating
- `CLAUDE_PROJECT_DIR` remains the single source of truth for project root

### Security Considerations

Environment variables `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR` form a trust boundary. Implementations MUST validate these values before file system operations:

**Trust Model**: These environment variables are set by Claude Code runtime, not user-controllable. However, in CI/CD contexts (e.g., GitHub Actions), environment variables may be attacker-controlled in forked PRs using `pull_request_target`. Implement defense-in-depth regardless of trust assumptions.

**Path Normalization**: Use `Path.resolve()` to eliminate `..` sequences:

```python
def get_project_directory() -> str:
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return str(Path(env_dir).resolve())  # Normalize path
    return os.getcwd()
```

**Containment Validation**: Verify resolved paths remain within expected boundaries:

```python
SAFE_BASE_DIR = Path(__file__).resolve().parents[3]


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


# Verify path is within project boundary
if not _is_relative_to(candidate_path, SAFE_BASE_DIR):
    return str(SAFE_BASE_DIR)  # Fallback to safe default
```

**Pre-Validation**: Reject malicious patterns before `Path()` construction:

```python
def _validate_path_string(path_str: str) -> str | None:
    # Reject null bytes (CWE-158), control chars, traversal patterns
    if "\x00" in path_str or any(c in path_str for c in ["\n", "\r", "\t"]):
        return None
    normalized = path_str.replace("\\", "/")
    if "/../" in normalized or normalized.startswith("../"):
        return None
    return path_str
```

**Canonical Implementations**:
- `.claude/lib/hook_utilities/utilities.py:18-45` (get_project_directory with Path.resolve)
- Historical removed hook reference: `.claude/hooks/Stop/invoke_skill_learning.py:66-95` (_validate_path_string pattern)

**Test Requirements**: All hooks MUST pass path traversal rejection tests (e.g., `CLAUDE_PROJECT_DIR=../../etc/passwd`).

## Implementation Notes

### Test Coverage

Add a standardized test to verify the import boilerplate pattern across all hooks and skill scripts:

```python
def test_plugin_path_resolution_pattern():
    """Verify all hooks with lib imports use the standard resolution pattern."""
    for hook_path in glob(".claude/hooks/**/*.py"):
        content = hook_path.read_text()
        if "from hook_utilities" in content or "from github_core" in content:
            assert 'os.environ.get("CLAUDE_PLUGIN_ROOT")' in content
            assert "sys.exit(0)" not in content  # No early exits
```

### Error Handling

Directory creation must handle permission errors:

```python
try:
    os.makedirs(path, exist_ok=True)
except OSError as exc:
    print(f"Cannot create {path}: {exc}", file=sys.stderr)
    sys.exit(2)  # ADR-035: config/environment error
```

Path resolution must verify lib directory exists:

```python
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # ADR-035: config/environment error
```

### Checklist for New Hooks

When creating a new hook or skill script:

1. Use the standard 7-line import boilerplate if importing from `.claude/lib/`. A skill script that imports `hook_utilities.frontmatter_block` uses the 2026-11-24 amendment's shape instead. `council.py` and `sol_loop.py` use `load_skill_paths()` per the 2026-11-19 amendment
2. Use `get_project_directory()` for consumer project paths
3. **Validate all paths are within project boundary before file operations**
4. Use `os.makedirs(path, exist_ok=True)` for required directories **AFTER path validation**
5. Never gate behavior on `CLAUDE_PLUGIN_ROOT` presence
6. Test with `CLAUDE_PLUGIN_ROOT=/tmp/test python3 hook.py` to verify plugin mode
7. **Test with malicious environment variables to verify rejection** (`CLAUDE_PROJECT_DIR=../../etc`)

## Amendments

### 2026-04-29: Manifest walk-up replaces `GITHUB_WORKSPACE`/`parents[N]` resolver

**Change**: The Standard Import Boilerplate now resolves the lib directory using two branches: `CLAUDE_PLUGIN_ROOT` env var, then a walk up from `__file__` looking for `.claude-plugin/plugin.json`. The previous three-branch resolver (`CLAUDE_PLUGIN_ROOT` → `GITHUB_WORKSPACE` → relative `parents[4]/lib`) is replaced.

**Why**:

- **Layout independence**. The `parents[4]` form hard-codes the depth from `__file__` to the lib directory. It works for `.claude/hooks/<Event>/<hook>.py` (depth 4) but breaks for the deeper plugin layout `src/<provider>/hooks/<Event>/<hook>.py` (depth 5) and for skill scripts at unrelated depths. The manifest walk-up resolves correctly in every layout because it stops on the plugin marker, not a count. The shipped migration script (`scripts/migrations/req003_inline_plugin_root_bootstrap.py:46-68`) already implements the layout-independent form, and 23 hooks now use it.
- **`GITHUB_WORKSPACE` is redundant**. In CI, the working tree contains a `.claude-plugin/plugin.json` marker at the repository root. The walk-up finds it without an env-var hint. Keeping `GITHUB_WORKSPACE` adds a third branch with no behavior the walk-up doesn't already provide.
- **One resolver, one mental model**. Two branches are easier to grep, easier to audit, and easier to keep correct across 40+ files than three.

**Behavioral compatibility**: The two-branch form is a strict superset of the three-branch form for every layout this project ships:

| Scenario | Old resolver | New resolver | Result |
|----------|--------------|--------------|--------|
| Plugin install (`CLAUDE_PLUGIN_ROOT` set) | branch 1 | branch 1 | identical |
| GitHub Actions checkout | `GITHUB_WORKSPACE`/.claude/lib | walk-up finds repo root marker | identical |
| Source tree, depth-4 hook | `parents[4]/lib` | walk-up finds `.claude-plugin/plugin.json` | identical |
| Source tree, depth-5 hook (`src/<provider>/...`) | wrong path (off by one) | walk-up still finds marker | **fixed** |

**Error message**: The error string was widened to include the resolved `_lib_dir` and the value of `CLAUDE_PLUGIN_ROOT` so the failure mode (env-var typo vs missing marker) is diagnosable from the stderr alone.

**Test impact**: `tests/test_plugin_path_resolution.py` continues to assert the literal string `os.environ.get("CLAUDE_PLUGIN_ROOT")` is present in every hook with a lib import. The test does NOT assert `GITHUB_WORKSPACE` is present, so the test passes both before and after this amendment.

**Migration**: The 23 production hooks were migrated to the manifest-walk-up form by `scripts/migrations/req003_inline_plugin_root_bootstrap.py` as part of REQ-003. Re-running the migration is idempotent.

### 2026-11-19: Share the paths bootstrap for llm-council and sol-loop

The original debate considered extraction and kept inline bootstraps for hooks.
The two skill entry points introduced together in #7416 share a layout.
Each ships at `skills/<skill>/scripts/<entry>.py` beside its plugin's `lib/`.

Only `council.py` and `sol_loop.py` receive this exception to the inline requirement.
They load their bundled `lib/bootstrap.py` by its resolved file path.
This follows source-tree skill links and entry-file symlinks.
Environment hints and Python's module search cannot select a different bootstrap.
The editable source is `scripts/hook_utilities/bootstrap.py`.
The existing build distributes it without adding shipped files.

`load_skill_paths()` checks the Copilot root, Claude root, then the skill's own lib.
Each candidate must hold a file at `lib/paths.py`.
The helper loads that exact file under a private module name.
Cached modules and packages cannot replace the selected file.
The selected library stays off Python's module search path.
The resolved entry directory comes first for sibling imports.
Exhausted candidates raise `RuntimeError`, listing their paths in order.
A partial install missing the bundled bootstrap fails while loading that file.

Hook callers keep their existing bootstrap and failure handling.
Other skill callers retain the inline requirement, except the 2026-11-24 amendment's scripts and the older scripts its Out of scope paragraph counts.

### 2026-11-24: Skill scripts that load the shared parser prefer their own lib

**Change**: Skill scripts that import `hook_utilities.frontmatter_block` use a new bootstrap shape. They read `Path(__file__).resolve().parents[3] / "lib"` first. They switch to the environment root's `lib` only when their own lib lacks `hook_utilities/frontmatter_block.py`. The environment root is `$COPILOT_PLUGIN_ROOT` when set, else `$CLAUDE_PLUGIN_ROOT`; the Standard Import Boilerplate reads only `CLAUDE_PLUGIN_ROOT`. PR #7531 added this shape to 18 authored scripts under `src/claude/skills/` and `.claude/skills/` (counted 2026-11-24). The build mirrors it into every plugin tree that ships those skills. PR #7531 changed no hook, so hooks keep the Standard Import Boilerplate above.

**Why**:

- **A foreign root must not shadow the parser.** With the environment root first, a root naming another plugin, or an older copy of this one, wins whenever its lib holds a file of that name. Review of PR #7531 found an older parser without `fence_end` could load that way. The security, architect, and agent-safety axes each flagged it.
- **The depth is fixed for skill scripts.** Every one sits at `<plugin>/skills/<name>/scripts/`, so `parents[3]` is the plugin root. The codex, cursor, muse, and hermes trees carry no `.claude-plugin/plugin.json`, so the manifest walk-up would find no marker there.
- **The probe names the module the script imports.** ADR-121's locator tells a foreign root apart by `lib/ptk_run.py`. This bootstrap checks for the file it is about to import, so the check matches the need.
- **Rejected: keep the environment root first and check its parser version.** A version check needs a version contract the parser does not have, and it still trusts a root that only looks current. Preferring the script's own lib needs no contract.

**Behavioral compatibility**:

| Scenario | Standard boilerplate | This shape |
|----------|----------------------|------------|
| Script inside its plugin, no environment root | manifest walk-up | own lib |
| Script inside its plugin, environment root names this plugin | environment root | own lib, the same files |
| Environment root names another or older plugin | that root's lib | own lib |
| Script copied outside its plugin, environment root set | environment root | environment root, after the own-lib probe fails |
| Script copied outside its plugin, no environment root | manifest walk-up, else exit 2 | `ImportError` or `RuntimeError` |
| Neither lib holds the parser | `ImportError`; exit 2 only when the lib directory is missing | `ImportError`; `RuntimeError` when the lib directory is missing |

**Test impact**: `tests/test_frontmatter_bootstrap_foreign_root.py` runs every authored copy under `src/claude/skills/` and `.claude/skills/`. The generated plugin mirrors are not run there; all 77 generated copies, 16 each in copilot-cli, codex, cursor, and muse plus 13 in the hermes packs, are byte-identical to their sources (compared 2026-11-24 UTC), and `build_all.py --check` keeps every generated tree in sync. It covers a stale root, a root that lacks the parser, and the fallback for a copied script. It also imports each copy under Python 3.10 when a 3.10 interpreter is available, and skips that case otherwise. `tests/test_plugin_path_resolution.py` still passes (87 passed with the bootstrap test on 2026-11-24, after the 2026-11-19 amendment merged), because each script still names `CLAUDE_PLUGIN_ROOT`. The bootstrap test finds copies by their parser import and the `parents[3]` line, so a copy written in another shape is not checked.

**Trade-off**: A new skill script that imports the shared parser copies this shape; a hook keeps the boilerplate. This shape fails with exit 1 (`RuntimeError` or `ImportError`) where the boilerplate exits 2, the ADR-035 config-error code. The shape assumes a script sits four levels below its plugin root; a shallower copy raises `IndexError`.

**Out of scope**: Other skill scripts predate this amendment and carry their own bootstraps. 14 read a plugin-root variable and fall back to `parents[3]` without the parser probe (counted 2026-11-24 with claims-ledger row 16, after the 2026-11-19 amendment moved `council.py` and `sol_loop.py` to `load_skill_paths()`). That loader still reads the environment root before the script's own lib; this amendment does not change its order. A wider set puts an environment-root `lib` on `sys.path` in other ways. Most read the environment root first, so a foreign root can still shadow their imports. ADR-121's command locator is a separate shape for commands, not imports. This amendment does not change either.

## Related Decisions

- ADR-045: Framework Extraction via Plugin Marketplace (established `CLAUDE_PLUGIN_ROOT` usage)
- ADR-042: Python-First Enforcement (all new scripts in Python)
- ADR-035: Exit Code Standardization
- ADR-121: One resolver for plugin-root commands (the `lib/ptk_run.py` locator)

## References

- Claude Code hooks documentation: `hooks.md`
- Plugin marketplace distribution analysis: `.project-toolkit/analysis/claude-code-plugin-marketplaces.md`
- Issues: #1179, #1180, #1181, #1182, #1183, #1184, #1185
- Security patterns: `.gemini/styleguide.md:24-50` (Path Traversal guidance)
- Historical removed path validation reference: `.claude/hooks/Stop/invoke_skill_learning.py:66-95`
- CWE-22: [Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- CWE-426: [Untrusted Search Path](https://cwe.mitre.org/data/definitions/426.html)

## Review Evidence

- Debate log: `.project-toolkit/critique/ADR-047-debate-log.md`
- 2026-11-19 amendment: `.project-toolkit/critique/ADR-047-debate-log-4.md`
- 2026-11-24 amendment: `.project-toolkit/critique/ADR-047-debate-log-2.md` and `ADR-047-debate-log-3.md`, with `ADR-047-claims-ledger.md`
- Security review: `.project-toolkit/security/SR-002-ADR-047-plugin-mode-security-review.md`
- Analysis: `.project-toolkit/analysis/001-adr-047-plugin-mode-hook-behavior-analysis.md`

---

*Template Version: 1.0*
*Created: 2026-02-16*
*GitHub Issue: #1179*
