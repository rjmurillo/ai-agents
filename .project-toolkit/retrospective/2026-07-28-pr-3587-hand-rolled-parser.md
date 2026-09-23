# Retrospective: PR #3587, a hand-rolled parser for a library the project already ships

**Branch**: `fix/orchestrator-phantom-agent`
**PR**: [#3587](https://github.com/rjmurillo/ai-agents/pull/3587)
**Status**: Open, 13 commits, 23 files
**Outcome**: PARTIAL. The defect is fixed and gated. Reaching a correct gate took four adversarial rounds and one full rewrite of the parsing layer.

---

## Failure Mode Classification

**Primary**: FM-9, Confident-Incorrectness Recurrence.

The validator had to decide which markdown tables GitHub renders as tables. That contract is written down: the GitHub Flavored Markdown specification. Instead of reading it, or using the parser this project already declares as a dependency, the first implementation modeled the contract from memory as five regular expressions. Every round of review found another place where the model and the contract disagreed. Three commits attacked the same conceptual mistake before the fourth removed it.

This matches the FM-9 trigger exactly: "A change asserts that it matches, mirrors, or aligns with an existing source (a regex, schema, exit-code table, or wire contract) without quoting that source verbatim. The author models the contract from memory instead of reading it."

It also matches the FM-9 detection signal "A PR corrects the same conceptual mistake across three or more commits." The relevant three are `2e3f5cbdd4`, `cbc6ea0d95`, and `69a11c6e76`.

**Secondary**: FM-1, Context Reading Failure. `pyproject.toml` lines 12 to 14 declare `markdown-it-py`, `python-frontmatter`, and `PyYAML` as core dependencies. That file was never opened before writing the parser. The context was present, discoverable, and one read away.

**Reference**: [`.agents/governance/FAILURE-MODES.md`](https://github.com/rjmurillo/ai-agents/blob/main/.agents/governance/FAILURE-MODES.md)

---

## What the PR fixes

The orchestrator capability matrix advertised agents that do not ship. A model reading that table routes to the name it finds, delegation resolves to nothing, no error surfaces, and the work is dropped in silence.

Two phantoms shipped:

- `memory`. The agent was retired on 2026-06-02 in [`ce4ebabb`](https://github.com/rjmurillo/ai-agents/commit/ce4ebabb) when cross-session memory became a skill. The matrix row stayed. Measured survival: 8 weeks, across every install.
- `quality-auditor`. Present in one tree, advertised by all six.

---

## Timeline

| Commit | What it did | Round |
|---|---|---|
| [`696c5ea5`](https://github.com/rjmurillo/ai-agents/commit/696c5ea5) | Removed the `memory` row | Initial |
| [`26aa3e9a`](https://github.com/rjmurillo/ai-agents/commit/26aa3e9a) | Removed it from the index tables | Initial |
| [`2e3f5cbd`](https://github.com/rjmurillo/ai-agents/commit/2e3f5cbd) | Added the validator, regex parsing | Initial |
| [`229ac61b`](https://github.com/rjmurillo/ai-agents/commit/229ac61b) | Corrected `src/claude` classification | Initial |
| [`aac0eefc`](https://github.com/rjmurillo/ai-agents/commit/aac0eefc) | Bumped plugin manifests | Initial |
| [`4d066610`](https://github.com/rjmurillo/ai-agents/commit/4d066610) | Removed `quality-auditor` | Round 1 |
| [`3dc13d89`](https://github.com/rjmurillo/ai-agents/commit/3dc13d89) | Resolved citations per tree, not repo-wide | Round 2 |
| [`23cef27f`](https://github.com/rjmurillo/ai-agents/commit/23cef27f) | Decided agent membership by content, not filename | Round 3 |
| [`cbc6ea0d`](https://github.com/rjmurillo/ai-agents/commit/cbc6ea0d) | Tried to match rendered GFM with better regexes | Round 3 |
| [`51ebab13`](https://github.com/rjmurillo/ai-agents/commit/51ebab13) | Refused to run when a configured tree is absent | Round 4 |
| [`69a11c6e`](https://github.com/rjmurillo/ai-agents/commit/69a11c6e) | Deleted the regexes, used `markdown-it-py` and PyYAML | Round 4 |
| [`d49f6fa9`](https://github.com/rjmurillo/ai-agents/commit/d49f6fa9) | Split the table walk to hold complexity under the cap | Round 4 |

Four adversarial rounds, each on a different model family than the author.

---

## Impact

| Area | Severity | Detail |
|---|---|---|
| Routing correctness | High | Two phantom names advertised across six installs. Delegation to either dropped the work with no error. |
| Review cost | Medium | Four rounds. Rounds 2, 3, and 4 all found parsing defects that a library would never have had. |
| Gate correctness | High | The regex parser had two blind spots that let a phantom through and three false positives that would have failed a legitimate document. |
| Commit budget | Low | 13 commits against a warn threshold of 15 and a hard limit of 20 (ADR-008). |

---

## Root Cause

Five whys.

1. Why did the validator need four rounds? Each round found a new disagreement between the parser and how GitHub renders markdown.
2. Why did the parser disagree with GitHub? It was five regular expressions approximating a block grammar.
3. Why regular expressions? Writing them was the first idea, and it appeared to work against the documents that exist today.
4. Why was no library considered? The project's dependency list was never read.
5. Why was it never read? No step in the working method required checking what is already available before building. The rule exists in `.claude/rules/builder-ethos.md` as "Search Before Building, Layer 1". It was not run.

**Root cause**: the Layer 1 search was skipped. The parser was built from memory of a contract instead of from the contract, and the tool that already encodes the contract was sitting in `pyproject.toml`.

---

## What the rewrite bought

Replacing the regexes was not only a cleanup. Diffing the old module against the new one across twelve constructed documents found five behavioral differences. Two were defects that let a phantom through.

| Document shape | Regex parser | Library parser | Class |
|---|---|---|---|
| Matrix inside a blockquote | invisible | parsed | **missed phantom** |
| Prose line directly after a table body | ended the table, hiding later rows | continues the table, per GFM example 206 | **missed phantom** |
| `Agent \| Role` over a bare `---` | read as a table | correctly a setext heading | false positive |
| Heading with a pipe after a table | reported a broken row | ignored | false positive |
| HTML comment after a table | reported a broken row | ignored | false positive |

The two rows marked "missed phantom" are the point. A hand-written parser did not merely risk being wrong in theory. It was already wrong in two ways that defeated the validator's only job.

---

## A second defect, found by the security review

The rewrite introduced `yaml.safe_load` on frontmatter. The old code never parsed YAML at all, so this was new attack surface created by the fix.

`safe_load` blocks arbitrary object construction. It does not block resource exhaustion. `SafeConstructor.flatten_mapping` expands a YAML merge key by copying every entry of the mapping the alias names, so a chain where each level references the level below it nine times multiplies the entry count by nine per level.

Measured at depth eight, each level referencing the level below it nine times: a frontmatter block **under 500 bytes** held the scan for **21.5 seconds**. Depth seven takes 2.5 seconds and depth six 0.3, so each level costs roughly nine times the last and two more levels reach roughly half an hour. The exact byte count moves with how the block is spelled, between 422 and 446 across three independent measurements, so it is the shape that matters and not the number: a chain of merge keys short enough to hide in a diff. The validator runs on `pull_request`, so a fork supplies the file.

Fixed by refusing alias references outright. Zero of 176 shipped frontmatter blocks use an anchor, alias, or merge key, so the guard excludes nothing real, and a test pins that fact so the tradeoff surfaces if it ever changes.

---

## A third defect, in the instrument rather than the code

The tests were checked with mutation testing: 49 deliberate defects planted in the validator one at a time, each expected to make some test fail. The first run reported 48 killed, 0 survived. Read plainly, that says the suite catches every defect anyone thought to plant.

It was false. All 48.

The harness copied the worktree with `.git` stripped, on the reasoning that history is not needed to run tests. A teardown fixture reads the repository HEAD, so in the copy the suite died on its first test with `could not read repository HEAD` and exited 1. The harness reads any nonzero exit as "the mutant was caught." Every mutant died before its mutation could matter.

The `.git` strip is the trigger, not the cause. The cause is that the harness had no control. It never ran the unmutated code, so it could not tell a mutant being caught from nothing running at all. An instrument with no control reports success by construction. That is the same shape as the defect this retrospective is about: a check that cannot fail, believed because it was green.

It was caught by an adversarial round, on a different model family, that read the harness rather than the validator.

Fixed by running the unmutated suite first and refusing to report anything if it is not green. Corrected numbers, with the gate in place:

| Run | Killed | Survived | Trustworthy |
|---|---|---|---|
| Before the gate | 48/48 | 0 | No, baseline red |
| After the gate | 44/53 | 9 | Yes |
| After closing the gaps | 52/52 | 0 | Yes |

The nine survivors were real. Six were untested behaviour, now tested: alt text spliced into an agent name, a name kept unstripped, uppercase and spaced names accepted. Three were branches for a row holding no cell, which the parser cannot produce. Measured across every tracked markdown file at `02a4be1c30`, 69,785 table rows in 3,912 files, plus rows built to hold nothing, it never happened. Those branches were removed and the invariant stated where it is relied upon.

The false report nearly shipped as evidence. It had been written into a working note as "48/48 killed" and would have gone into the PR body as the argument that the tests were sound.

A sixth round, on a further model family, found the same shape once more in a test written to close one of those gaps. A byte order mark was placed ahead of the frontmatter to prove the matrix read had been fixed. The mark sat ahead of the wrong thing: it breaks whatever it precedes, and the table further down the file is found either way, so the test passed with the fix reverted. A second attempt put the mark ahead of a heading and failed for the same reason. Only a document opening on the table row itself puts the mark where it decides the outcome.

The reviewer also could not reproduce three figures in an earlier draft of this document. It was right. Two came from a working tree scan that included untracked files, and one from a generator whose exact spelling was not recorded. They are restated above against tracked files at a named commit, and the byte figure is given as a range because it is the shape that carries the argument, not the number. A measurement whose method is not stated is not reproducible, and a reviewer who cannot reproduce it is correct to treat it as unverified.


1. **Never hand-write a parser for a documented format.** If a grammar has a specification, something already implements it. Check the dependency list before writing the first pattern. Cost of checking: one file read. Cost of skipping: three rounds and two live defects.
2. **A rewrite that fixes review findings should be diffed against what it replaces, not assumed equivalent.** Running both implementations over constructed inputs turned "this should behave the same" into five measured differences, two of which were defects nobody had found by reading.
3. **New surface introduced by a fix gets reviewed as new surface.** The YAML bomb existed only because this PR started parsing YAML. A review scoped to "did the fix work" would have missed it.
4. **A test that hangs on regression is a bad test.** The first version of the bomb test used a depth that runs for half an hour when the guard is removed. It was capped at a depth that fails in 22 seconds. A regression must fail and say why, not stall the runner.
5. **Verify the exit code you are reading.** A push reported as succeeding had actually been rejected; the `0` came from the last command in a pipe, not from `git push`.
6. **An instrument with no control reports success by construction.** The mutation harness said 48 of 48 defects were caught while catching none, because it never ran the unmutated code and could not tell a kill from a suite that failed to start. Any measurement whose failing case is indistinguishable from its passing case is not a measurement. Establish the negative before believing the positive.
7. **An assertion that cannot fail is a defect, not a passing check.** Three turned up in one session. A pre-flight check walked `ast.Assign` looking for an annotated assignment and reported zero problems while examining zero things. A guard scanned whole file text for a pattern that only means something inside frontmatter. Both were green. Both were empty. A check earns trust by being shown to fail on input that deserves failure. The cheap way to earn it: break the code the test names and watch the test go red. Two of the three survived review by inspection and died in seconds under that.
8. **State the method with the measurement.** Three figures in the first draft of this document could not be reproduced by a reviewer, because the scan behind them was never described. A number without its method is a claim, not evidence, and the reviewer is right to reject it.

---

## Remediation

| Action | Type | Status |
|---|---|---|
| Delete the regex parser, use `markdown-it-py` | Code | Done, [`69a11c6e`](https://github.com/rjmurillo/ai-agents/commit/69a11c6e) |
| Parse frontmatter with YAML rather than pattern matching | Code | Done, [`69a11c6e`](https://github.com/rjmurillo/ai-agents/commit/69a11c6e) |
| Refuse YAML alias references in frontmatter | Code | Done, this PR |
| Add `markdown-it-py` to the bare-pip CI install line | CI | Done, [`69a11c6e`](https://github.com/rjmurillo/ai-agents/commit/69a11c6e) |
| Keep a bare-pip workflow install list in step with `uv.lock` | CI gap | Issue filed, see below |
| Split the validator, now over the 500 line advisory | Code | Issue filed, see below |
| Give the mutation harness a baseline gate | Tooling | Done, harness is out of tree |
| Close the nine gaps the corrected run exposed | Code | Done, this PR |
| Promote `quality-auditor` to a shared template | Content | [#3584](https://github.com/rjmurillo/ai-agents/issues/3584) |
| Decide which unrouted agents earn a matrix row | Content | [#3585](https://github.com/rjmurillo/ai-agents/issues/3585) |

---

## Process Notes

The four adversarial rounds worked. Every round found something real, and the round that produced the rewrite was the one that asked why the code was approximating a parser at all. Running each round on a different model family than the author is what kept the rounds from agreeing with each other.

The gate that produced this document also worked. The push was refused because the session crossed midnight UTC and no retrospective existed for the new day. That refusal is why the five learnings above are written down instead of lost.

No individual is at fault. The working method allowed a parser to be written before the dependency list was read. That is the thing to change.
