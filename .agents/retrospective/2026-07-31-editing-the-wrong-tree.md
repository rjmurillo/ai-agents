# Editing the Wrong Tree: A Claude-Only Rule That Would Never Reach Copilot

Date: 2026-07-31
Scope: `orchestrator` agent, cross-harness generation topology

## Summary

While adding a concurrency-wave discipline to the orchestrator agent, the first
edit landed in `.claude/agents/orchestrator.md`. That file is a hand-maintained
self-host copy, not the generator source. Had it shipped, the new rule would
have reached Claude users and no Copilot user, and it would have silently
deepened a cross-harness divergence that has been in place since April.

The error was caught before commit. The catch was accidental in origin and
deserves a cheaper detector.

## Failure mode classification

Class 1, Context Reading Failure (`.agents/governance/FAILURE-MODES.md:32`).

The authority on which tree is canonical is
`.agents/governance/GENERATOR-FILES.md`. It was not read before the edit. The
edit proceeded on an assumption carried from prior sessions ("the agent lives
in `.claude/agents/`") rather than on retrieval.

This is the same shape as the class description: the instruction lived in a
file the agent did not read.

## Timeline

1. Located the orchestrator agent and confirmed it lacked a wave-width bound.
2. Edited `.claude/agents/orchestrator.md` directly.
3. Ran `build/scripts/build_all.py` out of habit, not suspicion.
4. Noticed the run reported `Written: 2` while no mirror file changed.
5. Read `.agents/governance/GENERATOR-FILES.md` and found
   `templates/agents/orchestrator.shared.md` is the source for the Copilot and
   VS Code mirrors.
6. Discovered the change had to be made in six places, not one.

Step 4 is the only thing standing between step 2 and a shipped defect. It was
not a designed check.

## Root cause

Five whys:

1. Why would the rule not reach Copilot? Because it was written to a
   hand-maintained copy, not the generator source.
2. Why was it written there? Because `.claude/agents/orchestrator.md` is the
   file that turns up first when searching for the agent.
3. Why did that seem sufficient? Because prior edits in this repository to
   files under `.claude/` were canonical, so the pattern generalized.
4. Why did the pattern generalize incorrectly? Because agent files are the
   exception: `.claude/agents/`, `.github/agents/`, and `src/claude/` are all
   hand-maintained copies of one generated template (ADR-002).
5. Why was the exception not consulted? `GENERATOR-FILES.md` documents it, and
   nothing prompts a read before an agent-file edit.

Root cause: the repository has a documented generator topology and no
edit-time signal that points a writer at it.

## Evidence

- Divergence origin: commit `dffa7f493a` in PR #1715 (2026-04-21) added the
  `Orchestration Budget` section to `.claude/agents/orchestrator.md` only.
  `git log -S 'Orchestration Budget' -- templates/agents/orchestrator.shared.md`
  returns empty, confirming the section never entered the template.
- Measured divergence on clean `origin/main`:

  | Surface | Lines | H2 count | `Orchestration Budget` | `Output Bounds` |
  |---|---|---|---|---|
  | `.claude/agents/orchestrator.md` | 345 | 20 | yes | no |
  | `src/claude/orchestrator.md` | 345 | 20 | yes | no |
  | `templates/agents/orchestrator.shared.md` | 328 | 19 | no | yes |
  | `src/copilot-cli/agents/orchestrator.agent.md` | 330 | 19 | no | yes |
  | `.github/agents/orchestrator.agent.md` | 335 | 19 | no | yes |

  `.claude` and `.github` copies differ by 104 lines of `diff` output.
- Generator topology: `.agents/governance/GENERATOR-FILES.md:15` (flow),
  lines 31 to 33 (hand-maintained copies).
- `Output Bounds` caps output verbosity per phase. It is not a delegation
  budget, so it is not an equivalent of the missing section.

## Impact

| Area | Severity | Detail |
|---|---|---|
| Copilot orchestrator behavior | High | No delegation budget of any kind since 2026-04-21. Wide waves and deep chains are unbounded. |
| Cross-harness consistency | Medium | Two harnesses running materially different orchestrator contracts under one agent name. |
| This change | High, averted | The wave rule would have shipped to one harness only, widening the gap. |
| Detection | Medium | No gate flagged the divergence. `detect_agent_drift.py` reports the pair as 100.0% similar. |

## What worked

- Running the generator after an edit, even without cause to suspect a problem.
  The `Written: 2` line with no changed mirror was the entire signal.
- Refusing to report `validate_install_parity.py` as defective when its
  `--base` mode reported no drift. The mode diffs `base..HEAD`, and the work was
  uncommitted, so `HEAD` equalled `origin/main`. Re-running in `--files` mode
  produced the correct violation and exit 1. The tool was right.

## What did not work

- Reaching for the first file that matched the agent name.
- Treating `.claude/` as canonical by default. For agents it is not.

## Remediation

1. Done in this change: the wave discipline was added to
   `templates/agents/orchestrator.shared.md`, which required creating the
   `Orchestration Budget` section there. That is a prerequisite for any
   delegation budget reaching Copilot at all. The two generated mirrors were
   regenerated and the three hand-maintained copies were updated to match.
2. Open: the remaining divergence is not closed by this change.
   `Context Maintenance` is still Claude-only and `Output Bounds` is still
   absent from the Claude copies. Needs a dedicated harmonization change so the
   two concerns are not entangled with a behavior change.
3. Open: `detect_agent_drift.py` reports `100.0% similar` for the
   `.claude/agents` versus `.github/agents` orchestrator pair while the files
   differ by 104 lines of `diff` output and one whole section. Determine whether
   the pair is baselined or the similarity metric is blind to section-level
   absence. Do not file a defect until that is established.
4. Proposed: an edit-time signal for agent files. The cheapest form is a note in
   the hand-maintained copies naming the template as the source, so a writer who
   opens the file sees the topology without needing to recall
   `GENERATOR-FILES.md`.

## Learning

When a repository generates some trees and hand-maintains others, "which file
is canonical" is a per-artifact-class fact, not a per-directory fact. In this
repository `.claude/rules/` is canonical and `.claude/agents/` is not. A habit
formed on the first does not transfer to the second.

The generic form: before editing any file that has sibling copies, read the
generator manifest. Running the generator afterward catches the error only when
the writer happens to notice a quiet line in its output.
