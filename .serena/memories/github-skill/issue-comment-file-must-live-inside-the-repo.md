# github skill scripts refuse a comment file outside the repository root

## Symptom

`close_issue.py`, `post_issue_comment.py`, and their siblings under
`.claude/skills/github/scripts/` reject `--comment-file` when the path sits
outside the repository:

```
[FAIL] Comment file must stay under /home/richard/src/GitHub/rjmurillo/ai-agents6:
/tmp/.../scratchpad/c4309.md
```

This collides with `AGENTS.md`, which lists "Scratch in tree" under **Never**.
Writing the body to the harness scratchpad is refused by the script; writing it
into the working tree is refused by policy.

## What works

Write the body under `.git/`. It is inside the repository root, so the path
check passes, and it is not part of the tree, so no policy is broken and nothing
shows up in `git status`:

```bash
mkdir -p .git/issue-scratch
cat > .git/issue-scratch/body.md <<'EOF'
...
EOF
uv run --frozen python .claude/skills/github/scripts/issue/close_issue.py \
  --owner rjmurillo --repo ai-agents --issue 1234 \
  --reason "not planned" --comment-file .git/issue-scratch/body.md --verify-claims
```

Issue #4276 asks for the same allowance on review-thread reply bodies, which is
the identical constraint one script over. Until it lands, `.git/` scratch is the
working answer for every script in the family.

## Two argument traps in the same family

**`--reason "not planned"` must be quoted.** The value contains a space, and an
unquoted `--reason not planned` is parsed as `--reason not`, which fails with
`invalid choice: 'not' (choose from 'completed', 'not planned')`. The error names
the choices but not the quoting, so it reads as a bug in the allowed values.

**`--verify-claims` rejects any cited PR that is not merged, including one cited
as context.** A closing comment mentioning `#4017` purely as a note for whoever
lands that branch aborts the close:

```
[FAIL] Closing comment cites unverifiable artifact(s); aborting close.
cited PR #4017 is not merged on rjmurillo/ai-agents
```

The guard exists for "resolved by PR X" claims naming a phantom or unmerged PR
(issue #2481), and it cannot tell a resolution claim from an aside. Refer to the
branch by name rather than by number when the mention is contextual, or drop
`--verify-claims` and accept the weaker check.

## Also worth knowing

Argument shapes differ across the family. `new_pr.py` takes neither `--owner`
nor `--repo` nor `--output-format`; it infers the repository. `close_issue.py`
requires `--owner` and `--repo`. Run `--help` rather than copying flags from a
sibling script.
