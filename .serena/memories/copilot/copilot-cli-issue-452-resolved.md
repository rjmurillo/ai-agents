# GitHub Copilot CLI Issue #452 Resolution

## Context

GitHub Copilot CLI issue #452 ("User-level agents not loaded") has been resolved upstream. This memory documents the cleanup of outdated workaround documentation from the repository.

## References Removed

### Session: 2026-01-18-session-01

**Files Updated:**

1. **AGENTS.md:512**
   - Removed note: "Copilot CLI global installation has a known issue. Use per-repository installation."
   
2. **docs/installation.md:131-136**
   - Removed entire "GitHub Copilot CLI Global Installation" troubleshooting section
   - Section contained issue link and workaround instructions

3. **.agents/planning/cva-install-scripts.md:436-440**
   - Removed `KnownBug` configuration block from Copilot platform definition
   - Cleaned up planning artifact to reflect current state

## Search Pattern Used

```regex
github\.com/github/copilot-cli/issues/452
```

## Impact

Users can now install Copilot CLI custom agents globally without requiring repository-level workarounds.

## Related

- PR: #976
- Commit: 70be42e1
- Issue: https://github.com/github/copilot-cli/issues/452 (resolved)

## Lessons

When upstream issues are resolved:
1. Search for all references (documentation, code comments, configuration)
2. Remove workaround instructions to prevent user confusion
3. Update planning artifacts to reflect current state
4. Verify no other references exist using comprehensive grep patterns
