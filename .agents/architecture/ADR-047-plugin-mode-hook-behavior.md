# ADR-047: Plugin-Mode Hook Behavior

## Status

Proposed

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

Hooks and skill scripts resolve library imports using a standard pattern:

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

When a required directory (e.g., `.agents/`, `.agents/sessions/`) does not exist, create it with `os.makedirs(path, exist_ok=True)`. Do not skip operations due to missing directories.

### Standard Import Boilerplate

Every hook or skill script that imports from `.claude/lib/` MUST use this pattern with path validation:

```python
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
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

- **Duplication**: The 7-line import boilerplate is repeated in 37+ files. This is acceptable because the bootstrap paradox prevents extracting it (cannot import a utility before making it importable).
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
- `.claude/hooks/Stop/invoke_skill_learning.py:66-95` (_validate_path_string pattern)

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

1. Use the standard 7-line import boilerplate if importing from `.claude/lib/`
2. Use `get_project_directory()` for consumer project paths
3. **Validate all paths are within project boundary before file operations**
4. Use `os.makedirs(path, exist_ok=True)` for required directories **AFTER path validation**
5. Never gate behavior on `CLAUDE_PLUGIN_ROOT` presence
6. Test with `CLAUDE_PLUGIN_ROOT=/tmp/test python3 hook.py` to verify plugin mode
7. **Test with malicious environment variables to verify rejection** (`CLAUDE_PROJECT_DIR=../../etc`)

## Related Decisions

- ADR-045: Framework Extraction via Plugin Marketplace (established `CLAUDE_PLUGIN_ROOT` usage)
- ADR-042: Python-First Enforcement (all new scripts in Python)
- ADR-035: Exit Code Standardization

## References

- Claude Code hooks documentation: `hooks.md`
- Plugin marketplace distribution analysis: `.agents/analysis/claude-code-plugin-marketplaces.md`
- Issues: #1179, #1180, #1181, #1182, #1183, #1184, #1185
- Security patterns: `.gemini/styleguide.md:24-50` (Path Traversal guidance)
- Path validation reference: `.claude/hooks/Stop/invoke_skill_learning.py:66-95`
- CWE-22: [Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- CWE-426: [Untrusted Search Path](https://cwe.mitre.org/data/definitions/426.html)

## Review Evidence

- Debate log: `.agents/critique/ADR-047-debate-log.md`
- Security review: `.agents/security/SR-002-ADR-047-plugin-mode-security-review.md`
- Analysis: `.agents/analysis/001-adr-047-plugin-mode-hook-behavior-analysis.md`

---

*Template Version: 1.0*
*Created: 2026-02-16*
*GitHub Issue: #1179*
