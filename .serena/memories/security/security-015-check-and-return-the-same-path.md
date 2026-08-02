# Skill-security-015: Check and Return the Same Path

**Statement**: A path guard must return the exact path it containment-checked.
Normalising between the check and the return lets it vet one file and hand back
another.

**Context**: `os.path.normpath` is often reached for as the "safe" way to clean
a path without following symlinks, on the theory that `resolve()` is too eager.
The opposite risk is real: `normpath` collapses `..` textually, which changes
which file the path names whenever a symlink sits above the `..`.

**Evidence**: Measured in `scripts/validation/portability_common.py` on
2026-08-01 (PR #4233). Given `link/../victim.json` where `link` points at
`target/a`, the containment test resolved through the link and vetted
`target/a/victim.json`, while `normpath` collapsed the same input to
`victim.json`. Same file: False. The collapse also consumed the link, so the
downstream symlink refusal had nothing left to catch and returned False. A code
comment above the call asserted this arrangement was safe. The comment was
wrong and had shipped.

**Atomicity**: 93% | **Impact**: 8/10

## Pattern

```python
# WRONG: the check and the return disagree once a symlink sits above the `..`
candidate = (root / user_path)
if not _contained(candidate.resolve(), root):
    return None
return Path(os.path.normpath(candidate))   # different file

# RIGHT: vet it, then hand back the identical object
candidate = (root / user_path)
if not _contained(candidate.resolve(), root):
    return None
return candidate                            # link still visible downstream
```

Returning the candidate whole keeps every symlink in the path where a later
guard can still see it. Any transformation applied after the check, including
`normpath`, `os.path.abspath`, or manual `..` stripping, reopens the gap.

## Two general rules this instance produced

**A comment asserting a safety property is a claim, not a proof.** Probe it like
any other claim. This one had been reviewed and merged.

**Check the argument order before writing the probe.** The first attempt at
reproducing this called `refuse_symlinked_baseline(baseline, root)` when the
signature is `(repo_root, baseline_path)`, and returned a confident but
meaningless True. A probe with swapped arguments looks exactly like a passing
guard.

## Related

- `.serena/memories/security/security-path-anchoring-pattern.md` covers
  anchoring the path before resolving. This memory covers the separate question
  of what you may do to it afterwards.
- `scripts/validation/portability_baseline.py`: `_linked_component`,
  `_escaping_parent`, `refuse_symlinked_baseline`
- `tests/validation/test_portability_baseline_destination.py`
