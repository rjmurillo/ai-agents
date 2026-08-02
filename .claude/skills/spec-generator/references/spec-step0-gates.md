#### Step 0 gate logic

<!-- vendor-portability: declared. Extracted from spec-generator/SKILL.md, which carries the same declaration. Names upstream-only paths because it documents the upstream gate: scripts/redact_secrets.py and scripts/metrics_writer.py are the runners, .agents/metrics/STEP-0-METRICS.md and .agents/dictionaries/spec-entity-aliases.json are consumer-workspace artifacts the gate writes and reads, and .claude/commands/spec.md, .claude/rules/secret-redaction.md, .claude/skills/memory/SKILL.md, and docs/spec-quality/hedge-phrases.md are contributor-scoped references in the rjmurillo/ai-agents repository. Issue #2050. -->

**Pass criteria** (all must be true):

1. All six fields have non-empty answers.
2. No answer contains a hedge phrase from the canonical list below.
3. Q1 passes the aspirational test.
4. Q3 passes the specificity test.
5. Q5 passes the speculative test.

**Canonical hedge phrase list** (a mix of multi-word phrases and a few unambiguous single-word entries `probably`, `eventually`, `someday`, all of which read as hedges in standard English. Case-insensitive word-boundary match: `\bphrase\b`. The hyphenated technical term `eventually-consistent` is exempted via a suffix-table lookup in `step0_parser.py:HEDGE_TECHNICAL_SUFFIXES`. Applied to author answers, not to system prompts or quoted instruction text):

| Phrase | Why it hedges |
|---|---|
| `would be nice` | aspirational |
| `would be useful` | aspirational |
| `would be helpful` | aspirational |
| `we believe` | belief, not observation |
| `we expect` | prediction, not observation |
| `we anticipate` | prediction, not observation |
| `we predict` | prediction, not observation |
| `we hope` | aspiration |
| `we assume` | assumption, not evidence |
| `stakeholders want` | unnamed audience |
| `users want` | unnamed audience |
| `customers want` | unnamed audience |
| `should we` | self-questioning, not commitment |
| `might be useful` | speculation |
| `might be needed` | speculation |
| `could be useful` | speculation |
| `probably` | hedging (single word, but unambiguous) |
| `eventually` | indefinite future |
| `someday` | indefinite future |
| `down the road` | indefinite future |
| `nice to have` | low-priority aspiration |
<!-- step0:hedge-table-end -->

This table in `.claude/commands/spec.md` is the canonical source for the blocklist. The Copilot-side mirror at `src/copilot-cli/skills/spec/SKILL.md` MUST keep the Step 0 block byte-identical; `tests/commands/test_spec_step0.py::test_step0_block_identical` enforces that parity. A public, annotated mirror with the RFC 2119 exemptions, the technical-suffix exemption table, and a "how to extend the list" section is published at `docs/spec-quality/hedge-phrases.md`. Edit this table first; update the Copilot-side mirror and the public mirror in the same commit.

Single words `should`, `might`, `could` are NOT hedges in this list. They conflict with RFC 2119 requirement language and produce false positives.

**Operational test for Q1 "aspirational"** (any one condition makes Q1 aspirational, triggering H3):

1. The answer names fewer than three specific requesters (people, teams, systems, or data sources). Q1 explicitly asks for three or more. A single named requester is not enough; either name three or document the deferral and re-invoke when the demand surfaces from more sources.
2. The answer uses future tense or conditional mood about demand existence (`would want`, `if customers start`, `when we have`, `would be useful`).
3. The answer is a generic category (`users in general`, `engineers`, `the team`, `stakeholders`, `developers`).

**Operational test for Q3 "specific"** (the answer must satisfy at least one):

1. A named individual (`Alice on the Payments team`).
2. A named team (`the Bleu/Delos rotation`, `the SRE on-call`).
3. A uniquely identified system or component with a version, environment, or instance qualifier (`the auth service in prod-east`, `the GraphQL pagination in get_pr_review_threads.py`).

Generic categories fail this test.

**Operational test for Q5 "speculative"** (Q5 is speculative if all three are absent. Any one of the three present prevents the halt):

1. The answer contains a direct quote (text in `"..."` or fenced block) from a ticket, message, comment, log, or document.
2. The answer cites a metric, log entry, file path, commit SHA, PR number, or named artifact.
3. The answer names a specific person, team, or system that described the problem.

**Halt triggers** (any one fires the halt):

| ID | Trigger |
|---|---|
| H1 | Any answer contains a hedge phrase from the canonical list. |
| H2 | Q5 fails the speculative test. |
| H3 | Q1 fails the aspirational test. |
| H4 | Q3 fails the specificity test. |
| H5 | Fewer than six questions answered (partial completion). |

When any trigger fires, halt and do not proceed to Step 1.

**Halt emission format** (machine-readable; every halt MUST emit a fenced code block with info-string `step0-halt` containing five `key: value` lines):

````
```step0-halt
trigger: H3
question: Q1 Demand Reality
answer: "users would want this"
test_failed: aspirational test condition 2 (future-tense `would want`)
deferral: Re-invoke /spec after naming three or more specific requesters by name.
```
````

The five fields are:

1. `trigger`: `H1`, `H2`, `H3`, `H4`, or `H5`.
2. `question`: number and label that failed (`Q3 Desperate Specificity`).
3. `answer`: the author's answer verbatim (or the matched hedge phrase quoted) on a single line; multi-line answers fold to one line with `\n` escapes.
4. `test_failed`: name the rule that was violated (e.g., `Q3 specificity test conditions 1, 2, 3 all failed`).
5. `deferral`: a single-line instruction telling the author what to do.

**Redaction pre-emit (BLOCKING)**: the `answer` field carries the author's words verbatim, and the emitted block lands in git history (PR descriptions, session logs, and the `.agents/metrics/STEP-0-METRICS.md` tally). An author answer such as `Alice@corp on prod-east-12.internal blocked on Bearer abc...` would otherwise disclose a credential, email, or internal hostname for the life of the history (CWE-209 information exposure through a diagnostic message, CWE-532 sensitive data in a log). Before emitting the `step0-halt` block, run the `answer` field through the redactor and emit the redacted form:

```bash
python3 scripts/redact_secrets.py <file>      # or pipe the answer text on stdin
```
<!-- vendor-portability-exec: scripts/redact_secrets.py -->

In Python: `from redact_secrets import redact; redact(answer).text`. Matched token shapes (private keys, GitHub/Stripe/AWS/Slack tokens, JWTs, `Bearer` headers, emails, hex secrets of 32 or more chars) become `` `[redacted: <reason>]` ``. Redaction is a backstop, not a license to collect secrets: do not paste live credentials into Step 0 answers. The full policy is `.claude/rules/secret-redaction.md`; the redactor is `scripts/redact_secrets.py`.

#### Script and state resolution (consumer-repo safe)

This skill names helper scripts and data files by toolkit-relative paths (`scripts/redact_secrets.py`, `scripts/metrics_writer.py`, `.agents/dictionaries/spec-entity-aliases.json`). Those paths exist when `/spec` runs inside the toolkit's own repo. When the skill runs from an installed plugin in a consumer repo, they do not. Resolve every helper script and data file with this order before invoking it.

**Helper scripts** (`redact_secrets.py`, `metrics_writer.py`). Resolve in order:

1. `<skill_dir>/scripts/<name>.py`, where `<skill_dir>` is the "Base directory for this skill" the harness prints at skill load (installed-plugin mode). The skill bundle ships byte-identical copies of both scripts under `scripts/`.
2. `scripts/<name>.py` relative to the current working directory only after confirming the current repo is the toolkit source checkout (toolkit-dev mode). Never prefer a consumer repo's `scripts/<name>.py` over the bundled vetted helper.

For the BLOCKING `redact_secrets.py`: if neither path resolves, FAIL loudly. Emit an error naming both paths tried and HALT the step. Do NOT emit the `step0-halt` block (or any field carrying author free-text) with redaction skipped; a silently-skipped redactor is the CWE-209/CWE-532 disclosure this step exists to prevent. `metrics_writer.py` is non-blocking: if neither path resolves, emit a coverage note and continue without the tally.

**`metrics_writer.py` bundled-copy caveat.** The writer sets `_PROJECT_DIR = Path(__file__).resolve().parents[1]`. In the toolkit repo that resolves to the repo root; in the bundled copy at `<skill_dir>/scripts/metrics_writer.py` it resolves to `<skill_dir>`. `_PROJECT_DIR` only anchors an in-process `safe_append_tally()` call when the caller omits `base_dir`. To make the bundled copy write to the consumer's state root, either invoke the script from the consumer repo so its CLI entrypoint validates the tally path under the current working directory, or call `safe_append_tally(..., base_dir=<consumer repo root>)` in process. Never rely on the implicit `_PROJECT_DIR` anchor from the bundled copy.

**Data files** (`spec-entity-aliases.json`). Resolve in order:

1. `.agents/dictionaries/spec-entity-aliases.json` relative to the current working directory (toolkit-dev or consumer-with-state mode).
2. `<skill_dir>/data/spec-entity-aliases.json` (installed-plugin fallback; the skill bundle ships a byte-identical copy under `data/`).

If neither resolves, treat the alias lookup as a no-op (keep the rule-4 result unchanged) and emit a coverage note. The alias miss is non-blocking; it degrades topic-synonym collapse, it does not stop the gate.

**Canonical cross-references** (`.claude/commands/spec.md`, `.claude/skills/memory/SKILL.md`). These are toolkit-source pointers for maintainers. In installed-plugin mode, equivalent content ships under `<plugin>/skills/`. Do not execute those source-tree paths in a consumer repo; resolve bundled scripts from `<skill_dir>/../<skill-name>/scripts/` first, then fall back to `.claude/...` only after confirming the current repo is this toolkit checkout.

Downstream callers (orchestrators, review skills, CI gates) parse this block by its `step0-halt` info-string. Free-form prose halts that omit the fenced block are non-conforming and SHALL be re-emitted in this format.

**Auto-mode behavior**: under auto-mode invocation (no human elicitation possible), the agent MUST halt with reason `STEP_0_REQUIRES_ELICITATION`, list each unanswered question, and return to the orchestrator. The agent MAY populate Step 0 from the source artifact (issue body, PR description) only when the source artifact contains the required structured fields verbatim. Free-form synthesis of Step 0 answers by the agent is prohibited. (Note: `STEP_0_REQUIRES_ELICITATION` is a prose convention in this version; no orchestrator caller currently parses it. Future iteration will add machine-readable halt protocol.)

**Kill criteria for the gate itself**: at 30 invocations, this gate is reviewed against four kill criteria documented in `REQ-006-13`:

1. False-positive rate ≥30% (halts followed by re-invocation with cosmetic word changes).
2. Bypass rate ≥20%.
3. Author abandonment ≥3 sessions in 7 days.
4. 30 consecutive passes with zero halts (recalibration trigger, not a kill).

If any criterion fires, the gate is loosened or removed in a follow-up PR.

**Tally instruction**: after each Step 0 evaluation (whether pass or halt), append one line to `.agents/metrics/STEP-0-METRICS.md` through the canonical hardened writer `scripts/metrics_writer.py` (`safe_append_tally(path, line)`), not a hand-rolled `open(path, "a")`. The writer rejects a symlink at the tally path (CWE-59 link following), opens with `O_NOFOLLOW` to close the check-then-open race (CWE-367 TOCTOU), and holds an exclusive `flock` so concurrent `/spec` runs do not interleave lines. It creates the parent directory `.agents/metrics/` lazily if absent (the directory is project-only and may not exist on a fresh checkout or vendored install) and creates the file lazily. Write the header line `# Step 0 Metrics (one line per /spec invocation)` as the first record when the file is new. Each tally line uses UTC ISO-8601 with the literal trailing `Z` (`YYYY-MM-DDTHH:MM:SSZ`) so drift/kill-criteria tooling parses records deterministically (observability traceability): `<UTC YYYY-MM-DDTHH:MM:SSZ> | <pass|fail> | <halt-trigger-or-none> | <halt-question-or-none>`. Absence of the file does not block `/spec`; the tally is review-only data for the kill criteria above.

**Archival policy**: after each kill-criteria review (every 30 invocations or when a kill criterion fires, whichever comes first), rotate the tally file: rename `.agents/metrics/STEP-0-METRICS.md` to `.agents/metrics/STEP-0-METRICS-YYYYMMDDTHHMMSSZ.md` (using the rotation timestamp in UTC) and start a fresh file with the same header. The timestamped suffix prevents same-day collisions when two rotations land in the same calendar day (collision safety). The rotated file is the audit trail for that review window. The active file SHALL NOT exceed 100 entries before rotation.

---


