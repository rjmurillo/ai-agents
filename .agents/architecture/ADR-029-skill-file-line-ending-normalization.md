# ADR-029: Skill File Line Ending Normalization

## Status

Accepted

## Date

2025-12-27

## Context

Generated `*.skill` files in `.claude/skills/` exhibit inconsistent line endings across platforms:

- **Windows developers**: CRLF line endings (`\r\n`)
- **Linux/Mac developers**: LF line endings (`\n`)
- **Generate-Skills.ps1**: Runs on different platforms, producing inconsistent output
- **Git behavior**: Reports "file changed" when only line endings differ, creating noise in git status/diff

This inconsistency creates:

1. **False positives in reviews**: Reviewers see large diffs that are only line ending changes
2. **Merge conflicts**: Same file with different line endings causes conflicts
3. **Build instability**: Skills generated in CI may differ from local builds

## Decision

**Force LF line endings for all `*.skill` files** using git attributes:

```gitattributes
# Skill Files: Line ending normalization (see ADR-019)
*.skill text eol=lf
```

This directive ensures:

- Git marks `*.skill` files as text (not binary)
- Git always checks out with LF endings (`eol=lf`)
- Git auto-converts CRLF → LF on commit
- Working tree always has LF (consistent across platforms)

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **No normalization** | Simple, no config | Inconsistent across platforms, git noise | Creates ongoing maintenance burden |
| **CRLF everywhere** | Native Windows behavior | Breaks Linux/Mac expectations, larger files | Non-standard for modern repos |
| **Developer-specific .editorconfig** | Flexible per-developer | Requires manual setup, not enforced | Doesn't prevent inconsistency |
| **LF everywhere (chosen)** | Consistent, industry standard, enforced by git | Windows devs need autocrlf=input or tool support | Best trade-off for multi-platform teams |

### Trade-offs

**Benefit**: Zero git noise from line ending differences. Skills generated on any platform are byte-identical.

**Cost**: Windows developers with `autocrlf=true` (default) may see warnings. Requires explicit git config or tool support.

**Mitigation**:
1. Generate-Skills.ps1 has `-Lf` flag for explicit LF generation
2. Git attributes are declarative - works retroactively
3. CI enforces consistency

## Consequences

### Positive

- Eliminates "phantom changes" in git status/diff
- Skills are byte-identical across platforms
- Merge conflicts reduced
- Consistent with modern repository conventions (most open-source projects use LF)

### Negative

- Windows developers may see git warnings if `core.autocrlf=true` (default)
- Requires awareness of line ending policy

### Neutral

- Adds one line to `.gitattributes`
- Requires documentation for contributors

## Implementation Notes

### .gitattributes Entry

```gitattributes
# Skill Files: Line ending normalization (see ADR-019)
*.skill text eol=lf
```

### Generate-Skills.ps1 Support

The script includes a `-Lf` flag to explicitly generate LF line endings:

```powershell
pwsh build/scripts/Generate-Skills.ps1 -Lf
```

This ensures consistency even before git normalization.

### Developer Setup (Windows)

Windows developers should set:

```bash
git config core.autocrlf input
```

This tells git to convert CRLF → LF on commit, but leave LF as-is on checkout.

### Verification

Check that a skill file has LF endings:

```bash
file .claude/skills/github/GitHub.skill
# Should show: "ASCII text, with no line terminators" or "with LF line terminators"
```

## References

- [Git Attributes Documentation](https://git-scm.com/docs/gitattributes)
- `.gitattributes` lines 125-126
- `build/scripts/Generate-Skills.ps1` (Normalize-Newlines function)

## Related ADRs

None
