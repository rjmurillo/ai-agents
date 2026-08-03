# Decision: agent files under `.claude/agents/` are not canonical

## Question

An agent's behavior needs to change. Which file do you edit so the change
reaches every harness?

## Conventional answer

Edit `.claude/agents/<name>.md`. It is the file that turns up first when
searching for an agent by name, and for most other artifact classes in this
repository the copy under `.claude/` is canonical. `.claude/rules/*.md` is
canonical and generates the two instruction mirrors, so the habit generalizes.

## First-principles position

Agents are the exception. `.claude/agents/`, `.github/agents/`, and
`src/claude/` are all **hand-maintained self-host copies**. The generator source
is `templates/agents/<name>.shared.md`, which produces
`src/copilot-cli/agents/` and `src/vs-code-agents/` per ADR-002.

An edit confined to `.claude/agents/` reaches Claude Code and no Copilot user.
It also passes quietly: the generator runs without error because its own inputs
did not change.

Six surfaces exist per agent:

| Surface | How it is maintained |
|---|---|
| `templates/agents/<name>.shared.md` | source of truth for the generated pair |
| `src/copilot-cli/agents/<name>.agent.md` | generated, do not hand-edit |
| `src/vs-code-agents/<name>.agent.md` | generated, do not hand-edit |
| `.claude/agents/<name>.md` | hand-maintained copy |
| `src/claude/<name>.md` | hand-maintained copy |
| `.github/agents/<name>.agent.md` | hand-maintained copy |

Correct order: edit the template, run `build/scripts/build_all.py`, then update
the three hand-maintained copies to match.

## Evidence

`.agents/governance/GENERATOR-FILES.md` line 15 records the generator flow and
lines 31 to 33 list the three hand-maintained copies. It is the authority.

The cost of not reading it is measurable. PR #1715 (commit `dffa7f493a`,
2026-04-21) added an `Orchestration Budget` section to the orchestrator. It
landed in the Claude copies only.
`git log -S 'Orchestration Budget' -- templates/agents/orchestrator.shared.md`
returns empty, so the section never entered the template and therefore never
reached Copilot. Measured on clean `origin/main` three months later:

| Surface | Lines | H2 | `Orchestration Budget` |
|---|---|---|---|
| `.claude/agents/orchestrator.md` | 345 | 20 | yes |
| `src/claude/orchestrator.md` | 345 | 20 | yes |
| `templates/agents/orchestrator.shared.md` | 328 | 19 | no |
| `src/copilot-cli/agents/orchestrator.agent.md` | 330 | 19 | no |
| `.github/agents/orchestrator.agent.md` | 335 | 19 | no |

The Claude and Copilot copies differ by 104 lines of `diff` output.

## What does not catch this

- Running the generator. It exits 0 and reports writes for unrelated targets.
  The only signal is that no mirror file changed, which is easy to miss.
- `build/scripts/detect_agent_drift.py`. It reports
  `orchestrator [.claude/agents vs .github/agents]: OK (100.0% similar)` for
  this pair, exit 0. Whether that is a baseline exemption or a blind metric is
  unresolved; do not treat its silence as evidence of parity.
- `build/scripts/validate_install_parity.py` **does** catch it, but only in
  `--files` mode. Its `--base` mode diffs `base..HEAD`, so with uncommitted work
  `HEAD` equals the base and it reports no drift. That is correct behavior, not
  a defect. Test it with
  `validate_install_parity.py --files <all six paths>`.

## Decision

Before editing any agent file, read `.agents/governance/GENERATOR-FILES.md`.
Edit `templates/agents/<name>.shared.md` first, regenerate, then hand-update
`.claude/agents/`, `src/claude/`, and `.github/agents/`. Verify with
`validate_install_parity.py --files` naming all six paths, not `--base`.

The generalization: in this repository "which file is canonical" is a
per-artifact-class fact, not a per-directory fact. A habit formed on
`.claude/rules/` does not transfer to `.claude/agents/`.

## References

- `.agents/governance/GENERATOR-FILES.md`
- ADR-002 (agent generation from shared templates)
- `.agents/retrospective/2026-07-31-editing-the-wrong-tree.md`
