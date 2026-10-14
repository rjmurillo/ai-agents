# Gate 5 Documentation Accuracy Procedure

`/test` Gate 5 composes `doc-accuracy` instead of keeping a documentation
checklist. `doc-accuracy` owns the phases, the issue taxonomy, and the exit
codes. This file owns only when the check runs, what is passed to it, and how
its result becomes a gate verdict.

## 1. Decide

Run the trigger with every changed path from Step 0, each as its own argument,
the diff base, and each documentation-impact effect you verified in the diff
body. Never shell-expand the paths.

`python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/test/scripts/doc_accuracy_trigger.py" --diff-base "origin/<base-branch>" --changed-path <path> --effect <name>`

If `/build` handed over a doc-impact record (see "Build handoff"), add
`--build-record <doc-impact-path>`. The record's `effects` join yours, and a
record whose `decision` was `activate` keeps this decision at `activate`, so a
signal raised at build time is never skipped here. The output echoes both in
`effects` and `build_record`. Exit `2` also covers an unreadable or malformed
record: report `VERDICT: ERROR`. No record handed over: omit the option.

Effects: `public-api`, `cli-surface`, `config-or-defaults`,
`quantitative-claim`, `behavioral-claim`, `support-or-limit`, `example-change`,
`generated-input`, `agent-behavior`. A code, build, or CI path activates the
check only through an effect, so read the diff for each one before you run the
trigger. A path the classifier cannot place, an unknown effect, and an empty
path list all activate it. Exit `2` means the classifier could not load or the
diff base was blank: report `VERDICT: ERROR`.

## 2. Skip

On `"decision": "skip"`, do not invoke `doc-accuracy`. Record
`DOC ACCURACY: SKIPPED` and quote the `reason` field verbatim.

## 3. Scan the changed documents

When `changed_documents` is not empty, invoke `Skill(skill="doc-accuracy")` and
run its incremental scan:

`python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/doc-accuracy/scripts/doc_accuracy.py" --target . --diff-base "origin/<base-branch>" --format gate`

Normalize its output and exit code with
`adapt_local_axis_verdict("doc-accuracy", output, exit_code)`, the same adapter
`/review` uses, resolved as that skill's "Path resolution" section describes. It
returns PASS, FAIL, or UNKNOWN.

## 4. Verify claims the scan cannot see

Run the behavioral and cross-document phases `doc-accuracy` defines when
`behavioral_escalation` is `required`, or is `on-findings` and step 3 reported a
finding on a changed line. Scope them to `changed_documents`.

When `coupled_documents_needed` is true no document changed, so the scan in
step 3 has nothing to inventory. Run
`python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/doc-accuracy/scripts/doc_accuracy.py" --target . --phases 1 --output-dir <dir>`
and take the documents in `<dir>/assessment.json` whose `mapped_source_files`
include a changed path. When none map, record
`DOC ACCURACY: SKIPPED - no document maps to the changed source`.

## 5. Verdict

A FAIL is `CRITICAL_FAIL`. An UNKNOWN, a `DID_NOT_RUN`, a missing report, or an
escalation you were required to run and did not is `ERROR`; none of them is ever
a PASS. A finding in a `historical_paths` entry is dated evidence: report it as
info and leave it out of the verdict. Name each `unreadable_documents` entry as
unverified, because `doc-accuracy` cannot read it. Classify each finding's
remediation by the artifact-neutral rules in the `code-qualities-assessment`
skill's `references/executable-nl-artifacts.md`; a generated copy is corrected
at its canonical source.

## Build handoff

`/build` runs the same trigger once, without `--build-record`, so it does not
audit after every edit. It passes the changed paths planned or verified so far
and each effect it verified in the diff body, then saves the JSON output as the
doc-impact record in the plan or issue handoff, at `<doc-impact-path>`. Re-run
and overwrite the record when later slices change the paths or effects. On
`"decision": "skip"` the handoff quotes the `reason` field as
`DOC ACCURACY: SKIPPED`. On `"decision": "activate"` `/build` runs the
incremental scan from step 3 on the changed documents and stops there; the
behavioral phases in step 4 stay with this gate. A missing record is not a
skip: `/build` runs the trigger first.

## Report

On activation, report this block as the gate's documentation findings:

```text
DOC ACCURACY REPORT
Activation: <reason field from the trigger>
Diff base: <diff_base field>
Phases executed: <for example 1-3 deterministic, 4 behavioral>
Deterministic scan: PASS|FAIL|UNKNOWN|NOT RUN
Behavioral and cross-document: PASS|FAIL|UNKNOWN|NOT RUN|N/A
FINDINGS:
- [SEVERITY] (file:line) claim: evidence. Remediation: correct durable claim|delete derived claim|reference canonical source|generate projection|consolidate authority
```
