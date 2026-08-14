---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14707-4940-model-pin-doc-examples.json
qaCommit: 21736b962851c192c855b274a48689eec30d309d
---

# Issue 4940 Model Pin Doc Examples QA

## Scope

Five documents taught authors to write a versioned `model:` pin that ADR-080
forbids and `scripts/validation/check_model_pins.py` rejects. This validates the
corrections plus the regression guard that keeps them corrected.

Files under test:

- `docs/SKILL-AUTHORING.md`
- `.agents/steering/claude-skills.md`
- `.agents/architecture/ADR-040-skill-frontmatter-standardization.md`
- `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`
- `.agents/architecture/DESIGN-REVIEW-context-optimizer-refactoring.md`
- `tests/test_skill_authoring_docs_model_pins.py`

## Acceptance Criteria

Quoted from issue #4940: "Five documents teach authors to write a versioned
`model:` pin that ADR-080 forbids and `check_model_pins.py` rejects" and
"Correct every example so it shows a conformant state: either no `model:` line
at all (inherit, the ADR-080 default) or a bare cost-tier alias with a
`model-rationale:` line."

- [x] Every fenced YAML example in the five documents shows a conformant state.
- [x] Counter-examples are labelled as such, so the docs can still show the
  rejected shape next to the correct one.
- [x] The inherit-by-omission default is stated as the default, not as an
  afterthought, matching ADR-080 rule 1.
- [x] The cost exception names the only alias that qualifies today and the
  `model-rationale` requirement that rides with it.
- [x] Historical decisions are preserved rather than rewritten.

## Canonical Source Check

The contract, read this session from `scripts/validation/check_model_pins.py`:

```python
_VERSIONED_RE = re.compile(r"^claude-(?:opus|sonnet|haiku)-[0-9]")
ROLLING_ALIASES = ("sonnet", "opus", "haiku")
DEFAULT_MODEL = "claude-sonnet-4-6"
```

```text
f"{unit.kind} carries versioned id '{model}'; skills and commands may not pin a version (ADR-080 rule 1)"
f"bare alias '{model}' lacks a model-rationale field"
f"cost rationale on '{model}' but it does not price below the default '{default}'"
```

Coverage of those strings, stated precisely (corrected after PR #5003 review):
`docs/SKILL-AUTHORING.md` and `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`
quote the "carries versioned id" and "cost rationale on" messages so a reader
recognises the failure they will see. The "lacks a model-rationale field"
message is not quoted anywhere, and no test compares doc text to validator
strings, so rewording a gate message would leave all 18 tests green and the
quoted text stale. The guard asserts what the documents teach, not what the
validator prints.

Two consequences of that regex drove corrections the issue's line list missed:

1. `claude-haiku-4-5` matches `_VERSIONED_RE`. The issue grepped for 4.6 and
   4-6, so every haiku example it listed as fine was equally rejected.
2. `_collect_nested_pins` matches `if key == "model"`, so
   `metadata.subagent_model` sits outside the gate. The docs now describe it as
   inert metadata instead of claiming the gate rejects it.

Pricing and tier claims come from `templates/platforms/copilot-cli.yaml`
(`model_tiers`) and `scripts/eval/_eval_common.py`
(`MODEL_PRICING_RATES_USD_PER_1K_TOKENS`): opus $0.005, sonnet $0.003, haiku
$0.001 per 1K input tokens. Only `haiku` prices below the sonnet-tier default,
which is why it is the only alias the docs offer.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Doc regression guard | `uv run pytest tests/test_skill_authoring_docs_model_pins.py -q` | 18 passed |
| Non-vacuity control | detector run against `git show origin/main:<doc>` for all five docs | 5 of 5 WOULD FAIL (5 hits, 1, 5, 7, 1) |
| Model pin gate | `uv run python scripts/validation/check_model_pins.py --mode warn` | exit 0, "OK: no new or changed pin violations" |
| Markdown lint | `npx markdownlint-cli2 docs/SKILL-AUTHORING.md` | 0 issues (the `.agents/**` docs are excluded by `.markdownlint-cli2.yaml`) |
| Python lint | `uv run ruff check` and `ruff format --check` on the new test | All checks passed |
| ADR change detection | `uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --since-commit origin/main` | ADR-040 Modified; review recorded in `.agents/critique/ADR-040-amendment-2026-08-14-model-pin-examples-debate-log.md` |
| Shipped-frontmatter mirror | `grep -h '^model:' .claude/skills/*/SKILL.md \| sort \| uniq -c` | 7 occurrences, all `model: haiku`, out of 99 skills |

## Inverse Failure Modes Checked

A correction like this fails in three directions. Each was closed in the same
diff.

| Inverse | Risk | Closed by |
|---------|------|-----------|
| Over-correction | Banning `model:` outright would forbid the legitimate `haiku` cost alias that 7 shipped skills use and ADR-080 rule 3 permits. | Both conformant states documented; the cost alias appears with its rationale in every guide. |
| Under-correction | Fixing only the 4.6 spellings the issue listed would leave `claude-haiku-4-5`, which the same regex rejects. | Corrected every versioned spelling, dotted and hyphenated. |
| Contradiction | Telling readers "no pins ever" would contradict ADR-080 rule 2, which allows an agent to pin with a KEEP_PIN sweep entry. | `docs/SKILL-AUTHORING.md` has an "Agents Are Different" section; `SKILL-STANDARDS-RECONCILED.md` repeats it in the `model` field definition. |

## Testing Quality Checklist

- [x] Security-critical paths: none. The diff changes prose and adds a test that
  reads repository markdown. No secrets, no input parsing, no subprocess, no
  path construction from user data. `detect_infrastructure.py` printed a
  CRITICAL advisory on `tests/test_skill_authoring_docs_model_pins.py` because
  its `CRITICAL_PATTERNS` entry `.*Auth.*\.(cs|ts|js|py)$` matches the substring
  "auth" inside "authoring". A name collision, not a finding.
- [x] Tests verify behavior, not execution. The guard asserts what a document
  teaches, and the pre-fix control shows all five documents failing it before
  the change.
- [x] No coverage theater. Seven unit tests pin the edges: an unlabelled pin
  fires, a labelled one does not, a pin later in a `# Wrong` fence still fires,
  `**Before**` migration fences are exempt, a bare alias is not mistaken for a
  version, the dotted spelling matches, and a `**Before**` label does not exempt the
  `**After**` fence that follows it (added after the PR #5003 review).
- [x] Line-level, not block-level, matching. The pre-fix troubleshooting section
  put `# Wrong` and `# Correct` in one fence, so a block-level marker check
  would have accepted the exact shape this guard exists to catch.

## Known Gaps

1. `.markdownlint-cli2.yaml` excludes `.agents/**`, so four of the five edited
   documents are not lint-covered. The guard test covers their model-pin
   content, which is the part this issue is about.
2. The `model` column of ADR-040's Section 3 tier table still shows versioned
   ids. Deliberate: it is the historical tier reasoning, marked do-not-copy by
   the callout above it.
3. `.agents/architecture/SKILL-STANDARDS-RECONCILED.md` lines 60, 93 and 100
   still call `version` a "SkillForge validator requirement". `_constants.py`
   lists it under `OPTIONAL_PROPERTIES`, so those lines are inaccurate. They sit
   outside this diff and outside the model-pin scope; recorded as a follow-up
   rather than corrected here.
4. Serena memory `claude/claude-code-skill-frontmatter-standards`, memory
   `skills/skillcreator-enhancement-patterns`, and
   `.agents/analysis/claude-code-skill-frontmatter-2026.md` still carry the
   retired `claude-opus-4-5` guidance. Out of scope for a docs PR; recorded as
   follow-ups.

## Verdict

PASS. Every copyable example in the five documents now shows a state the gate
accepts, the two conformant states are taught rather than one, the historical
record survives, and a guard with a demonstrated pre-fix failure keeps the
examples honest.
