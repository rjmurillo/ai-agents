<!-- # taste-lint: ignore file-size, append-only review record; rounds are cited by number from ADR-109 and its pull request; splitting breaks those references and the audit continuity. -->
# ADR Debate Log: Template-First Plugin Distribution

Record under review: `.agents/architecture/ADR-109-template-first-plugin-distribution.md`
Tracker: none assigned at review time; issue #5282 (ADR-052's migration tracker) is the item this record re-scopes. Branch: `feat/adr-109-template-first-distribution`, worktree `/home/richard/worktrees/adr109`.
Tree state at review: HEAD `5cad780a2`, the record untracked and its four cross-references (ADR-052, ADR-107, REQ-003, the ADR index) modified and unstaged, read from disk.

## Summary

- Rounds: 2
- Seats: 6 (architect, critic, independent-thinker, security, analyst, high-level-advisor)
- Round 1 outcome: **1 Accept, 5 Disagree-and-Commit, 0 Block.** Consensus on the vote; one P0 found by the orchestrator's gate run and nine P1s from seats required a revision before the record could stand as `proposed`.
- Round 2 outcome: **6 Accept, 0 Disagree-and-Commit, 0 Block. Consensus reached.**
- Disposition: every round-1 P0 and P1 was folded into revision 2 in text; every P2 was folded as well rather than deferred, because no P2 needed a GitHub issue to resolve and this review was not authorized to file one. Objections to the owner's direction were recorded as noted, not as blockers.
- Final status: `proposed`, `implemented: false`, `supersedes: []` until acceptance, `review-by: 2027-03-11`.

Constraint fixed before the debate: the repository owner decided the direction on 2026-09-11 (template-first for every plugin artifact class, one Claude plugin from `src/claude/`, binplace into `.claude/` and `.github/`, the record first and then one PR per class). Seats could challenge evidence, wording, missing consequences, wrong citations, and migration mechanics. Each seat received the record's path, the Zimmermann checklist path, the Phase 0 related-work list, and that constraint, and nothing else. None saw the reasoning that produced the record, and none saw another seat's findings. Every claim below was re-verified against the tree by the orchestrator before it entered this log; three seat claims were corrected and are recorded under "Findings rejected or corrected".

Phase 0 related work: open issues #5282, #5307, #5686, #5688, #5689, #5294, #5298, #4871, #5196, #5200, #5292; open PR #5741 (second-wave skill templating); closed issues #1918 and #2267 (prior proposals for the same mechanism, closed 2026-06-03 and 2026-06-04 on the REQ-003 D4 and REQ-003-010 premise). None of the open PRs implements this record.

## Agent positions

| Agent | Round 1 vote | Load-bearing objection |
|-------|--------------|------------------------|
| architect | Accept | No `review-by` field where both cited siblings carry one; five related issues absent from References |
| critic | Disagree and commit | Section 2 silently moves `src/claude/` from flat agent files to an `agents/` subdirectory; section 3 claims `--check` over all of `.github/prompts/` when 12 of 33 files have a compile step |
| independent-thinker | Disagree and commit | D6 and the Positive consequence say "customers" when `.github/hooks/*.json` benefits this repository's sessions and the cloud agent; the cheapest fix for D2, a symmetric co-change gate, is never named or rejected |
| security | Disagree and commit | The binplace manifest is the `.claude/` write allowlist and has no CODEOWNERS entry; CODEOWNERS is not a merge gate under the current ruleset; the per-skill symlink and containment checks do not extend to other classes on their own |
| analyst | Disagree and commit | The record narrates ADR-052 and ADR-107 amendments as future work the tree already carries; the REQ-003-010 quote is not the current text; the "loads only" phrase is cloud-agent text applied to the interactive CLI |
| high-level-advisor | Disagree and commit | B3 proposes 93 skills where ADR-108 needed five PRs for 18; no per-class stop-doing instruction; dependent issues not addressed by number |

## Key issues found in round 1

**The record fails the repository's own lifecycle gate (P0, orchestrator).** `uv run python scripts/validation/check_adr_lifecycle.py` reported `proposed-cannot-supersede: 0 -> 1` against the record: `status: proposed` with `supersedes: [ADR-052]`. The check is defined at `scripts/validation/check_adr_lifecycle.py:72`, "a `proposed` record may not declare `supersedes`". The working tree compounded it: ADR-052 was already flipped to `status: superseded`, `superseded-by: ADR-109`, and the ADR index had moved ADR-052 to Retired and re-pointed ADR-036's terminal superseder to ADR-109, all under a record the owner has not accepted. No seat ran the gate. Fixed in revision 2: frontmatter `supersedes: []`; Status and section 5 state that supersession takes effect at acceptance and cite the check; ADR-052 restored to `accepted` with a Status note naming this record as proposed, placed after the accepted paragraph because the gate's `prose-frontmatter-agree` check requires the first Status line to match the enum; index rows restored. The gate now passes all eight checks across 109 records.

**`src/claude/` changes shape and the record did not say so (P1, critic).** `ls src/claude` shows agent files flat at the plugin root, and `build/scripts/validate_install_parity.py:141` matches `^src/claude/(?P<name>[^/]+)\.md$`. Section 2 listed `agents/` as a subdirectory of the rendered tree with no mention of the move. Revision 2 states the move in section 2, adds a Consequence bullet, updates the Impact row for the parity validator, and puts the move in B1.

**`--check` over `.github/prompts/` was overstated (P1, critic).** 33 files sit there and 12 are `pr-quality-gate-*`, the only prompt subset with a compile step (`build/scripts/generate_pr_quality_prompts.py`). Revision 2 scopes `--check` to manifest-named paths and says the other 21 stay hand-maintained.

**D6 and the Positive consequence name the wrong beneficiary (P1, independent-thinker).** `.github/hooks/*.json` is Copilot's repository hook location (`official-hook-contracts.md:48`); the cloud agent loads only it and ignores installed plugins (`:291-299`). Writing it helps this repository's own sessions and cloud-agent runs. The seat also argued plugin consumers already get working hooks through the plugin channel; that part was wrong, see below. Revision 2 rewrites Context, D6, and the Positive bullet, and adds ADR-097 to Related Decisions.

**The Rationale table omitted the cheapest fix for D2 (P1, independent-thinker).** A symmetric co-change gate on `validate_install_parity.py` closes the 31% agent gap with no canonical-source move. Revision 2 adds it as Alternative E, rejected because it covers agents only and the owner directive names every class. Recorded as an alternative, not as an objection to the direction.

**The write allowlist moves into an unowned data file (P1, security).** Revision 2 makes the binplace manifest a CODEOWNERS entry in B1, the PR that introduces it, and names the ruleset fact from `.agents/critique/ADR-108-debate-log.md:378-383` (`require_code_owner_review: false`) so nobody reads a CODEOWNERS row as a merge gate. Whether to require code-owner review before B4 writes executable hook configuration is left to the owner and recorded in B4.

**The symlink and containment checks are skills-scoped (P1, security).** `build/scripts/skill_templates.py:183-244` checks `.claude/skills/<name>/` only; the tree-level guard all classes share is `build_all.py`'s unreachable-owned-path check from issue #4632. Section 6 said the checks "extend to every class". Revision 2 makes each of B1 through B4 responsible for its own checks with tests, and adds the symlink and out-of-root cases to the conformance list.

**Sizing and instructions (P1, high-level-advisor).** B3's 93 skills against ADR-108's five-to-eight-file PRs (#5731, #5739, #5740) and `.claude/rules/claude-agents.md:27`; no one-line stop-doing instruction per class; #5307, #5686, #5688, #5689, #4871 absent. Revision 2 lets a class land in batches without changing the class order, adds a stop-doing bullet per class, and lists every related issue with a disposition. The reading of "one PR per class" as one PR series per class is flagged for the owner under "Noted against the owner direction" below.

**Tense against the staged text, and two quotes (analyst).** ADR-107 property 1 (`:62-63`) and its Related Decisions bullet (`:662-663`), REQ-003 D4 (`:80`), D9 (`:85`), and the REQ-003-010 note (`:367-370`) already carry conditional clauses naming this record as proposed, while sections 5 and 6 read as future work. The REQ-003-010 quote dropped "any other path under", which ADR-108's amendment added (`REQ-003-multi-tool-artifact-build.md:360`). "Loads only `.github/hooks/*.json`" is the cloud-agent bullet, not a statement about the interactive CLI. All three fixed in revision 2, with the conditional clauses cited by line and the acceptance edit described.

**Smaller findings, all folded.** No `review-by` field where ADR-107 and ADR-108 carry one (architect, security, high-level-advisor): added, `2027-03-11`. The lib import-breakage claim was labeled `hypothesis` when a two-minute measurement exists (independent-thinker, analyst): measured, 39 `from scripts.<pkg>` lines across 17 files inside the three packages and 263 lines across 138 files outside them, 40 relative imports in the `.claude/lib/` copies, regex recorded inline, label upgraded. Rollback omitted D9 and ADR-052's Status prose (critic) and said nothing about byte-identical restoration or a consumer who updated during a B6 revert window (security, high-level-advisor): rollback now names every B0 file, a rebuild plus `--check` per revert, and the one-way window. `scripts/hook_utilities/` and `scripts/github_core/` lack the CODEOWNERS parity `ai_review_common` has (`.github/CODEOWNERS:20-21`) (security): added to B5. "One atomic operation" said nothing about a live session holding loaded files (independent-thinker): section 3 now says write atomicity, not live reload. Hooks and settings are JSON and Python, not markdown with frontmatter, so ADR-108's grammar does not transfer (high-level-advisor): B4 row now says so. Issues #1918 and #2267 proposed this mechanism and were closed on a premise this record amends (orchestrator, Phase 0): added to Prior Art. `templates/platforms/` listing omitted `visual-studio.yaml` (orchestrator): fixed.

## Findings rejected or corrected

- **Independent-thinker: installed-plugin consumers already receive working hooks through `src/copilot-cli/hooks/hooks.json`.** Corrected. Both `.claude/hooks/hooks.json` and `src/copilot-cli/hooks/hooks.json` read `"hooks": {}`; ADR-097 retired the last plugin-registered event (`.agents/architecture/ADR-097-zero-tool-use-hooks.md:96-98`). The overstatement finding stands on the repository-versus-cloud-agent channel distinction, and the record now says plugin consumers gain a hook only when a template registers one.
- **Architect and high-level-advisor: the record's tense and Impact table agree with the tree.** Not accepted. The tree's flip of ADR-052 to `superseded` was itself the defect the lifecycle gate reports, and the record's sections 5 and 6 described conditional staged text as unconditional. The analyst seat had it right.
- **Analyst: 24 and 3 absolute imports in `github_core` and `hook_utilities`.** Corrected to the measured 39 lines across 17 files inside all three packages (the seat had no shell and grepped two packages by a narrower pattern). The conclusion, that the hypothesis was cheaply verifiable and directionally correct, stands.
- **High-level-advisor: a "≤10 files per PR" convention at `claude-agents.md` MUST-4.** Verified at `.claude/rules/claude-agents.md:27` as a SHOULD for skill additions; cited as such in section 7.

## Adjacent defects flagged, not fixed

Outside this record and not edited.

- `.github/plugin/marketplace.json` describes `project-toolkit` as "generated from Claude canonical sources"; the wording goes stale once templates are canonical. Recorded as a Low Impact row for B6.
- `.claude/hooks/hooks.json`'s description says "membership lives in dispatch_groups.json (plugin-* groups)" while its `hooks` object is empty; ADR-097 explains the emptiness but the description reads as if registrations exist.

## Noted against the owner direction, not blockers

- Critic: the record bundles four separable decisions (per-class canonicalization, marketplace consolidation, the lib copy-hop fix, and a new `.github/hooks/` capability) under one Decision Drivers list and one rollback chain. Noted; the owner directed one record, and the per-class Implementation Notes keep each class's gate separable.
- Independent-thinker: a symmetric co-change gate would close the measured agent gap without moving any canonical source. Recorded as Alternative E and rejected on the directive.
- High-level-advisor: "one PR per class" is read in revision 2 as one PR series per class so that B3's 93 skills can land in batches. If the owner meant a single PR, section 7 and the B3 row need one sentence changed; the class order is unaffected either way.

## Not resolved, carried forward

- The record enforces nothing until B1; every mechanism in sections 1 through 4 describes code that does not exist yet, and the Implementation Notes table scopes each to a PR.
- Whether the default-branch ruleset should require code-owner review before B4 writes executable hook configuration is the owner's decision, named in Consequences and left open.
- PR #5741 will change the "18 of 111" count on merge; the record says so in References.

## Verdict

Round 1: one Accept and five Disagree-and-Commit, no Block. The vote met the consensus bar, but the record could not stand as written: the repository's lifecycle gate fails it, and the seats' P1s were each a text fix inside the owner's direction. Revision 2 folds every P0, P1, and P2 and passes the gate. Round 2 is recorded below.

## Round 2

Revision 2 was put back to the same six seats with a summary of the changes and each seat's own round-1 concerns marked addressed. Seats were told to re-read the record from disk and verify before asserting, read-only. Every claim below was re-verified against the tree by the orchestrator.

### Agent positions

| Agent | Round 2 vote | Position |
|-------|--------------|----------|
| independent-thinker | Accept | All four concerns addressed and verified: D6 citations and the empty `hooks.json` correction hold, Alternative E present, import count reproduced independently (302 lines across 155 files, matching 39+263 and 17+138), live-reload sentence present. Did not re-verify the items other seats raised; recorded as unreviewed, not cleared |
| critic | Accept | Layout move disclosed in section 2, Consequences, Impact, and B1 and matches `ls src/claude`; prompts split verified by count; rollback names every B0 target; the lifecycle fix matches ADR-052's restored frontmatter and note; six further citations spot-verified |
| security | Accept | Manifest CODEOWNERS entry lands in B1 with the manifest; the ruleset fact is stated and the pre-B4 decision assigned to the owner; per-class symlink and containment checks are a MUST with the conformance cases listed; lib CODEOWNERS parity in B5; rollback carries rebuild plus `--check`; `review-by` present |
| architect | Accept | Every spot-checked claim matches the tree, including import counts, line-anchored quotes, and file counts; both round-1 P2 gaps resolved with substantive content |
| high-level-advisor | Accept | Six round-1 concerns closed with mechanism, not assertion; two owner notes recorded under "Noted against the owner direction": confirm the "one PR series per class" reading before B3, and decide the ruleset gap before B4 |
| analyst | Accept | Citation audit: all verified, including the reproduced import graph (39/17 inside; 263/138 outside, with per-package and per-tree breakdown matching); no blocking issues, no dissent |

Consensus reached: six of six seats at Accept, no Block.

### Round-1 findings verified closed

Recorded per seat above and re-verified by the orchestrator: lifecycle gate green (`[PASS] 0 violation(s) across 109 ADR record(s)`); every `path:line` citation in revision 2 resolved by `sed -n` to a line carrying the cited text (list in the review report); no em or en dash and no banned word in the record, in ADR-052's changed lines, or in the index's changed lines.

### New findings in round 2

- Critic (cosmetic, not a defect): Alternative A's cell says the two directions "cannot both be the target state", which reads in tension with the acceptance-time deferral in section 5. Section 5 resolves it; no edit made.

### Verdict

Consensus reached on revision 2: six Accept, no Disagree-and-Commit, no Block. The round-1 P0 (lifecycle gate) is closed and the gate passes; every round-1 P1 is closed in text and re-verified by the seat that raised it and by a second seat; every round-1 P2 was folded rather than deferred. Three items go to the owner, none blocking: the "one PR series per class" reading of the directive before B3 starts, the ruleset code-owner-review decision before B4, and the reading of "one PR per class" against B6's one-way window. The record ships as `proposed`, `supersedes: []`, with ADR-052 at `accepted` until the owner's acceptance edit flips both.

## Post-consensus edits

- 2026-09-11: five `path:line` citations in the record (sections 5, 6, and 7) re-anchored so a backtick span in each citing sentence appears at the cited line; the citation-freshness pre-push gate reported them stale. No decision text changed.
  Re-anchoring note: the gate reads one citation per line; the section 6 amendment list became bullets for that reason.
