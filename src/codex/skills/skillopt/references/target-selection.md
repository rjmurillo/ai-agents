# Target selection and patch authoring

Read this before you fund rollouts for a target, and again when a patch fails
to apply or the gate has no headroom.

## Confirm the defect first

A failure hypothesis written from reading a document is a guess. Running the
loop on a guess spends rollouts and invites an invented fix. Before any
rollout:

1. Find the defective rule in the target text, verbatim. If the target already
   prescribes the correct behavior and the runner did not follow it, there is
   no defect to patch. Propose no patch.
2. Find at least 2 distinct, realistic inputs that fail at baseline. One
   failure can train a fix, but it leaves no different failure to validate it.
3. Confirm the decision under test lives in the named target file. When the
   target delegates the decision to a sibling skill or file, optimize the
   owner.

Rank candidates by a verifier you can ground, a clean anchor line, and a
baseline failure. Rank them above raw usage counts. A target with no headroom
at baseline returns `REJECT_CEILING` and no candidate can pass.

## Split after baseline, before authoring

A pool of 5 or more distinct instances of one failure mode, plus 1 or 2 guard
tasks the target already handles, gives enough to split. Baseline the whole
pool, then freeze the split: failures divide between `train` and `sel`, and the
guards go to `sel`. Each side needs a real failure, or the gate is
inconclusive. Freeze before the candidate exists. The agent that designs the
pool and writes the candidate has seen every verifier, so list those tasks
under `exposed` unless a separate author wrote the `sel` side (Precondition 4
in SKILL.md).

## Author patches that apply

- An anchor is an exact, unique line copied from the target. Re-read the file
  to confirm it exists before you submit the patch.
- Editing a numbered list: renumber the affected items in the same patch.
- Inserting near a Markdown table: anchor on the last row or on the blank line
  after it, never on a middle row.
- Prefer one corrective rule over a rewritten section.

## Library-wide pass

For many skills at once, inventory every canonical skill, then optimize only
the eligible ones:

1. Classify each skill as `EVALUABLE`, `TARGETED-DEFECT-ONLY` (a confirmed
   defect with no wider eval), or `NOT-OBJECTIVELY-GATEABLE`.
2. Form cohorts of 2 to 4 skills that share a failure family and a deployment
   owner. Never group unrelated skills to share model calls.
3. Treat a bundle as atomic only when it is evaluated and deployed atomically.
   Otherwise gate and promote each skill on its own.
4. Keep the incumbent, candidate, results, pair report, and rejected proposals
   for every skill.
