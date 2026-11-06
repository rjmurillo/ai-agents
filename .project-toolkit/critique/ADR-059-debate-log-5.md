# ADR Debate Log: ADR-059 /pr-review Completion Gate Dispatcher and pass_when DSL (fifth debate)

## Summary

- **Rounds**: 1 of 10. Round 1 reached consensus.
- **Prior debate log**: `.project-toolkit/critique/ADR-059-debate-log-4.md`
- **Outcome**: Consensus. Round 1: two Accept.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-059-pr-review-completion-gate-dispatcher.md`
- **Edit**: one cite path in the R1 no-harness bullet (ADR line 156).
  `src/codex/.../pr-review-config.yaml:30` is now
  `src/codex/skills/pr-review/pr-review-config.yaml:30`. Frontmatter,
  decision items, and rules are unchanged. The ADR stays at 500 lines.
- **PR**: #7014, branch `fix/6506-batch7-merge-pr-automation-2`.
- **Trigger**: the pre-push `Citation Freshness (added lines)` gate failed
  on ADR line 156 with "cited file not tracked at HEAD". The elided path
  named no file. Log 4 had closed, so this edit opens a new debate
  (`debate-protocol.md#round-cap`).
- **Same commit, outside the ADR**: `templates/skills/pr-review.SKILL.md.tmpl`
  line 46 drops "(#5112)", with its rendered mirrors. The pre-push
  `Template Repo References` gate refuses issue numbers in shipped
  templates. The edit keeps every line in place, so the ADR's template
  cite (lines 152-154) does not move.

Panel: reduced panel (architect, critic). The edit fixes a cite path and
changes no rule, so the AGENTS.md ADR review rule routes it to the reduced
panel.

Method: each seat ran as its own `claude -p` process, with its Phase 1
prompt from `references/agent-prompts.md`, the Factual Claim Verification
Block, and the convergence instructions. Seats had read-only tools.

## Round 1 (2026-11-02)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | The fixed path exists, and its line 30 backs the sentence. The template edit moves no cited line. |
| critic | Accept | The path is tracked; line 30 is `copilot:` in the Codex, Cursor, and Hermes copies. |

### Issues Raised

None at P0, P1, or P2.

### Claims Checked

| Claim | Agent | Result |
|-------|-------|--------|
| `src/codex/skills/pr-review/pr-review-config.yaml:30` is a Copilot map | architect, critic | VERIFIED |
| Cursor and Hermes copies carry a Copilot map at line 30 | critic | VERIFIED. The Hermes copy is under `src/hermes/project-toolkit-delivery/`. |
| The template edit moves no ADR-cited line | architect, critic | VERIFIED |
| The freshness gate passes on the new cite | critic | UNVERIFIED in the round: the checker reads HEAD, and the fix was not yet committed. The commit that lands this log runs the gate. |

### Carried Forward

Every open item from log 4 is unchanged, including D4-SEGMENT and the
R3-ORDER residual. This edit changes no `gate.py` file and no cited line.

## Closing Summary

Consensus in round 1 with two Accept. The decision is unchanged.
