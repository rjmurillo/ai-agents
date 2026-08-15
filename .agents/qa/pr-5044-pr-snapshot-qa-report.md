# QA Report: PR #5044 - Immutable PR Snapshot

qaCommit: 5084fa3aacf6c0ac2e214591fefe850c4e378fcb

## Test Execution

```bash
uv run pytest tests/test_pr_snapshot.py -q
```

**Result**: 58 passed in 1.79s

## Test Coverage

### Unit Tests (34 tests)
- Input validation: owner, repo, SHA format validation
- Exit code contracts: ADR-035 compliance (0=OK, 1=verify, 2=config, 3=external, 4=auth)
- PrIdentity serialization roundtrip
- resolve_pr_identity: same-repo, fork rejection, auth failure, not found, invalid SHA, missing gh
- check_staleness: unchanged, head change, base branch change, repo transfer, network failure, auth propagation
- Git env sanitization: GIT_DIR stripped, GIT_WORK_TREE stripped, GIT_CONFIG_ prefix stripped, forced values
- CLI: missing identity file, full workflow, auth error exit code

### Integration Tests (24 tests)
- Real Git capture: basic file changes
- Rename detection via NUL-delimited diff
- Delete detection
- Binary file handling
- Unicode path handling (NUL delimiter)
- Newline in path handling (NUL delimiter)
- Shallow repository rejection (VerifyError)
- No hooks execution (core.hooksPath=/dev/null)
- No submodule initialization (protocol.file.allow=never, submodule.recurse=false)
- Caller checkout unchanged verification (clean and dirty)
- Scanner invocation with missing script (ConfigError)
- Cross-repository rejection (VerifyError)
- Full capture end-to-end (worktree creation, file content, changed paths, cleanup)
- Full capture verifies non-shallow result

## Security Posture

- Git environment fully sanitized (GIT_DIR, GIT_WORK_TREE, GIT_CONFIG_*, all denied)
- GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL=/dev/null, GIT_CONFIG_SYSTEM=/dev/null
- core.hooksPath=/dev/null (no hook execution)
- core.fsmonitor=false (no fsmonitor execution)
- protocol.file.allow=never (no file:// access from untrusted content)
- transfer.fsckObjects=true (verify fetched objects)
- submodule.recurse=false (no submodule init)
- Input validation: owner/repo regex, SHA format check
- Cross-repository (fork) rejection at resolve time
- Full fetch (no --depth, no --filter) with shallow rejection

## Acceptance Criteria Coverage

| Criterion | Status |
|-----------|--------|
| Capture owner, repo, PR number, head SHA, base SHA, base branch | PASS |
| Fetch exact objects into isolated temporary storage | PASS |
| Verify fetched object IDs and reject shallow/partial | PASS |
| NUL-delimited changed paths (renames, deletes, binary, Unicode, newline) | PASS |
| Run existing scanner against snapshot (--run-scanner flag) | PASS |
| Treat content as untrusted (no hooks, scripts, filters, submodules) | PASS |
| Never execute target scripts, tests, filters, submodules, hooks | PASS |
| Recheck PR identity before publishing (head, base, repo, branch) | PASS |
| Fail closed for auth, quota, transport, fetch, verification | PASS |
| Prove caller checkout unchanged (--verify-caller flag) | PASS |

## Verdict

PASS - All acceptance criteria addressed. Implementation in canonical location
(.claude/skills/doc-accuracy/scripts/) with mirror regenerated.
