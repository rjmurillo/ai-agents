# 182 findings, 21 real: repairing memories the ADR-042 migration broke

Session 3629. Branch `fix/memory-stale-script-refs`. Twenty reference repairs
across fifteen memory files, one decision memory, no code.

- Issue: #3629
- Starting commit: `b6b33f3963`
- Artifacts: fifteen edited files under `.serena/memories/`, plus
  `.serena/memories/decision-orphan-ref-scope-serena-memories.md`

## What this was

ADR-042 migrated this repository from PowerShell to Python. The scripts moved.
The memories that told future sessions to run those scripts did not. A memory
that says "Run `scripts/Validate-PrePR.ps1` before every PR" is worse than no
memory: a future session follows it, the file is not there, and the session
spends its first minutes debugging the instruction instead of the task.

The orphan-ref validator can find these. Pointed at `.serena/memories` it
returned `CRITICAL_FAIL` with 182 findings across 877 files.

## The number was wrong by roughly a factor of ten

182 findings split into 161 `skill_name` and 21 `script_path`. The two halves
are unrelated populations and only one of them is a real problem.

I sampled fourteen distinct files from the `skill_name` half. Zero were skill
references. The detector treats any backticked kebab-case token as a skill name,
so it caught mypy error codes (`arg-type`, `return-value`), model identifiers
(`gpt-4o-mini`), a jq construct (`if-then-else`), a GitHub Actions runner label
(`ubuntu-latest`), a bot login, and a YAML frontmatter field name. The single
largest contributor was a file about GitHub topic strings, which are kebab-case
by definition. It produced 24 findings and contains no skill references at all.

That detector is sound on its default targets, which are plugin manifests and
spec files where a backticked kebab-case token really is a skill name. It is not
sound on prose. `.serena/memories` is prose.

The available shortcut was to suppress the 161 and report the corpus clean. That
would have been the dishonest fix: it makes a scanner quiet without making a
single memory more correct, and it destroys the signal for whoever later fixes
the detector's scope. No suppressions were added. The finding was written up
instead, so the next person to run this scan does not re-derive it or act on the
inflated number.

## Failure mode classification

Primary: Failure Mode #4, False Completion Markers
(`.agents/governance/FAILURE-MODES.md`). While filling in the session log I
marked five `sessionEnd` requirements `complete: true` with the evidence string
`"PENDING"`. That is the textbook shape: a completion marker asserting work that
had not happened. It never reached a commit.
`scripts/validate_session_json.py` rejected it as an evidence contradiction,
which is the gate working as designed.

Primary by impact: Failure Mode #9, Confident-Incorrectness Recurrence. Five
instances. Two were caught by self-check before review. Three survived my own
verification and were caught only by an adversarial reviewer on a second model
family, and all three were confident negative assertions built on a partial
search. None reached a commit. The section below covers them, because they are
the substance of this session rather than a footnote to it.

## The two near-misses

**A successor mapped by name instead of by content.** Matching
`Invoke-PRMaintenance.ps1` on its name pattern pointed at
`scripts/pr_maintenance/maintenance.py`. Plausible, and wrong. The memory citing
that script cited it for a specific function, `Get-BotAuthorInfo`. Searching for
the function instead of the filename found `get_bot_author_info` at line 70 of
`scripts/invoke_pr_maintenance.py`, a different file. Had the name-based mapping
shipped, the memory would have kept pointing a reader at a file that exists and
does not contain what the memory promises. That is a worse failure than the
broken path it replaced, because it looks correct.

The rule that came out of it: map a successor by the content the citation
depends on, not by the resemblance of its name.

**A historical record rewritten.** One memory records the files PR #795
committed. On the first pass I rewrote that list to the current Python name. That
PR committed a PowerShell file. Rewriting the record makes it assert something
that never happened, and any future reader auditing that PR against the memory
finds a contradiction with no way to tell which side is wrong.

This produced the editorial policy the rest of the session ran on. A memory
sentence is either a current-tense directive or a historical record. Directives
get repointed to the live path, because their whole value is that following them
works. Historical records keep the original name and gain the successor in
parentheses. The parenthetical form was not invented here; `(removed)` was
already the house convention in these same files.

Of twenty references, twelve were directives and repointed. Eight were history
and annotated. The twelve remaining `script_path` findings after the fix are
exactly those annotations: intentional, and left visible rather than suppressed.

## What did not survive the migration

Six PowerShell functions were cited across the memories. Five survived the
migration in some form. Only `Invoke-CopilotSynthesis` did not, and even there the
classifier that sets `requiresSynthesis` survives; the collect, generate, and post
workflow is what was dropped. That citation is marked specification-only. Saying
"this was specified and never built" is more useful to a future session than a link
to something adjacent, but it is only useful when it is true, which is the subject
of the next section.

The Pester test suite, runner, and workflow are retired: no `*.Tests.ps1` under
`tests/`, no `scripts/tests/`, no Pester workflow, and the reusable workflows pass
`enable-pester: false`. Dormant support remains in
`.github/actions/setup-code-env/action.yml`, which still accepts an `enable-pester`
input. Nothing enables it. The memory says exactly that, while still naming the dead
paths so the historical record survives.

## What the adversarial review caught

The change went to a reviewer on a different model family before it was committed.
It came back with five blocking findings. Three of them were the same mistake.

I had asserted three negatives: that the comment-lifecycle helpers were not ported,
that derivative-PR detection was not ported, and that `Invoke-CopilotSynthesis` had
no successor. I reached all three by searching `scripts/` and
`scripts/github_core/`. The implementations were in
`.claude/skills/github/scripts/pr/get_unaddressed_comments.py` and
`.github/scripts/invoke_pr_maintenance.py`. I had never looked in either tree.

This is worse than the stale reference it replaced. A broken path tells the reader
to go find the truth. A confident "this was never built" tells the reader to stop
looking, and it is the kind of claim a future session will act on without
re-checking. The migration moved things across trees, not just across extensions,
so a search of one tree cannot support a claim about the whole repository.

The rule: asserting a negative requires an exhaustive search. Repointing a path
requires only a targeted one. The two are not the same amount of work, and I
priced them the same.

The other two blocking findings were half-finished repoints. I changed
`scripts/Validate-PrePR.ps1` to `scripts/validation/pre_pr.py` and left `-Quick`,
`-CI`, `-Parallel`, and a `pwsh` invocation in the surrounding prose. The path
resolved and every command in the memory still failed:
`pre_pr.py -Quick` exits 2, and the real flag is `--quick`. Two memories also kept
prescribing `Validate-*.ps1` layouts and mandatory Pester suites in sections a few
lines below the one I had repointed.

Repointing a reference means making the instruction work, not making the path
resolve. The unit of repair is the paragraph, not the token.

## The second review round found four more, and one was my own measurement

I sent the corrections back for a second round on the same reviewer. It confirmed
every line number I now cite and found four further blocking problems, all of them
in prose I had left alone because it sat next to the line I was fixing.

The validation-runner memory claimed the runner is fail-fast. It is not:
`run_all_validations` in `scripts/validation/pre_pr_sequence.py` issues 35
sequential `run_validation` calls with no early exit. It listed
`.githooks/pre-commit` and `.agents/SHIFT-LEFT.md` as related files; neither has
existed since lefthook replaced the `.githooks/` layout. The SHA-pinning memory
cited the same dead hook path. The script-placement convention said validators
belong only under `scripts/`, while six live under `build/scripts/`. And I had
introduced a fresh false claim myself: repointing generation at
`build/generate_agents.py` left an adjacent output list naming `src/claude/`,
which that generator does not produce (its allowlist at lines 269-272 is
`src/copilot-cli/agents` and `src/vs-code-agents`).

Same failure shape as round one, one level out. In round one I fixed the token and
left the paragraph. In round two I fixed the paragraph and left the section.

The measurement error was worse, because it was mine and it was invisible. I had
measured the "pristine baseline" with `git stash push -- .serena/memories`, which
does not stash untracked files. My own new decision memory, which contributes 18
`skill_name` findings, was sitting in the tree during the baseline scan. Every
before-and-after figure in both artifacts was computed against a baseline that
already contained part of the change. The real baseline is 182 findings, not 200.
The honest delta is that `skill_name` went **up** 161 to 183 and `script_path`
went down 21 to 14, not the near-flat 179 to 180 I had reported.

A baseline you measure after you have started working is not a baseline. `git
stash push -- <path>` needs `--include-untracked`, or the new files moved aside by
hand, before the number means anything. I reported a verified figure twice and it
was wrong both times, in a document whose entire purpose is to stop someone
trusting an unverified number.

## The uncomfortable part

The new decision memory contributes 18 `skill_name` findings on its own, 15 from
its list of false-positive examples and three more where the closing section
repeats three of them: writing down `arg-type` and `gpt-4o-mini` as things the
detector wrongly flags causes the detector to wrongly
flag them again. Across the whole repair the `skill_name` count rose 161 to 183:
20 from this file, plus one each from two paragraphs I rewrote to be accurate
(`action-pin-policy`, `enable-pester`). Writing true prose costs findings under
this detector. `script_path` went 21 to 14: nine retired, two added deliberately
because the corpus now records which tooling is dead.

The memory says so. Disguising the examples to keep the count flat would have
been the same dishonesty as the suppression, in a smaller package, and it would
have thrown away the cleanest evidence available that the detector matches on
token shape and reads no context.

## What generalises

- An aggregate `CRITICAL_FAIL` is a prompt to look, not a count to act on. Split
  findings by kind and sample each population before believing the total.
- A validator calibrated for structured targets will produce noise on prose. Its
  verdict is only as scoped as its default target list.
- Suppressing a false positive and fixing a detector's scope are different work.
  Doing the first makes the second harder, because the evidence is gone.
- `.serena/memories` is not gated by CI. That makes reader correctness the only
  thing worth optimising for, and makes validator silence worth nothing.
- Asserting that something does not exist costs more evidence than asserting where
  it moved to. A negative needs a search of every tree that could hold it. Three
  claims here failed because one tree was searched and the answer lived in another.
- Repointing a reference is done when the instruction works, not when the path
  resolves. A repointed script name sitting above unchanged PowerShell flags is a
  reference that looks repaired and still fails on first use.
- Numbers copied from an earlier scan go stale as soon as the corpus moves. Re-run
  the measurement against the state being shipped and label it with the commit,
  rather than carrying forward a figure from the start of the session.
