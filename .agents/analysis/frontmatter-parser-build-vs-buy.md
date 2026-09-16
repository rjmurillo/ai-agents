# Frontmatter Parsing: Buy vs Build vs Extend Evaluation

**Date**: 2026-09-16
**Driving issue**: [#5275](https://github.com/rjmurillo/ai-agents/issues/5275) (Three ADR frontmatter parsers disagree on closing-fence strictness)
**Depth tier**: Quick (Phase 0 of `buy-vs-build-framework`)
**Status**: Recommendation, pending owner decision

## Executive Summary

**Recommendation: EXTEND in the repo tree, disciplined BUILD in the plugin trees.**
One decision, two implementations, because a hard packaging boundary runs through
the middle of this problem and no single answer survives it.

`python-frontmatter==1.3.0` is already a pinned dependency (`pyproject.toml:13`)
and already correctly used by three production modules. Where it is importable,
it should be the only fence-detection and YAML-load engine, behind one repo-owned
adapter. Where it is **not** importable, its `FM_BOUNDARY` regex should be the
written specification that a stdlib-only implementation mirrors verbatim, with a
test pinning the two together.

Four findings drive this.

1. **The issue understates the problem by an order of magnitude.** It names three
   parsers. A repo-wide sweep finds **at least 11 distinct fence contracts**
   (verified by regex enumeration, table below) across roughly **35 hand-rolled
   implementations** (reported by a full-tree survey; see Provenance). Unifying
   three of them leaves the same defect class live in the rest.
2. **A hard constraint splits the fix in two.** `.claude/rules/plugin-self-containment.md`
   limits plugin-shipped skill scripts to the standard library and `yaml`.
   Verified: every import across `.claude/skills/*/scripts/*.py` resolves to
   stdlib, `yaml`, or a sibling module. Zero third-party packages.
   **`detect_adr_changes.py`, one of #5275's own three parsers, lives behind that
   boundary** and states the constraint in its own docstring
   (`.claude/skills/adr-review/scripts/detect_adr_changes.py:162-165`). It cannot
   import the library. No amount of preference changes that.
3. **Buying alone does not work even where the library is available.**
   `python-frontmatter`'s public `loads()` collapses "no frontmatter",
   "unterminated", "empty block", and "non-mapping block" into the same
   `metadata == {}`. At least two call sites must tell those apart, and
   `check_adr_lifecycle.py:246` already documents this exact collapse as a problem
   it works around. The adapter restores the distinction using the library's own
   `detect()` and `split()` primitives, with no repo-owned regex.
4. **The ADR-073 conflict is not real.** `build/scripts/generate_adr_index.py`
   lines 36 to 40 cite ADR-073's `yaml.safe_load` mandate as its reason to avoid
   the library. But `YAMLHandler.load` (`frontmatter/default_handlers.py:255`) is
   `yaml.load(fm, Loader=SafeLoader)`, which is what `yaml.safe_load` is. The
   library satisfies the mandate, and ADR-073's own worked example (lines 111 to
   116) already imports `frontmatter`. No accepted decision is reversed and no new
   ADR is required. That docstring is a wrong citation and needs correcting.

### On the stated directive

The instruction driving this evaluation was "don't have a custom frontmatter
parser, use a lib." That holds in full across the repo tree, which is where the
large majority of the duplication lives. It cannot hold literally inside the three
plugin roots, because the library is not shippable there. The recommendation
honors the intent as far as the packaging allows: in the plugin trees the library
stops being the *implementation* and becomes the *specification*, pinned by a test
rather than by an import. That is the repo's own existing precedent, not a new
invention (issue #4918 / PR #5004, discussed below).

## Scope Correction: The Real Inventory

Distinct fence contracts, verified on 2026-09-16 by enumerating compiled patterns
and substring parsers:

| # | Fence contract | Representative site | Tree | Mirrors |
|---|---|---|---|---|
| 1 | `text.find("\n---", 3)` | `scripts/validation/yaml_utils.py:26` | repo | `check_adr_lifecycle.py:224,237`, `spec_contradiction.py:218`, `check_spec_id_uniqueness.py:47` |
| 2 | `line.strip() == "---"` | `.claude/skills/adr-review/scripts/detect_adr_changes.py:225` | **plugin** | `src/claude/...`, `src/copilot-cli/...` |
| 3 | `^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$` | `build/scripts/generate_adr_index.py:84` | repo | `build/generate_agent_catalog.py:48`, `build/generate_agents_common.py:97` |
| 4 | `^---\r?\n(.*?)\r?\n---` (DOTALL) | `src/claude/skills/skillforge/scripts/validate-skill.py:62` | **plugin** | 3 skillforge trees |
| 5 | `\A---\n(.*?)\n---\n` (DOTALL) | `scripts/metrics/control_plane_baseline.py:65` | repo | none |
| 6 | `\A---\n(.+?)\n---` (DOTALL; `.+?` alone rejects an empty block) | `.github/scripts/check_design_review_gate.py:48` | repo | none |
| 7 | `^---\n(.*?)\n---` (DOTALL) | `scripts/validation/check_skill_adr_bindings.py:226` | repo | none |
| 8 | `^---\n(.*?)\n---\n` (DOTALL) | `scripts/validation/check_skill_skip_clauses.py:21` | repo | none |
| 9 | `^---\s*\n(.*?)\n---\s*\n` (DOTALL) | `scripts/validation/instruction_budget_globs.py:11` | repo | `check_rule_scope_keys.py:64` |
| 10 | `\A(---\r?\n.*?\r?\n---\r?\n)(.*)\Z` (DOTALL) | `build/scripts/copilot_body_translation.py:60` | repo | none |
| 11 | open `---[ \t]*\n` + close `^---[ \t]*$` (MULTILINE) | `build/scripts/validate_agent_matrix_refs.py:200,206` | repo | none |

The full-tree survey reports roughly 35 implementations once every `split("---", 2)`,
`startswith("---")` line-scan, and per-field regex variant is counted. Beyond fence
shape, three parsers do not load YAML at all and scrape fields with their own
regexes (`scripts/validation/traceability.py:93`, `scripts/traceability/spec_utils.py:54`,
`.github/scripts/check_design_review_gate.py:70`), so they diverge on YAML semantics
as well as on fences.

Three modules already delegate to the library and are not part of the problem:
`scripts/validate_skill_installation.py:28`, `scripts/openclaw_bridge.py:32`,
`scripts/memory_enhancement/serena_integration.py:15`.

`scripts/validation/memory_index.py:888` is the decisive case. It **hand-copies
python-frontmatter's own `FM_BOUNDARY` regex** into repo code, with a docstring
quoting it verbatim and naming three deliberate divergences. It is not sloppiness.
It is the correct answer to a constraint, and it is the template for the plugin
trees.

## Prior Art: This Question Was Already Answered Once

Issue #4918 / PR #5004. A Serena memory file carried unquoted YAML. The canonical
loader (`serena_integration.py`, which uses the real library) raised, caught, and
silently dropped the file's metadata with only a stderr warning. No gate failed;
corruption reached `main`. The first gate written to catch it keyed on
`line == "---"`. A differential probe against the library found three false-negative
shapes it missed, because the real delimiter is `^-{3,}\s*$` (three **or more**
dashes) after a `.strip()` pass, not a literal `---`.

The resolution was not "import the library everywhere." It was: copy the library's
exact pattern into the gate, quote it verbatim, and pin it with a test. That is the
`.claude/rules/canonical-source-mirror.md` doctrine, and it exists precisely because
approximating a parser you cannot import produces silent false negatives.

The memory states it directly: *"a gate with false negatives is decorative."*

This evaluation does not overturn that. It extends it: use the library wherever
importing is possible (which #5004 did not systematically do), and keep the
mirror-plus-pin discipline only where importing is impossible.

## Evidence: Executed Divergence Matrix

Direct execution against the four parsers named in #5275 plus the library.
`OK` = frontmatter extracted, `None` = rejected.

```text
| case                           | yaml_utils | adr_lifecycle | detect_adr | adr_index_re | python-frontmatter |
|--------------------------------|------------|---------------|------------|--------------|--------------------|
| baseline (clean)               | OK         | OK            | OK         | OK           | OK                 |
| close fence + 1 space          | OK         | OK            | OK         | None         | OK                 |
| close fence + trailing text    | OK         | OK            | None       | None         | None               |
| close fence 4 dashes           | OK         | OK            | None       | None         | OK                 |
| CRLF line endings              | OK         | OK            | OK         | OK           | OK                 |
| open fence + 1 space           | OK         | OK            | OK         | None         | OK                 |
| no closing fence               | None       | None          | None       | None         | None               |
| close fence, EOF no newline    | OK         | OK            | OK         | None         | OK                 |
| close fence + tab              | OK         | OK            | OK         | None         | OK                 |
| BOM before open fence          | None       | None          | None       | None         | None               |
```

Library boundary, read from the installed package:
`YAMLHandler.FM_BOUNDARY = re.compile(r"^-{3,}\s*$", re.MULTILINE)`
(`frontmatter/default_handlers.py:252`).

Two readings matter.

- The library sits at a **defensible middle**. It accepts author slips that change
  no meaning (padded fence, tab, extra dashes, missing final newline) and rejects
  the one shape that signals a real mistake (`--- trailing text`). That is the
  contract a human author would predict, which is the property worth standardizing
  on.
- Adopting it is a **behavior change at every one of the four sites**, not a
  drop-in. It rejects `--- trailing text` that `yaml_utils` accepts, and accepts
  `----` that `detect_adr_changes` rejects. Each flip needs its own reviewed test
  change. This is the real cost of the recommendation and it is not hidden.

### Corpus risk is latent, not active

Scanning all **2,525** markdown files under `.agents/architecture`, `.serena/memories`,
`.claude/skills`, `src`, and `templates`: **zero** files disagree on fence shape
between `yaml_utils`, the index regex, and the library.

The only three flagged files are one skillforge template mirrored three times
(`{.claude,src/claude,src/copilot-cli}/skills/skillforge/assets/templates/skill-md-template.md`),
and the disagreement is a YAML *value* problem, not a fence problem: `name: {{SKILL_NAME}}`
parses as a nested flow mapping and PyYAML raises `ConstructorError`. Every parser
that loads YAML rejects it identically.

This is what puts the decision at **Quick** tier rather than Deep. Nothing is broken
today. The work buys insurance against a defect that is cheap to introduce and
expensive to diagnose. Issue #4918 is the proof that the insurance pays out.

## Integration Hazards Found by Probe

Why the adapter is load-bearing rather than ceremonial. Each was executed.

| # | Hazard | Observed | Consequence if ignored |
|---|---|---|---|
| H1 | `loads()` collapses four states | no-frontmatter, unterminated, empty, and non-mapping all yield `metadata == {}` | `generate_adr_index.py` loses its named `AdrIndexError`; a malformed ADR silently lands under "Needs backfill" instead of failing the run |
| H2 | `loads()` strips the body | `'---\nid: A\n---\n\n\n# Title\n\nPara.\n'` yields `content == '# Title\n\nPara.'` | Any caller computing body line offsets reports wrong line numbers |
| H3 | `loads()` raises where the current helper returns `None` | `yaml.scanner.ScannerError` on malformed YAML; `yaml_utils` returns `None` | Uncaught exception replaces a clean validation failure at five `yaml_utils` call sites |
| H4 | **`loads(text, Loader=...)` silently corrupts metadata** | `frontmatter.loads(t, Loader=yaml.SafeLoader).metadata` returns `{'Loader': <class SafeLoader>, 'id': 'ADR-1', ...}` | The obvious way to pin the loader injects a bogus `Loader` key into every record. `**defaults` in `loads()` means *default metadata*, not loader kwargs |
| H5 | Loader selection is environment-dependent | The library binds `CSafeLoader` when libyaml is present (confirmed present here), pure-Python `SafeLoader` otherwise | The same document can parse differently on a contributor machine than in CI |
| H6 | `dumps()` is not byte-faithful | round-trip of `'---\nid: A\nstatus: accepted\n---\nBody.\n'` returns `'---\nid: A\nstatus: accepted\n---\n\nBody.'` (blank line inserted, trailing newline dropped) | Any tool rewriting an ADR in place reformats unrelated bytes |

H4 and H5 together are the finding that most changes the plan: **the obvious
one-line mitigation for H5 is exactly H4.** The correct pin is a handler subclass:

```python
class _PinnedYAMLHandler(YAMLHandler):
    def load(self, fm, **kw):
        kw["Loader"] = yaml.SafeLoader   # match yaml.safe_load exactly, per ADR-073
        return yaml.load(fm, **kw)
```

Verified: `frontmatter.loads(t, handler=_PinnedYAMLHandler()).metadata` returns
`{'id': 'ADR-1', 'status': 'accepted'}` with no injected key.

### The library's own primitives restore what `loads()` loses

`YAMLHandler.detect()` and `.split()` give a clean four-way outcome with no
repo-owned regex:

| Input | `detect()` | `split()` | Adapter outcome |
|---|---|---|---|
| no frontmatter | `False` | `ValueError` | `ABSENT` |
| unterminated | `True` | `ValueError` | `UNTERMINATED` |
| empty block | `True` | ok | `EMPTY` |
| non-mapping (list) | `True` | ok, load returns list | `NOT_A_MAPPING` |
| valid | `True` | ok | `(metadata, body)` |

This is what makes "use the library" achievable in full on the repo side: the
adapter reads `detect`, `split`, and `load` from the installed package and adds
**zero** fence logic of its own.

## Phase 1: Core vs Context

**Classification: CONTEXT.** Strategic importance **2/10**.

1. Frontmatter fence detection is a commodity with a stable shape and mature
   implementations. Nobody chooses this repo because of how it finds a `---`.
2. The dependency is already paid for and already correctly used in three modules.
3. Hours spent on fence arithmetic are hours not spent on the governance logic
   above it, which is the actual differentiator.

**Red lines.** The framework's "Never Build" row (commodity, undifferentiated, no
strategic value) matches the repo tree exactly. But its "Never Buy" row also fires
for the plugin trees, under *no viable vendor*: `python-frontmatter` is not
installable in a shipped plugin's execution context, so for that tree there is no
vendor to buy from. This is the split, and it is a packaging fact rather than a
preference.

## Phase 2: TCO and Capacity

Both options are engineering hours inside an existing repo with no license cost, so
the framework's dollar-denominated TCO script does not apply. Substituting hours,
using the compression table in `.claude/rules/builder-ethos.md`:

| Cost category | Build (unify hand-rolled, no library) | Buy (raw `loads()` everywhere) | **Split: Extend + disciplined Build** |
|---|---|---|---|
| Initial: parser implementation | One canonical contract designed and defended from scratch | 0 | ~40-line adapter (repo, no regex) + one stdlib module per plugin root (mirrored) |
| Initial: call-site migration | ~35 sites | ~35 sites, ~8 of which cannot import the library | ~35 sites |
| Initial: test updates | Every suite re-baselined | Same, plus H1 to H3 fallout | Same, plus one parity test |
| Initial: hazard handling | All hazards ours to discover | H1 to H6 hit production | H1 to H6 handled once in the adapter |
| Ongoing: correctness | Ours forever | Upstream, but H1/H2 re-litigated per site | Upstream on the repo side; pinned-by-test on the plugin side |
| Ongoing: new call sites | Each author re-derives the contract (this is how we reached 11) | One import, four collapsed states | One import (repo) or one sibling import (plugin) |
| Hidden | Contract #12 appears next time someone needs a parser | Silent metadata corruption via H4; **8 sites simply cannot comply** | One dependency-version risk; parity test must not be deleted |

**Capacity**: no new skill required. Three modules already use the library, and
`memory_index.py:888` shows the mirror-and-pin discipline is already understood and
executed here.

**Dependency risk**: pinned exact version, pure Python over PyYAML (already a
direct dependency), no new transitive surface. If it were abandoned, the adapter is
the one file needing a new backend. That containment is a main thing the adapter
buys.

## Phase 3: Decision Matrix

| Dimension (weight) | Build (no library) | Buy (raw, everywhere) | **Split (recommended)** |
|---|---|---|---|
| Strategic (40%): alignment, optionality | 3 (invests in commodity) | 4 (**infeasible in 3 plugin roots**) | **8** (one seam, ADR-073 satisfied, #5004 precedent extended) |
| Operational (30%): time to value, maintenance | 4 (largest initial, highest ongoing) | 3 (fast until it hits the boundary, then stalls) | **8** (hazards paid once) |
| Risk (30%): execution, lock-in | 5 (contract #12 risk persists) | 2 (H4 corrupts silently; plugin sites cannot ship) | **7** (behavior change is the real risk, and it is testable) |
| **Weighted** | **3.9** | **3.1** | **7.7** |

Gap between leader and runner-up is 98%, far past the framework's 20% clear-winner
threshold. Confidence: HIGH. Note that raw Buy scores *below* Build once the
packaging boundary is priced in, which is the opposite of the ordering before that
constraint was verified.

### Pre-mortem on the recommended option

Assume it is six months out and this failed. Why?

| Failure mode | Likelihood | Mitigation |
|---|---|---|
| A tightened contract rejects an ADR that used to pass; CI goes red on `main` | Medium | Corpus scan shows 0 affected files today. Land the adapter with **no** call-site changes, then migrate one PR at a time, each re-running the scan |
| Tests re-baselined to match new behavior without anyone deciding the new behavior is correct | **High** | The "incidental breakage" risk #5275 names itself. Every flipped expectation lands in a commit that changes only that test, naming the case |
| The repo adapter and the plugin mirror drift apart | **High** | The parity test is the whole mechanism. Assert the plugin module's boundary constant equals `YAMLHandler.FM_BOUNDARY.pattern` read from the installed library, the way PR #5004 pinned `memory_index.py` |
| The adapter grows fence logic and becomes contract #12 | Medium | A test asserting the repo adapter contains no `---` regex literal |
| `CSafeLoader` vs `SafeLoader` drift between a contributor machine and CI | Low | H5 pinned by the handler subclass; test asserts the bound loader |
| Someone adds parser #12 anyway | **High** without a gate | A validator failing on any new `---` fence regex outside the two sanctioned modules. Without it the decision decays to the status quo |
| **The adapter is named `frontmatter.py` and shadows the PyPI package** | Medium | Real, already-realized failure: issue #4995. `.claude/skills/skillforge/scripts/frontmatter.py` forces `scripts/validation/skill_size.py:39-58` to load it through `importlib.util.spec_from_file_location`. Name the adapter `frontmatter_contract.py`, never `frontmatter.py` |

Seven failure modes, three rated High, one drawn from an incident that already
happened. All have concrete, cheap mitigations that are part of the recommendation
rather than deferred follow-ups.

## Phase 4: Decision and Rollout

**Decision: EXTEND on the repo side, disciplined BUILD on the plugin side.**

Sequenced so no step can break `main`:

1. **Repo adapter, no callers.** `scripts/validation/frontmatter_contract.py`
   (**not** `frontmatter.py`, per issue #4995) exposing the four-way outcome above,
   the pinned handler, and byte-faithful body access. Zero regex. Positive,
   negative, and edge tests per `.agents/governance/TESTING-RIGOR.md`, covering the
   #5275 case and every H1 to H6 hazard as a negative control.
2. **Plugin mirror, no callers.** One stdlib+`yaml` module per plugin root,
   quoting `FM_BOUNDARY` verbatim with a `Stricter/looser/different than canonical`
   section per `.claude/rules/canonical-source-mirror.md`, plus the **parity test**
   asserting its constant equals the installed library's pattern.
3. **The #5275 regression test**, asserting `check_adr_lifecycle.py`,
   `detect_adr_changes.py`, and `generate_adr_index.py` agree on a closing fence
   with one trailing space. This is acceptance criterion 2. It crosses the plugin
   boundary, so it is the test that proves steps 1 and 2 actually agree. Written
   red first.
4. **Migrate #5275's four parsers**, one PR each, each re-running the 2,525-file
   corpus scan. Order: `generate_adr_index.py` (strictest, the one that crashes),
   then `detect_adr_changes.py` (plugin side, via step 2), then
   `check_adr_lifecycle.py`, then `yaml_utils.py` last because it has five callers
   (acceptance criterion 3: `pre_pr.py`, `check_adr_lifecycle.py`,
   `validate_design_review.py`, `validate_copilot_agent_frontmatter.py`, and
   `spec_contradiction.py` which mirrors it).
5. **Migrate the remaining contracts**, one PR each. Outside #5275 as filed; file
   as sub-issues so the scope correction is tracked rather than lost.
6. **Add the anti-regression gate** so contract #12 cannot be introduced.
7. **Delete the dead constant.** `FRONTMATTER_REGEX` at `_constants.py:78` in all
   three skillforge trees has zero importers, while `validate-skill.py:62` inlines
   the same literal instead of importing it.

**ADR**: not required. ADR-073 already names `python-frontmatter` in its worked
example and its `yaml.safe_load` mandate is satisfied by `YAMLHandler.load`. The
`Stricter/looser/different than canonical` section of
`build/scripts/generate_adr_index.py` (lines 36 to 40) needs correcting, because it
claims a conflict with that mandate that does not exist. Under
`.claude/rules/canonical-source-mirror.md` a wrong citation is worse than none.

**Reassessment triggers**: `python-frontmatter` stops receiving releases for 24
months; a call site needs a fence contract the library cannot express; PyYAML
ceases to be a direct dependency; the plugin self-containment constraint changes.

## Flags Raised on the Path (voice.md: see something, say something)

1. `FRONTMATTER_REGEX` at `_constants.py:78` in all three skillforge trees is
   declared and never imported; `validate-skill.py:62` duplicates the literal
   inline. Dead constant plus live duplicate. Folded into step 7.
2. `scripts/validation/memory_index.py:888` hand-copies the library's `FM_BOUNDARY`
   rather than importing the installed package, in a tree where importing **is**
   possible. Correct today, and the pinned-constant test protects it, but it is the
   one mirror that could become a plain import.
3. `.github/scripts/check_design_review_gate.py:48` uses `.+?` where every sibling
   uses `.*?`, so it alone rejects an empty frontmatter block, and it scrapes
   fields with `key.partition(":")` instead of loading YAML. Two behaviors nobody
   chose. Not currently reachable by any corpus file.
4. `build/scripts/generate_adr_index.py` lines 36 to 40 assert a conflict with
   ADR-073 that does not exist. Corrected in step 4.
5. `scripts/validation/traceability.py:93` documents that it avoids a YAML library
   "to match the PowerShell implementation behavior." That PowerShell parity
   constraint is worth confirming still binds before migrating it; if the
   PowerShell side is retired, the justification is stale.

## Provenance

Verified by direct execution or direct file read during this evaluation: the
dependency pin; `FM_BOUNDARY` and `YAMLHandler.load`; the divergence matrix; the
2,525-file corpus scan; hazards H1 to H6; the `detect`/`split` discrimination
table; the 11 distinct fence contracts; the stdlib-only import reality of
`.claude/skills/*/scripts/*.py`; the `skill_size.py:39-58` collision workaround;
ADR-073's cited lines.

Reported by a full-tree survey and **not** independently re-verified line by line:
the ~35 total implementation count, the per-row details of parsers outside the 11
enumerated contracts, and the issue #4918 / PR #5004 narrative (the surviving
artifacts at `memory_index.py:887-897` and
`.serena/memories/validation/validation-frontmatter-gate-parity.md` corroborate it,
but the incident timeline itself was not re-derived from git history).
