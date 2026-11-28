# claude-workflow-authorization-pattern claims ledger, 2026-11-25

Claims in the retirement note added to `.project-toolkit/architecture/claude-workflow-authorization-pattern.md`. The body below the note is not re-verified: the note says it describes the state before 2026-11-25.

Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| claude.yml no longer exists | absence | `test ! -e .github/workflows/claude.yml && echo absent` | VERIFIED: absent |
| Commit 3f145f26fd (2026-11-25) deleted it | behavior | `git show --format=%cs --name-status 3f145f26fd -- .github/workflows/claude.yml \| tr '\n' ' '` | VERIFIED: 2026-11-25 D .github/workflows/claude.yml |
| Before the deletion claude.yml was the only file under .github that named the checker | behavior | `git grep -l 'test_claude_authorization' 3f145f26fd^ -- .github \| sed 's#^[^:]*:##' \| tr '\n' ' '` | VERIFIED: .github/workflows/claude.yml |
| The checker script and its test suite remain | path | `ls tests/workflows/test_claude_authorization.py tests/test_claude_authorization.py \| tr '\n' ' '` | VERIFIED: tests/test_claude_authorization.py tests/workflows/test_claude_authorization.py |
| No file under .github or lefthook.yml calls the script now | absence | `git grep -l 'test_claude_authorization' -- .github lefthook.yml \| wc -l` | VERIFIED: 0 |
| No job under .github declares an agent-* environment now (the "every other job" clause) | absence | `git grep -n -E '^\s*environment:\s*agent-' -- .github \| wc -l` | VERIFIED: 0 |
