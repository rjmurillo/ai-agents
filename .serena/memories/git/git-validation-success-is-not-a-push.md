# "Ready To Create Pull Request!" Is Emitted Before Any Push

**Atomicity**: 95%
**Category**: Git Operations
**Source**: 2026-08-02 fleet session, branch `docs/eval-fixture-provenance`

## Statement

`scripts/validation/pre_pr.py` ends by printing `RESULT: All validations passed`
and `Ready to create pull request!`. Neither line reports a push. The string is
at `pre_pr.py:330`, in the validator, and it is emitted whether or not a push
ever happens. Confirm a push landed with `git ls-remote origin refs/heads/<branch>`,
not with the exit message of whatever ran last.

## Context

The trap needs two ingredients that this repo supplies by default.

First, the pre-push hook takes roughly 11 minutes, so validation and push are
usually run as separate long-lived background shells. Second, the validator's
closing line is written in the vocabulary of the *next* step ("ready to create a
pull request") rather than its own, so it reads like a completion notice for the
whole publish workflow.

An agent holding several background shells then attributes the validator's output
to the push shell, and reports the branch as pushed. The failure is silent: there
is no error to notice, and the branch simply does not exist on the remote.

## Evidence

Measured 2026-08-02. A shell labeled as the push for `docs/eval-fixture-provenance`
completed with:

```
RESULT: All validations passed

Ready to create pull request!
```

The immediately following check returned nothing at all:

```
$ git ls-remote origin refs/heads/docs/eval-fixture-provenance
$ echo $?
0
```

Empty output, exit 0. The ref did not exist. `gh pr list` likewise showed no PR
for the branch while three sibling branches from the same batch appeared.

## Remedy

Capture the remote SHA on both sides of a push and compare against the branch:

```bash
before=$(git ls-remote origin "refs/heads/$b" | awk '{print $1}')
git push -u origin "$b"
after=$(git ls-remote origin "refs/heads/$b" | awk '{print $1}')
[ "$after" = "$(git rev-parse "$b")" ] || echo "MISMATCH"
```

Compare against `$b`, not `HEAD`. The shell running the push is often checked out
to a different branch, in which case `git rev-parse HEAD` names that branch and
the check reports a mismatch on a push that actually succeeded.

`git ls-remote` exits 0 for a ref that does not exist, so test the captured
string, never the exit code. For the same reason do not read `$?` after a
pipeline such as `git push ... | tail`: that reports the exit status of `tail`.
This is how the original failure stayed hidden. The pipeline reported exit 0
while `git push` printed `error: failed to push some refs`.

## Scope

Applies to any success message whose wording names a later step than the one that
printed it. The same shape appears in markdown lint selection, which carries its
own disclaimer at `scripts/validation/checks_tooling.py`, in `_report_selection`:

```
[WARNING] Markdown linting selected 0 of N target(s)...
This PASS means 'not linted', not 'clean'.
```

That warning exists because the mistake was already made there once. Read a
message as a claim about the emitting command only.
