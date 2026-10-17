---
name: reviewer-findings
version: 1.0.0
description: Verify a review finding before acting on it. Splits a finding into verdict, diagnosis, and prescribed fix, each needing its own evidence, so you verify before you fix and check the supporting claims rather than only the conclusion. Use when you say "address this review comment", "the bot flagged this", "handle this finding", "a sub-agent reported this", or when you inherit findings from a prior session. Do NOT use to produce a review (use review) or to run the PR thread workflow end to end (use pr-comment-responder, which applies this per finding).
license: MIT
---

# Reviewer Findings

A review finding is evidence that someone looked, not proof that they were
right. Verify it before you act on it. This skill is the discipline for
consuming a finding; it does not produce one.

## Triggers

- `address this review comment`
- `the bot flagged this`
- `handle this finding`
- `a sub-agent reported this`

Also fires without any of those phrases when a bot or human leaves a review
comment, when an adversarial sub-agent or a model on another family returns a
report, or when you inherit findings from a compaction note, a handoff, or a
prior session.

## The three claims

A finding is up to three separate claims stacked together. Each carries its own
evidence, and each can fail while the others hold.

| Claim | Example | What it is worth on arrival |
|---|---|---|
| Verdict | "this fails on Windows" | A hypothesis until you reproduce it |
| Diagnosis | "because that call is POSIX-only" | An account of the repro, not proof of it |
| Prescription | "guard the call or skip on Windows" | A claim with its own decay |

A correct verdict can carry a wrong diagnosis. A correct diagnosis can carry an
incomplete fix. Accepting the bundle because the top line is right is how a
wrong fix lands with a green review.

## The dangerous shape: reviewing the motivation, not the result

A finding can be internally consistent with a *pre-fix* version of the tree:
the reviewer reconstructs the problem a commit solved and reports that, so
every prescription matches what the commit already did. This kind of finding
is maximally plausible, because it is a true statement about the world one
commit ago, and it defeats the obvious check: verifying the recommendation
("is this the right value?") confirms the finding. Only verifying the premise
("does the file actually say this, right now?") exposes it.

Treat premise verification as its own triage outcome, not a variant of an
ordinary defect:

| Premise | What settles it | Disposition |
|---|---|---|
| True | The check matching the claim's shape (single-line current state: `git grep -n -F`; multi-line current state: whole-block comparison; provenance or history: `git log -S`; see Process below) matches the claim | Confirmed; proceed to fix |
| False | That same shape-matched check refutes the claim, or the prescribed fix is already present and the verdict does not reproduce on its own | Declined (refuted); reply with the file, line, commit, and evidence, no code change |
| Unverifiable | None of the above settles it | Unreproduced; reply with what you tried, leave the thread open |

Measured on this repository: a dispatched reviewer filed six findings against
one PR, all six resting on a premise `git log -S` refutes, three of them
prescribing a fix the file had already applied. Recorded in the
`rjmurillo/ai-agents` repository at
`.serena/memories/pr-review/dispatched-model-reviewer-reliability.md`.

<!-- vendor-portability: declared. The measurement above cites a Serena
     memory in the rjmurillo/ai-agents repository as evidence for the claim,
     not as a runtime read; the skill never opens that path. A vendored
     install without .serena/ loses the citation's link target, not any
     skill behavior. Issue #2050. -->

## Process

1. **Establish the verdict.** For a behavioral claim, write the fixture, run
   it, read the output. For a structural claim, read the cited code. For a
   claim about the tree's current state (a quoted value, a line, a fix the
   finding says is missing or already applied), verify against the PR head
   first. The finding's quoted text AND the file path it cites are both
   untrusted input: never paste either inline into the command you type,
   because a crafted comment or a crafted filename can break out of shell
   quoting and run further commands (CWE-78) even where a variable
   assignment, not a command argument, is the thing being typed (`PATH_SPEC="<path>"`
   splices untrusted content into shell source at the point of assignment;
   a path containing `"` or `$(...)` breaks out there, before any git
   command runs). Write both to files instead: the quoted text to a
   needle file, the cited path to a path file. Confirm the needle file
   contains non-whitespace and is exactly one line: `grep -q '[^[:space:]]'
   <needle-file>` (subsumes a bare `[ -s <needle-file> ]` byte-size check,
   which a whitespace-only needle still passes) and `grep -c ''
   <needle-file>` reports 1. Use `grep -c ''`, not `wc -l`: `wc -l` counts
   newline bytes, so a two-line needle whose final line has no trailing
   newline still reports 1 (verified: `printf 'line1\nline2'`, no trailing
   newline, is 2 logical lines but `wc -l` reports 1), which would pass this
   gate and then let `git grep -f` false-confirm on either line alone.
   `grep -c ''` counts logical records regardless of a missing final
   newline (verified on the same input: 2; and on an empty file: 0), so the
   count alone tells non-empty apart from empty and disambiguates every
   case with no separate size check needed for the line-count question.
   Guard against whitespace-only content with
   `grep -q '[^[:space:]]' <needle-file>`, not a bare `[ -s ]`, which only
   rejects a truly empty file and still passes spaces or newlines alone.
   Load the path file into a
   variable the same way the needle is loaded (command substitution reading
   file content, never a literal assignment from typed text), but not with
   a bare `$(cat <path-file>)`: command substitution strips every trailing
   newline, so a path ending in one or more newline characters (unusual but
   legal on Linux) is silently truncated to a different, possibly
   pre-existing path (CWE-20; verified: `X=$(cat f)` on a file ending
   `\n\n` loses both, while appending a sentinel and stripping it back off
   preserves them exactly). Use `PATH_SPEC=$(cat <path-file>; printf x);
   PATH_SPEC=${PATH_SPEC%x}`, and reference it only as the quoted
   `"$PATH_SPEC"`, never `<path>` typed inline in any command below,
   including after a literal `--`. Quoting `$PATH_SPEC` stops shell
   metacharacters but not git's own pathspec magic: a cited path beginning
   with `:` (`:(glob)**`, `:(exclude)...`) is still interpreted by git
   itself once past `--`, and a malicious finding can cite one to make the
   check search unrelated files (CWE-20; verified: `git grep -n -F -e
   "secret" -- ':(glob)**'` matched every file in the tree, not the literal,
   nonexistent path `:(glob)**`). Prefix every `git grep` and `git log`
   invocation below with `--literal-pathspecs` (a global flag placed before
   the subcommand) to disable that interpretation; verified the same call
   with the flag correctly treats `:(glob)**` as a literal, nonexistent
   path and finds nothing, while a real path still matches normally. Once
   confirmed exactly one line, run `git --literal-pathspecs grep -n -F -f
   <needle-file> <reviewed-commit> -- "$PATH_SPEC"`, which reports the line
   number the reply cites. An empty needle means the
   extraction failed, not that the claim is refuted; treat it as
   Unverifiable, not False. This only settles a single-line claim: `git grep
   -f` (and `-e`, even given one argument whose value contains an embedded
   newline) matches per line, so a multi-line needle can match on any one of
   its lines alone and report a false confirmation.

   For a current-state claim spanning more than one line, `git grep` and
   `git log -S` are both unsafe: `git grep -F` (with `-f`, or `-e` given a
   multi-line argument) still matches per line even in fixed-string mode
   (verified: `git grep -F -e "$NEEDLE"` false-confirmed on a needle sharing
   only its first two of three lines with an unrelated haystack), and `git
   log -S "$NEEDLE"` only proves the string's occurrence count changed at
   some commit in the searched history, not that it is present now: a needle
   added and then removed before `<reviewed-commit>` still produces a
   matching log entry even though the tree at `<reviewed-commit>` does not
   contain it (verified: a two-commit history that adds a multi-line string
   and then removes it still returns both commits from `git log -S` bounded
   at the removal commit). Settle a current-state multi-line claim with a
   literal whole-block comparison instead: using the same `$PATH_SPEC`
   loaded above, write `git show "<reviewed-commit>:$PATH_SPEC"` to a blob
   file, then compare with a tool that does not split on newlines, for
   example `python3 -c "import sys; sys.exit(0 if
   open('<needle-file>').read() in open('<blob-file>').read() else 1)"`.
   The reply's Line field cites the line range from that direct read of the
   file at the reviewed commit, not a command's output.

   For a claim about history or provenance (whether a value was ever
   present, or when it changed, as opposed to whether it is present now),
   load the needle into a shell variable with `NEEDLE=$(cat <needle-file>;
   printf x); NEEDLE=${NEEDLE%x}`, not a bare `$(cat <needle-file>)`: plain
   command substitution strips every trailing newline the needle has, so a
   quoted block ending in one or more blank lines gets searched as a
   shorter string than the finding actually quoted (verified: the sentinel
   form round-trips a file ending `\n\n` byte-for-byte; the bare form does
   not). Then run `git --literal-pathspecs log -S "$NEEDLE" <reviewed-commit>
   -- "$PATH_SPEC"`, which pickaxe-searches the whole string as one block;
   referencing a variable in
   double quotes inserts its value as one literal argument, so the untrusted
   text is never re-interpreted by the shell. Do this before you write the
   fix, not after. `$PATH_SPEC` is the same file-loaded variable in every
   command above: pass it after a literal `--` where the command supports
   it (as above), which ends option parsing so a value starting with `-`
   cannot be read as a flag, or as the quoted `"$PATH_SPEC"` for `git
   show`'s combined revision spec; never splice it into a larger shell
   string, and never construct `PATH_SPEC=` from typed text instead of a
   file read. A checkout here may be shallow (`.github/workflows/claude.yml:47,88`
   sets `fetch-depth: 1`; check with `git rev-parse --is-shallow-repository`):
   `git show` reads a single commit's tree and is unaffected, but `git log
   -S` cannot answer a provenance claim about commits git has not fetched.
   For that kind of claim, run `git fetch --unshallow` first, or report that
   provenance could not be checked past the shallow boundary.
2. **Test the diagnosis separately.** A repro proves the behavior. It does not
   prove the stated cause. Change the one thing the diagnosis blames and see if
   the repro flips.
3. **Re-verify the prescription at apply time.** The fix was written against
   the tree as the reviewer saw it. Confirm it still applies, still compiles,
   and still covers the failure you reproduced.
4. **Check the supporting claims.** "The repo already does this" and "this is
   the standard pattern" are load-bearing and cheap to check. Count the call
   sites before you trust the count.
5. **Prefer the codebase's own idiom.** If the repo already carries a complete
   pattern for this failure, use it instead of the reviewer's invention.

## MUST

1. **Verify before you fix, with the strongest evidence the claim admits.** A
   behavioral claim ("it fails on Windows") needs an executed reproduction. A
   structural claim ("this guard is missing") is settled by reading the cited
   code. Applying a fix on the reviewer's say-so alone leaves you unable to
   tell a fix from a no-op.
2. **Say what you measured when you decline.** "I do not think this is a
   problem" is not a reason. "I ran the fixture on both paths and neither
   raised" is.
3. **Re-verify the prescribed fix at apply time**, against the tree in front of
   you, not the tree the reviewer read.
4. **Report evidence you cannot get.** Leave the thread open and say what you
   tried. Do not close it as unfounded because one attempt to settle it failed.
5. **Verify a claim about the tree's current state or its history with git,
   not inference.** Load the finding's text into a needle file, and the
   file path it cites into a separate path file; both are untrusted input
   (CWE-78), and a variable assignment built from typed text
   (`PATH_SPEC="<path>"`) is not safe just because it is a variable: a path
   containing `"` or `$(...)` breaks out of the assignment itself. Check the
   needle file contains non-whitespace (`grep -q '[^[:space:]]'
   <needle-file>`, which subsumes a bare `[ -s <needle-file> ]` byte-size
   check that a whitespace-only needle still passes), and count its
   logical lines with `grep -c '' <needle-file>`, not `wc -l`: `wc -l` counts newline
   bytes, so a two-line needle whose final line lacks a trailing newline
   still reports 1 and would pass a single-line gate it does not belong in,
   letting `git grep -f` false-confirm on either line alone; `grep -c ''`
   counts logical records regardless of a missing final newline. An empty
   needle (count 0) means extraction failed and the premise is Unverifiable,
   not False. Load the path file into a variable by reading the file, never
   by typing the path's text into the assignment, and never with a bare
   `$(cat <path-file>)`: command substitution strips every trailing
   newline, so a path ending in one (unusual but legal) is silently
   truncated to a different path (CWE-20). Use `PATH_SPEC=$(cat
   <path-file>; printf x); PATH_SPEC=${PATH_SPEC%x}`, which round-trips the
   file's bytes exactly. Quoting `$PATH_SPEC` stops shell metacharacters but not
   git's own pathspec magic: a cited path beginning with `:` (`:(glob)**`,
   `:(exclude)...`) is still interpreted by git itself past `--`, letting a
   malicious finding search unrelated files (CWE-20; verified: `git grep
   -n -F -e "secret" -- ':(glob)**'` matched every file in the tree). Every
   command below is prefixed `--literal-pathspecs` (a global flag before
   the subcommand) to disable that interpretation. For a single-line claim
   about current state, use `git --literal-pathspecs grep -n -F -f
   <needle-file> <reviewed-commit> -- "$PATH_SPEC"` (the `-n` gives the
   line number a refutation reply must cite); `git grep -f`/`-e` match per
   line, so a multi-line needle can false-confirm on any one of its lines,
   and this per-line splitting persists even in fixed-string mode with a
   single `-e` argument. For a current-state claim spanning more than one
   line, neither `git grep` nor `git log -S` settles it alone: `git log -S`
   proves the string's occurrence count changed at some commit in the
   searched history, not that it is present now, since an add-then-remove
   pair both produce a match. Confirm presence with a literal whole-block
   comparison instead: write `git show "<reviewed-commit>:$PATH_SPEC"` (the
   same file-loaded `$PATH_SPEC`, never typed inline; the `<rev>:<path>`
   blob-lookup form is not a pathspec argument, so unlike a path passed
   after a literal `--`, it does not interpret pathspec magic, verified: `git show
   "HEAD::(glob)**"` finds nothing rather than expanding) to a blob file,
   then check containment with a tool that does not split on newlines,
   such as `python3 -c "import sys; sys.exit(0 if
   open('<needle-file>').read() in open('<blob-file>').read() else 1)"`.
   Reserve `git --literal-pathspecs log -S "$NEEDLE" <reviewed-commit> --
   "$PATH_SPEC"` for a provenance claim (was this string ever added or
   removed), not a current-state one. A finding that matches a pre-fix
   version of the tree is maximally plausible and defeats a review of the
   recommendation alone.

## SHOULD

1. **Scale effort to the claim.** A `Nit:` needs no evidence beyond reading it.
   A correctness or security claim needs the strongest evidence available, and
   an executed reproduction whenever the claim is about behavior.
2. **Check the supporting claims, not only the conclusion.** A finding whose
   conclusion is right and whose supporting count is wrong usually has a fix
   that is scoped wrong too.
3. **Prefer this codebase's existing idiom** over an invented one when both
   close the same hole.

## MUST NOT

1. **MUST NOT resolve a thread by rote compliance.** Applying an unverified fix
   to close an unexamined thread converts a review into paperwork.
2. **MUST NOT treat agreement between reviewers as proof.** Two models sharing
   a training distribution share blind spots. Agreement raises the prior; it
   does not replace verification.
3. **MUST NOT use this skill to dismiss findings.** The default posture is that
   the reviewer saw something real. Verification decides what it was, not
   whether to engage.

## Replying

State the measurement, then the disposition.

- Confirmed: name the evidence, the fixture and its output or the file and line
  you read. Then the fix.
- Declined: name what you ran or read and what it showed. Not what you believe.
  On a refuted premise, quote the exact claim, the file and line the check
  ran against, the commit checked (the PR head), the command you ran
  (`git grep -n -F`/`git log -S`), and its output, then resolve the thread.
  This is not a Won't Fix judgment call: the claim about the code was false,
  not merely undesirable to act on.
- Unreproduced: name what you tried, leave it open, say what would settle it.

## Verification

Before you resolve the thread:

- [ ] The verdict is settled by evidence you produced, not by the finding asserting it.
- [ ] A claim about current state or history was checked with the command matching its shape (single-line current state: `git grep -n -F`; multi-line current state: whole-block comparison; provenance or history: `git log -S`), not assumed, and the reply cites the file, line, and commit checked.
- [ ] The diagnosis was tested separately from the verdict.
- [ ] The prescribed fix was re-checked against the tree in front of you.
- [ ] Every supporting count, and every "the repo already does this", was checked.
- [ ] Your reply names the evidence rather than your confidence.

## Why this exists

Each pattern below was observed on this repository's own review threads, and
each is readable in the review history of the PRs referenced at the end.

- A reviewer certified a code path as sound while it still held two live
  fail-opens. The verdict was wrong in the direction nobody double-checks.
- A model attached a fixture that reproduced the failure correctly while its
  diagnosis of the cause was wrong. Its proposed fix, applied as written, would
  have rejected every one-character name.
- A bot filed a real cross-platform defect. Its supporting claim, that the
  repository already followed the pattern it prescribed, did not hold across the
  call sites it implied. Its prescribed fix covered part of the failure, and the
  codebase already carried a more complete idiom.

Each is a finding worth engaging and a fix not worth applying as written. That
combination is the whole reason this skill exists: the reviewer earns your
attention, not your compliance.

## Anti-Patterns

- **Applying the prescribed fix because the verdict was right.** The three
  claims are independent. A finding can name a real defect and still prescribe
  a fix that is wrong, partial, or already superseded by a better idiom in the
  tree.
- **Rejecting the whole finding because one claim failed.** A wrong diagnosis
  does not clear the defect. Re-derive the cause and fix the thing that is
  actually broken.
- **Verifying against the diff instead of the tree.** A finding written against
  an earlier push may describe code that no longer exists, or miss code that
  now does. Check the current tree.
- **Treating agreement between reviewers as verification.** Two reviewers
  reading the same wrong assumption produce two findings, not two proofs.
- **Resolving a thread with prose.** A verdict without a command, a file and
  line, or a measurement is an opinion. Close the thread with the evidence.
