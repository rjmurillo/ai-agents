# ADR Debate Log: Template-Owned Skill Files Under `.claude/skills/`

Record under review: `.agents/architecture/ADR-108-template-owned-skill-files.md`
Tracker: issue #5706, sub-issue of epic #5698. Branch: `feat/5706-adr-108-skill-templates`.
Tree state at review: HEAD `cd0f9561d`, the record and its cross-references staged and not
committed, read from disk.

## Summary

- Rounds: 4
- Seats: 6 (architect, critic, independent-thinker, security, analyst, high-level-advisor)
- Round 1 outcome: **3 Block, 3 Disagree-and-Commit.** No consensus on revision 1.
- Round 2 outcome: **4 Accept, 1 Disagree-and-Commit, 1 Block.** No consensus on revision 2.
- Round 3 outcome: **1 Accept, 4 Disagree-and-Commit, 1 Block.** No consensus on revision 3.
- Round 4 outcome: **3 Accept, 3 Disagree-and-Commit, 0 Block. Consensus reached.**
- Disposition: the owner folded all 18 round-1 findings into revision 2, the five round-2 P1s into
  revision 3, and the three round-3 P1s into revision 4. Every Block condition from rounds 1, 2 and
  3 is verified closed. Round 4 reached consensus with one P1 carried forward against the
  implementation spec rather than against this record.
- Final status: proposed, `implemented: false`, `review-by: 2027-03-11`.

Each seat received the record's path and the Zimmermann checklist path, and nothing else. None
saw the reasoning that produced the record, and none saw another seat's findings. Every claim
below was re-verified against the tree by the orchestrator before it entered this log. Four seat
claims were checked and corrected or rejected; they are recorded under "Findings rejected or
corrected".

## Agent positions

| Agent | Round 1 vote | Load-bearing objection |
|-------|--------------|------------------------|
| architect | Block | Decision sections 2 and 3 quote new text for REQ-003-010 and ADR-107 property 1 that neither staged file carries; both were amended by a note and a pointer instead, and the record's own Impact table says so |
| critic | Block | Same mismatch on the verification sentence, plus REQ-003 decision D4 named as a blocking constraint and then never amended while section 1 contradicts it |
| security | Block | The `.claude/` write allowlist is computed from filesystem presence with no bound and no owner gate on `templates/skills/`, and section 4 does not say whether `--validate` passes or fails a NO-REGEN protected file |
| independent-thinker | Disagree and commit | The record's own restricted grammar argues against needing `chevron` at all, and the rejected alternative is described as lacking a template layer it already has |
| analyst | Disagree and commit | Citation audit: the class table calls the Copilot mirror unchanged when the generator translates it, and the Serena memory citation does not resolve |
| high-level-advisor | Disagree and commit | The scope fence is social rather than mechanical, and no tracked issue depends on this pilot to deliver the epic's byte reduction |

## Key issues found in round 1

**The record states amendments that the staged files do not carry.** Three seats found this
independently and it is the round's strongest finding. Line 58 says REQ-003-010 "now reads" a
sentence with an inline exception clause. The staged file leaves its sentence untouched at
`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:359` and appends a
`> [!NOTE]` block at `:363-367` with different wording. Line 62 makes the same claim about the
verification sentence, which is untouched at `:361`. Lines 64 to 66 say ADR-107 property 1 "reads,
from this record on" a new sentence; property 1 is untouched at `ADR-107-canonical-skill-contracts-and-harness-projections.md:61`
and the staged change is a Related Decisions bullet at `:656-658`. The record's own Impact table
at lines 148 and 149 describes the note and the pointer correctly, so the Decision section
contradicts the same record's Impact table. Verified by reading `git diff --cached` on both files.

**REQ-003 decision D4 is listed as a blocking constraint and never resolved.** Line 36 cites
`REQ-003-multi-tool-artifact-build.md:80`, "`.claude/<artifact>/` is canonical", as one of four
constraints that block the design. Sections 2 and 3 amend REQ-003-010 and ADR-107 property 1 and
stop there. Section 1 then makes `templates/skills/<name>.SKILL.md.tmpl` the canonical source for
the class, which is what D4 forbids. Line 80 is untouched in the staged diff.

**The class table calls the Copilot mirror unchanged, and the generator translates it.** Line 51
reads "the existing `generate_skills.py` directory copy mirrors into `src/copilot-cli/skills/<name>/`,
unchanged". `build/scripts/generate_skills.py:116-120` calls `translate_skill_file`, and
`build/scripts/copilot_body_translation.py:311-322` rewrites the `allowed-tools` frontmatter line
and the body. The `@CLAUDE.md` to HTML comment rewrite is the record's own evidence at line 27, so
the two statements disagree inside one record.

**The write allowlist has no bound and the scope fence has no lock.** Line 54 states membership is
read from the directory at run time with no list of names kept anywhere else, and line 82 says
converting any other skill waits on the owner's word. `.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md:72-73`
gives `discover(repo_root)` and `owned_targets(repo_root)` no allowlist parameter, and
`.github/CODEOWNERS` carries no entry for `templates/skills/`; its only skills entry is
`/.claude/skills/review/references/ @rjmurillo` at line 11. A ninth template file therefore widens
a `.claude/` write allowlist with no gate and no ADR.

**One citation will fail the repository's own citation gate.** Line 33 cites
`REQ-003-multi-tool-artifact-build.md:358` while quoting a sentence that sits at `:359`. Measured
with the gate's own matcher: `citation_anchors._anchor_candidates` on line 33 returns
`['claude/<artifact>/', 'docs-say', 'The build shall never write to ...']`, and `_anchor_matches`
returns False against line 358 alone and True against lines 358 and 359 together.
`check_citation_freshness.py` examines added lines against a base ref, so it reported zero
citations while the change is staged and uncommitted; it fires on commit.

**The `chevron` claims are true about the package and wrong about the tree.** Line 50 says the
engine is "pinned as a dev dependency in both dev tables of `pyproject.toml`" in the present
tense. `grep -n chevron pyproject.toml uv.lock` returns nothing and `import chevron` raises
`ModuleNotFoundError` in the project environment. Line 114 labels a chevron probe `repo-observed`,
a label the record defines at line 21 as read from the tree at `cd0f9561d`; a package absent from
the tree and the lock cannot be observed there. The behavior itself reproduces: in an isolated
environment with `chevron==0.14.0`, `render("A{{> nope}}B", {}, partials_dict={})` returns `'AB'`
and `render("A{{x}}B", {})` returns `'AB'`.

**The dependency is not priced against the in-tree alternative.** Measured: `chevron` 0.14.0 is
746 lines across five modules, implementing sections, inverted sections, lambdas, and custom
delimiters, every one of which section 1 forbids. The record's Trade-offs paragraph at line 118
already concedes that replacing it with an in-tree expander is a bounded change, then defers it.
The independent-thinker seat reported writing the permitted two-tag grammar in 22 lines of
dependency-free Python; the orchestrator verified chevron's size, licence, and silent render
behavior, and did not re-verify the 22-line expander.

**Smaller findings.** Line 131 says a contributor who edits a rendered file "learns it from the
drift gate", but a plain writing build replaces the edit and leaves the gate green, so only
`--check` and the pre-PR gate catch it, and only when they run first. Line 70 does not say whether
`--validate` passes or fails a NO-REGEN protected file, and both readings are bad. Line 168 rolls
back A2 and A1 and says nothing else moves, while A0 already stages the REQ-003-010 note and the
ADR-107 bullet, which would keep asserting an exception under a rejected record. The Impact table
omits `scripts/validation/check_skill_md_portability.py`, whose docstring scopes it to "SKILL.md
and reference `.md` files" and which is the gate a bundled partial carrying a repository path
would trip. Line 183 cites Serena memory `decisions/decision-copilot-cli-skill-task-arguments-claude-import-contract`;
`.serena/memories/decisions/` exists and is empty, and a repository-wide grep for
`claude-import-contract` returns only `build/scripts/copilot_body_translation.py`, this record, and
REQ-021. Line 27 says `templates/` holds `agents/`, `platforms/`, and `toolsets.yaml` only, and it
also holds `AGENTS.md`, `CLAUDE.md`, and `README.md`. Line 101 says the outcome needs a template
layer skills do not have, while the declined design already specifies `templates/skills/partials/`.
The record names none of issues #5686 to #5691, which issue #5706 step 1 and the epic #5698
correction both require the pilot to be placed against. The record carries no
`## Decision Drivers` section; ADR-107 carries one at `:145`.

## Findings rejected or corrected

- **Analyst: the `.serena/memories/decisions/` subdirectory does not exist.** Corrected. The
  directory exists and holds zero entries. The conclusion stands, the evidence was wrong.
- **Analyst and security: the commit and issue claims are unverifiable.** Cleared by the
  orchestrator. `c00a32e5f` is dated 2026-04-30 with subject "feat(spec+plan+adr): REQ-003
  multi-tool artifact build system (#1819)". Both issue quotes were read with `gh issue view` and
  are verbatim: issue #5706 step 1 and the epic #5698 "Review corrections" bullet.
- **Analyst: `copilot_body_translation.py:140` is imprecise because the mechanism spans 140 to 151.**
  Not accepted as a finding. Line 139 is the `def` and line 140 is its docstring, which names the
  transform; the citation anchors the described content.
- **High-level-advisor: the epic's byte reduction has no funded follow-up, so the record is
  unjustified.** Downgraded, not accepted as a defect. Lines 82 and 133 already state that the cut
  waits on the owner's word and that the pilot adds bytes until it lands, and
  `.agents/plans/active/5706-skill-guidance-excerpts.md:109` lists the deferred cut against issues
  #5400, #5492, and #4871. The disclosure the seat asked for is already in the record.

## Adjacent defects flagged, not fixed

Both are outside this record and were not edited.

- `ADR-107-canonical-skill-contracts-and-harness-projections.md:61` cites `build_all.py:788`,
  `:2221`, and `:2227`. The current tree has the definition at `:793`, the call at `:2226`, and
  `audit.overall_exit = 2` at `:2232`. ADR-108's own numbers are the correct ones.
- `.claude/skills/ai-agents-change-control/SKILL.md:56` cites `build/scripts/build_all.py:962-967`
  as the code that fails the build on a `.claude/` write. Those lines are the `OWNED_PREFIXES`
  tuple.

## Not resolved, carried forward

- The record enforces nothing until A1. Line 17 says so plainly, and no seat treated that as a
  defect.
- Every mechanism in sections 4 and 5 describes code that does not exist yet. Three seats noted
  that the present-tense phrasing reads as current state; it is scoped to A1 and A2 in
  Implementation Notes.
- Consensus was not reached and no second round was run. Three seats voted Block and each named
  its unblock condition: reconcile sections 2 and 3 with the staged text, resolve D4, bound the
  allowlist, and settle the NO-REGEN behavior of `--validate`.

## Verdict

No consensus in round 1. The vote is 3 Block and 3 Disagree-and-Commit. The Block seats agree on
one root cause: a record whose whole purpose is to leave governing text in a precise and citable
state describes two amendments that the staged files do not make. That is fixable in text and does
not touch the owner's decision D1. The record stays `proposed` pending revision.

## Round 2

Revision 2 was reviewed by the same six seats under the same rules: the record's path and the
Zimmermann checklist path, nothing else, no seat shown another seat's findings and no seat told
what changed. Every claim below was re-verified against the tree by the orchestrator.

### Agent positions

| Agent | Round 2 vote | Position |
|-------|--------------|----------|
| architect | Accept | All three Block-driving round-1 findings verified fixed against the staged files, not reworded; two precision items remain |
| critic | Accept | Every checked citation matches the tree byte for byte; the skill-authoring documents still carry no exception, and the compile plan has no test for an unsafe template name |
| analyst | Accept | The internal citations carrying the record's evidentiary weight verify cleanly, including the re-anchored guard lines |
| high-level-advisor | Accept | The amendments are backed by matching diffs rather than described-but-absent ones; two one-sentence additions remain |
| independent-thinker | Disagree and commit | The widening control is mechanical rather than owner-gated despite the record's language, and one rationale sentence still overstates why the chosen design is needed |
| security | Block | The sole exception to the `.claude/` write boundary is governed by a test any contributor can edit in the same pull request, and the NO-REGEN path silences the drift gate at NOTICE severity |

### Round-1 findings verified closed

Checked against the staged files, not against the record's description of them.

- `REQ-003-multi-tool-artifact-build.md:359` carries the exception clause inline and matches the
  quote at ADR-108:66. `:361` carries the amended verification sentence. The note at `:363-367` is
  provenance and no longer states the rule a second time.
- `REQ-003-multi-tool-artifact-build.md:80` carries the D4 exception clause, and ADR-108:50 now
  says it amends three texts rather than two.
- `ADR-107-canonical-skill-contracts-and-harness-projections.md:61-62` amends property 1 inline and
  re-anchors the guard to `:793`, `:2226`, `:2232`. All three are the live numbers:
  `def assert_no_claude_writes` at `build_all.py:793`, the call at `:2226`, `audit.overall_exit = 2`
  at `:2232`.
- ADR-108:59 names the translation instead of calling the mirror unchanged, and
  `copilot_body_translation.py:311-322` is `translate_skill_file`, which rewrites the
  `allowed-tools` frontmatter line and the body.
- ADR-108:58 states chevron is not in the tree at `cd0f9561d`. Confirmed: no match in
  `pyproject.toml` or `uv.lock`, and `import chevron` raises `ModuleNotFoundError`.
- ADR-108:41 carries a `## Decision Drivers` section, D1 to D5.
- ADR-108:80 states that a NO-REGEN file is skipped by both the write path and `--validate`.
- ADR-108:125 prices the in-tree expander against chevron, ADR-108:167 and `:168` add the
  portability scanner and D4 rows, `:182` rolls back the A0 edits, `:191` names issues #5686 to
  #5691, and `:198` replaces the unresolvable Serena memory citation.

### New findings in round 2

**The control on widening is not owner-gated.** Three seats reached this independently and one
blocked on it. ADR-108:62 calls `tests/build_scripts/test_skill_templates_pilot_scope.py` "the
control on widening" and says its docstring records that adding a name is an owner decision. The
test does not exist yet, which is correct for A1, but `.github/CODEOWNERS` carries five entries and
none covers `templates/skills/` or `tests/build_scripts/`; the only skills entry is
`/.claude/skills/review/references/ @rjmurillo`. A contributor adding a ninth template edits the
`PILOT` constant in the same pull request and the suite stays green. Verified by reading
CODEOWNERS in full.

**The NO-REGEN path silences the drift gate by design and reports at NOTICE.** ADR-108:80 states a
protected file that has diverged is "the author's declared state, not a gate failure".
`build/scripts/regen_guard.py:36-38` sets `_HEAD_BYTES = 4096` and `_HTML_TOKEN = b"<!-- NO-REGEN"`,
a raw substring match in the first 4 KiB with no closing token, and the module also supports a
sidecar form (`REASON_SIDECAR`) the record does not mention. For eight files Claude Code loads
directly, that is a self-declared, quietly reported exemption from the only gate the class has.

**The skill-authoring documents still tell contributors the opposite.** `.claude/skills/CLAUDE.md`
states "`SKILL.md` is the contract per skill" and mentions no template layer; a repository-wide
grep for `templates/skills`, `template-owned`, and `ADR-108` returns nothing in that file, in
`.agents/steering/claude-skills.md`, or in `.agents/governance/SKILL-CREATION-CRITERIA.md`. The
Impact table names `GENERATOR-FILES.md` at `:158` and none of these three. The first of them ships
inside the plugin, so it is the document a contributor reads before hand-editing a rendered file.

**Two citations will fail the repository's own citation gate once committed.** Found by the
orchestrator, not by a seat. ADR-108:160 cites `.agents/architecture/ADR-107-...md:61-62` with a
literal ellipsis in the filename; `check_citation_freshness.py` skips only slashless names, and a
slashed path absent from HEAD returns a `Finding` reading "cited file not tracked at HEAD".
ADR-108:198 cites `build/scripts/copilot_body_translation.py:9-14` in a sentence whose anchors are
`cd0f9561d` and `.serena/memories/decisions/`, neither of which appears at those lines, so
`_anchor_finding` reports "none of the cited anchors appear at lines 9-14". Both were measured by
running the gate's own matcher against the two lines. The gate currently examines zero citations
because the change is staged and uncommitted.

**Smaller findings.** The compile plan at ADR-108:180 lists no case for a template filename that
resolves outside `.claude/skills/`, though that name is spliced straight into the `allowed_paths`
set described at `:68`. The "About 40 lines" figure for the in-tree expander at `:125` carries no
evidence label while the chevron figure beside it carries one; it is taken from
`REQ-021-skill-guidance-excerpts.md:96`, which calls it an estimate. The trailing "which" at `:59`
can read as saying the mirror is unchanged rather than the translation. ADR-108:111 still says the
outcome "needs a template layer skills do not have"; the declined design at
`DESIGN-020-skill-guidance-excerpt-sync.md:154`, inside its "Declined alternative" section that
begins at `:152`, also pins excerpts under `templates/skills/partials/`, so the real difference is
which file is canonical. The record names the byte-growth regret at `:144` but ties it to no
trigger: a grep for `revisit`, `trigger`, `5400`, `5492`, and `4871` in the record returns nothing,
and the deferred cut is tracked only in
`.agents/plans/active/5706-skill-guidance-excerpts.md:109`. The Context constraint table at `:33`,
`:35`, and `:36` quotes the pre-amendment wording from lines that now carry the amendment, so a
reader opening a cited line sees the exception inside the sentence presented as the blocker; the
quotes still satisfy the citation gate's anchor matching, so this is reader-facing only. Four spec
files cited at `:196` keep "excerpt" in their filenames while their frontmatter titles describe the
template design.

### Findings rejected or corrected

- **Analyst: ADR-108:106 misstates the direction of the 2025-12-15 incident.** Rejected. The seat
  read `.claude/skills/ai-agents-change-control/SKILL.md:106`, an anti-pattern table row reading
  "Editing a generated tree to silence a drift gate | Inverts the source of truth (2025-12-15
  incident, reverted)". Line 56 of the same file reads "on 2025-12-15 an agent \"fixed\" a drift
  failure by editing the canonical source to match the generated output; the commit was reverted".
  ADR-108 quotes line 56 faithfully. The contradiction is inside the skill file, not in this
  record, and is flagged below.
- **Independent-thinker: the declined design specifies a partials tree in five places.**
  Corrected. Four lines of `DESIGN-020-skill-guidance-excerpt-sync.md` contain
  `templates/skills/partials`, and only `:154` sits inside the declined-alternative section that
  begins at `:152`. The other three describe the chosen design. The finding stands on `:154` alone.
- **Analyst and security: the chevron measurements and the issue quotes are unverifiable.**
  Cleared by the orchestrator in round 1 and unchanged: chevron 0.14.0 is 746 lines across five
  modules with no declared dependencies, and both render calls return `AB`. Both issue quotes were
  read with `gh issue view`.
- **Round-1 item on ADR-108:111 ("a template layer skills do not have").** The orchestrator had
  provisionally dropped this as defensible, since `templates/skills/` does not exist in the tree.
  The independent-thinker seat's evidence at `DESIGN-020:154` restores it as a P2: the sentence
  describes the wrong differentiator, not a false fact.

### Adjacent defects flagged, not fixed

- `.claude/skills/ai-agents-change-control/SKILL.md` describes the 2025-12-15 incident in opposite
  directions at `:56` and `:106`. The same file cites `build/scripts/build_all.py:962-967` as the
  code that fails the build on a `.claude/` write; those lines are the `OWNED_PREFIXES` tuple.

### Verdict

Revision 2 closed every round-1 Block condition, verified against the amended files rather than
against the record's description of them, and four seats moved to Accept. Consensus was not
reached: the security seat opened a new Block on two controls the revision itself introduced, the
same-pull-request editability of the pilot-scope constant and the NO-REGEN exemption from the drift
gate. Both unblock conditions are additive and neither reopens the owner's decision D1. The record
stays `proposed`.

## Round 3

Revision 3 was reviewed by the same six seats under the same rules: the record's path and the
Zimmermann checklist path, nothing else, no seat shown another seat's findings and no seat told
what changed or that earlier rounds existed. Every claim below was re-verified against the tree by
the orchestrator.

### Agent positions

| Agent | Round 3 vote | Position |
|-------|--------------|----------|
| critic | Accept | Every checked citation matches; the generated ADR index is stale and the skill-size gate is missing from the Impact table, neither a design defect |
| architect | Disagree and commit | Section 4 states two severities for the same event, and the class's membership key carries no name-format constraint before it reaches the write allowlist |
| analyst | Disagree and commit | Two Context-table quotes read as pre-amendment text against lines this record's own change set already rewrote; one estimate carries no evidence label |
| independent-thinker | Disagree and commit | The code-owner control is not load-bearing today, and the rationale for paying the amendment cost leans on a migration the record itself defers |
| high-level-advisor | Disagree and commit | The generated ADR index disagrees with the record's own Decision text, and A0's own task file names index regeneration as its done-condition |
| security | Block | The drift signal this record exists to make a gate does not state whether WARN exits non-zero, and CODEOWNERS does not protect itself |

### Round-2 findings verified closed

- `.github/CODEOWNERS` carries `/templates/skills/` and
  `/tests/build_scripts/test_skill_templates_pilot_scope.py` under `@rjmurillo`, staged in this
  change set. ADR-108:62 names both controls and states that neither is a hard gate unless the
  branch ruleset requires code-owner review. The Impact table gains a CODEOWNERS row at `:167`.
- ADR-108:80 adds the WARN treatment for a sentinel under a template-owned file, in both modes and
  both forms, and names the `.noregen` sidecar. `regen_guard.py:63` confirms the sidecar is
  `path.with_suffix(path.suffix + ".noregen")`.
- The Impact table gains a Direct row at `:168` for `.claude/skills/CLAUDE.md`,
  `.agents/steering/claude-skills.md`, and `.agents/governance/SKILL-CREATION-CRITERIA.md`.
- `:160` spells the full ADR-107 filename, and `:200` quotes text that is actually at
  `copilot_body_translation.py:9-14` and carries no other anchor. Measured by running the citation
  gate's own matcher over all 20 citations in the record: zero gate-relevant problems, against two
  in revision 2.

### New findings in round 3

**Section 4 states two severities for one event.** ADR-108:80 says a rendered file carrying a
NO-REGEN sentinel "is skipped with a NOTICE by both the write path and `--validate`" and, two
sentences later, that such a file "is reported at WARN by both the write path and `--validate`".
Same subject, same two checkers, contradictory severities. The architect and security seats found
this independently. `generate_skills.py:105-109` prints NOTICE today, so the WARN claim is the new
and unreconciled half.

**The WARN carries no stated exit code.** The security seat blocked on this. Driver D4 at `:46`
says drift is a gate and not prose, and the motivating incident at `:106` is an undetected hand
edit reaching the trunk, so the exit behavior of this exact signal is the load-bearing part.
Nothing in the record says whether WARN makes `--validate`, `--check`, or the pre-PR gate exit
non-zero, and the compensating mechanism named beside it, the A2 byte report, is a one-time pull
request deliverable rather than a continuous check.

**The Status sentence and the Decision disagree on how many texts are amended, and the generated
index inherits the older count.** ADR-108:17 reads "This record amends ADR-107 settled property 1
and REQ-003-010 for exactly one artifact class", naming two texts. ADR-108:51 reads "amend the
three texts that forbid it: REQ-003-010, REQ-003 decision D4, and ADR-107 property 1". The staged
`.agents/architecture/README.md:191` carries "amend the two texts that forbid it", and
`uv run python build/scripts/generate_adr_index.py --check` reports
`DRIFT: .agents/architecture/README.md differs from generated output`. Two seats reported the index
drift; the Status sentence is its root cause, because the index blocker cell is generated from that
paragraph. `TASK-024-skill-excerpt-parity-gate.md:24` names a green `build_all.py --check` as A0's
own done-condition, and it is red.

**CODEOWNERS does not protect itself.** `.github/CODEOWNERS` carries seven entries and none covers
`.github/CODEOWNERS`. A change that adds a ninth template can delete the two entries meant to
route it for review, in the same diff.

**Smaller findings.** The class's membership key has no name-format constraint: `<name>` is
whatever precedes `.SKILL.md.tmpl` and is spliced straight into the `allowed_paths` set at `:68`,
while partial slugs do carry a pattern; the A1 conformance list at `:182` has no case for a name
containing `..` or a separator. `scripts/validation/skill_size.py` is absent from the Impact table
although it blocks at 500 lines and warns at 300 (`:61-62`), and the pilot files run 103 to 205
lines today, so bundled guidance consumes real headroom; the A2 report is specified in bytes only.
The "About 40 lines" figure for the in-tree expander at `:125` carries no evidence label while the
chevron figure beside it carries one; it is an estimate taken from
`REQ-021-skill-guidance-excerpts.md:96`. The record names the byte-growth regret at `:144` but ties
it to no trigger other than the calendar `review-by`. The Alternatives table's reason for paying
the amendment cost cites "the path to migrating all 111 skills", which section 7 at `:92` declares
out of scope pending a separate owner decision. Three seats again flagged `:140` as pointing at the
docstring of `_translate_includes` rather than the rewrite at `:144-148`.

### Findings rejected or corrected

- **Independent-thinker: `main` carries zero branch protection, so CODEOWNERS enforces nothing.**
  Corrected, conclusion kept. The legacy endpoint returns 404 because protection is expressed as a
  ruleset: `repos/rjmurillo/ai-agents/rulesets/11104075`, "Copilot review for default branch",
  enforcement active, targeting the default branch. Its `pull_request` rule carries
  `require_code_owner_review: false` and `required_approving_review_count: 0`, so code-owner review
  is indeed not required today. The seat's conclusion holds and its stated evidence does not. ADR-108:62
  claims only that the controls are not hard gates unless the ruleset requires code-owner review,
  which the ruleset data confirms is accurate rather than overclaimed.
- **Analyst: two Context-table quotes fail an exact match against their cited lines.** Corrected to
  reader-facing only. Measured with the citation gate's own matcher: for ADR-108:33 the anchors are
  `claude/<artifact>/` and the quoted sentence, and `_anchor_matches` returns True against
  `REQ-003-multi-tool-artifact-build.md:358-359` as amended. The gate passes. What remains is that
  a reader opening a cited line sees the exception clause inside the sentence the table presents as
  the blocking constraint, which is worth a parenthetical and is not a gate failure.
- **Critic ran `generate_adr_index.py` against the working tree and restored it.** Verified: `git
  diff` is empty and `.agents/architecture/README.md` remains staged with no unstaged change. The
  seat was told to read only; it mutated and restored. Recorded because the restore was clean and
  the finding it produced is real.

### Verdict

Revision 3 closed every round-2 condition, verified against the amended files and by running the
citation gate's own matcher over the record. Consensus was not reached for the third round. The
security seat blocked on one sentence: the drift signal that driver D4 calls a gate does not say
whether it exits non-zero. The architect seat found the same sentence contradicts itself on
severity. Both are text fixes inside section 4, and neither reopens the owner's decision D1. The
record stays `proposed`.

## Round 4

Revision 4 was reviewed by the same six seats under the same rules: the record's path and the
Zimmermann checklist path, nothing else, no seat shown another seat's findings and no seat told
what changed or that earlier rounds existed. Seats were told to read only and to run no command
that writes to the tree. Every claim below was re-verified against the tree by the orchestrator.

### Agent positions

| Agent | Round 4 vote | Position |
|-------|--------------|----------|
| architect | Accept | Every governing-artifact claim verifies against the tree; three precision gaps in section 4 and one citation anchor remain |
| security | Accept | The sentinel can no longer silently exempt a file, the allowlist stays precise, and the four residual items belong to the A1 review |
| high-level-advisor | Accept | A0 is correctly shaped: three amended texts, a bounded class, and no runtime change, with a sequenced rollback |
| critic | Disagree and commit | The record describes its own cited design document as the record of the declined alternative when that document is primarily the chosen design, and the rollback list omits files the same change set stages |
| independent-thinker | Disagree and commit | The safety argument rests on the grammar check, and a reproduced chevron behavior defeats it in a way the grammar check cannot see |
| analyst | Disagree and commit | Three citation-precision defects, one of them in the historical rationale |

Consensus reached: six of six seats at Accept or Disagree-and-Commit, no Block.

### Round-3 findings verified closed

- Section 4 at `:80` now states one severity: the skip "is reported at WARN, elevated from the
  NOTICE the copy path prints". The earlier NOTICE claim for the same event is gone.
- The same line states the exit behavior: the sentinel "makes the compile exit 1 in every mode: the
  write path, `--validate`, `build_all.py` and its `--check`, and therefore the pre-PR gate and
  CI", names the author's resolution (delete the template or the sentinel), and records the
  divergence from issue #5706 step 10.
- `:17` now names three texts, ADR-107 property 1, REQ-003-010, and REQ-003 decision D4.
  `.agents/architecture/README.md:191` carries the matching three-text summary,
  `generate_adr_index.py --check` reports `OK ... (108 ADR record(s))`, and
  `build_all.py --check` exits 0 with no `VIOLATION`, `DRIFT`, `STALE` or `FAIL` line in its 334
  lines of output. The working tree is unchanged by that run.
- The citation sweep is clean for the second round running: 20 citations, zero gate-relevant
  problems, measured with `citation_anchors._CITATION` and `_anchor_matches` over the record.

### New findings in round 4

**A partial with no trailing newline glues the next line, and nothing in the design catches it.**
This is the round's strongest finding and the orchestrator reproduced it. With `chevron==0.14.0`,
`render("Line before.\n{{> no-dashes}}\nLine after.\n", {}, partials_dict={"no-dashes": "Use
commas, periods, colons, parentheses, hyphens, or restructure."})` returns
`'Line before.\nUse commas, periods, colons, parentheses, hyphens, or restructure.Line after.\n'`.
Adding one trailing newline to the partial restores the separator. The corrupted output contains
no `{{`, so the record's two stated defenses at `:58`, the restricted grammar and the
literal-brace scan, both pass. The partials in DESIGN-020 are specified as substrings of rule
files, which carry no trailing newline of their own, and a repository-wide search of ADR-108,
DESIGN-020, TASK-024, TASK-025 and TASK-026 returns no trailing-newline requirement. Because the
drift gate compares against the committed rendered file, a first render carrying this defect
becomes the baseline the gate then protects. The fix belongs in the A1 grammar check and the
DESIGN-020 test matrix, not in this record's decision.

**The record undercounts the sentinel forms.** `:80` says the sentinel is recognized "in either
form it recognizes (the in-file `<!-- NO-REGEN` token in the first 4 KiB, or the `.noregen`
sidecar)". `build/scripts/regen_guard.py:32-38` defines three: `REASON_HTML_COMMENT`,
`REASON_HASH_COMMENT` with `_HASH_TOKEN = b"# NO-REGEN"`, and `REASON_SIDECAR`. The hash-comment
form is a raw byte match, so a literal `# NO-REGEN` heading inside a rendered `SKILL.md`'s first
4 KiB protects the file. Two seats found this independently. The consequence is a loud build
failure rather than a silent one, because of the exit-1 rule this revision added.

**The record describes its own design document as the record of the declined alternative.**
`:17` says the declined alternative "is recorded in
`.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md`" and `:111` says "The
no-amendment alternative exists (DESIGN-020)". That file's frontmatter title is "Mustache-compiled
pilot skills under a template-owned class" and its own line 27 says "This document describes the
chosen design. The declined alternative is kept at the end for the record." The declined design
occupies its closing section from `:152`. The statements are imprecise rather than false, which is
why this is recorded at P2 and not at the P1 the seat assigned.

**The rollback list omits files the same change set stages.** `:184` ends "Nothing else moves",
while `git status --porcelain` shows the A0 change set also stages `.github/CODEOWNERS` and six new
spec, plan and task artifacts. A rejection before A1 would leave CODEOWNERS pointing at a
`templates/skills/` directory and a pilot-scope test that never exist.

**Smaller findings.** The exit-code taxonomy is not stated as a rule, so a reader cannot predict
which code a ninth failure mode takes. The REQ-003-010 quote at `:66` is introduced with "now
reads" and stops before the paragraph's third sentence. The CODEOWNERS entry and the amended
REQ-003-010 text both describe things no code honors until A1, which is correct for a policy-only
slice but not stated. `scripts/validation/check_skill_md_portability.py` is in the Impact table but
no CI workflow row names where the drift gate runs server-side, although
`.github/workflows/validate-generated-agents.yml` does run `build_all.py --check` today. The
restricted grammar's exit 2 cannot come from chevron, which renders `{{#section}}` natively, so A1
must scan the raw template before rendering. Three seats again flagged `:140` as the docstring of
`_translate_includes` rather than the rewrite at `:144-147`.

### Findings rejected or corrected

- **Analyst: `:106` reverses the direction of the 2025-12-15 incident.** Rejected for the second
  time, on the same evidence. The seat reported searching the whole skill file and cited
  `.claude/skills/ai-agents-change-control/SKILL.md:106`. Line 56 of that same file reads: "on
  2025-12-15 an agent \"fixed\" a drift failure by editing the canonical source to match the
  generated output; the commit was reverted". ADR-108 quotes line 56. The file states the incident
  in both directions, at `:56` and at `:106`, and that contradiction is the defect, in the skill
  file and not in this record. It is flagged below for the third round running.
- **Critic: the DESIGN-020 mischaracterization is P1.** Downgraded to P2. DESIGN-020 does record
  the declined alternative, in its closing section, so the references are imprecise rather than
  wrong.
- **Independent-thinker: the exit-1 rule is a repo-wide hard block with an unexamined blast
  radius.** Recorded as a P2 observation rather than a defect. The record states the resolution
  path at `:80` and the owner chose the strict reading deliberately, recording the divergence from
  issue #5706 step 10. Whether a scoped failure would be better is an A1 implementation question.
- **Security: no CI workflow is named for the drift gate.** Partly answered.
  `.github/workflows/validate-generated-agents.yml` runs `build_all.py --check` today, so the
  record's "pre-PR and CI" claim at `:112` and `:137` has a server-side path. What is missing is
  the workflow row in the Impact table, not the coverage.

### Adjacent defects flagged, not fixed

Both are in `.claude/skills/ai-agents-change-control/SKILL.md` and outside this record.

- The 2025-12-15 incident is described in opposite directions at `:56` and `:106`.
- `:56` cites `build/scripts/build_all.py:962-967` as the code that fails the build on a `.claude/`
  write; those lines are the `OWNED_PREFIXES` tuple.

### Verdict

Consensus reached on revision 4: three Accept, three Disagree-and-Commit, no Block. Every Block
condition raised in rounds 1, 2 and 3 is verified closed against the amended files, the generated
index, and the repository's own citation gate. The one P1 carried forward, a partial without a
trailing newline silently joining the line after it, is a defect in the A1 grammar check and the
DESIGN-020 test matrix rather than in this record's decision, and it is cheap to close before
TASK-025 starts. The record ships as `proposed` with the dissent above recorded.

## Post-consensus edits (2026-09-11, after round 4)

Two edits to the record after the round-4 vote, neither changing a decision:

- The round-4 P1 (partial without a trailing newline) was folded into section 1 as a
  configuration error, exit 2, with the probe result, and the sentinel forms in section 4 were
  corrected to the three `regen_guard.py` recognizes. Rollback in Implementation Notes now names
  the CODEOWNERS entries and the spec artifacts.
- Two Impact-table citations (`REQ-003-...md:358-361` and `generated-artifacts.md:196`) gained
  backticked anchor text so `scripts/validation/check_citation_freshness.py` can match them at
  the cited lines. No line number or claim changed.
