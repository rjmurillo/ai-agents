# ADR-120 Claims Ledger: Amendment 2026-11-27

Scope: the amendment section and the edited Negative bullet. Read from the working
tree of branch `fix/github-not-found-exit-codes` on 2026-11-27.

| # | Claim | Kind | Command | Result |
|---|---|---|---|---|
| 1 | ADR-035 maps a missing remote object to exit 3 | quote | `grep -n "not found" .project-toolkit/architecture/ADR-035*.md` | VERIFIED. Line 217: `\| 4 (not found) \| 3 (external error) \| Consolidate into external service category \|` |
| 2 | Some github skill scripts, such as `get_pr_context.py`, used 2 for a missing PR | path | `git show origin/main:src/claude/skills/github/scripts/pr/get_pr_context.py \| grep -n "not found in"` | VERIFIED. Lines 122 and 169 call `error_and_exit(f"PR #{pr} not found in ...", 2)` |
| 3 | They now exit 3 with `Error.Type` `NotFound` in a JSON envelope | path | `grep -n 'not found in\|error_type="NotFound"' src/claude/skills/github/scripts/pr/get_pr_context.py` | VERIFIED. Lines 130 and 177 raise `_PrNotFoundError`; line 63 writes `write_skill_error(message, 3, error_type="NotFound", ...)` |
| 4 | Exit 2 keeps a missing lib | path | `sed -n 60,63p src/claude/skills/github/scripts/skill_bootstrap.py` | VERIFIED. Line 62 prints `Plugin lib directory not found`, line 63 `sys.exit(2)` |
| 5 | The gate code does not change | behavior | `git diff origin/main...HEAD --stat -- src/claude/skills/github/scripts/pr/run_completion_gate.py` plus working tree diff | VERIFIED. No change to that file on the branch |
| 6 | `_unanswered_exit` treats any exit above 1 as no answer | path | `sed -n 3901,3909p src/claude/skills/github/scripts/pr/run_completion_gate.py` | VERIFIED. `if exit_code > 1: return exit_code` |
| 7 | REST refusal probe explains exits 2, 3, and 4 | path | `sed -n 3848,3859p src/claude/skills/github/scripts/pr/run_completion_gate.py` | VERIFIED. First `_SessionProbe` carries `frozenset({2, 3, 4})` |
| 8 | GraphQL refusal probe explains only exit 2 | path | same range | VERIFIED. Second `_SessionProbe` carries `frozenset({2})` |
| 9 | An unknown or failed row never passes | behavior | `sed -n 3912,3933p src/claude/skills/github/scripts/pr/run_completion_gate.py` | VERIFIED. Docstring at line 3919: "An unknown row keeps ``passed`` false"; `failed` outranks `unknown` |
| 10 | A refused session should not reach the not-found branch, because the classifier matches neither refusal body | behavior | `PYTHONPATH=scripts python3 -c` calling `github_core.not_found.is_pr_not_found` on both refusal bodies from lines 3851 and 3856 | VERIFIED for the classifier: both return `False`. INFERRED for live behavior: not run in a real refused session |

## Refuting seat, round 1 (haiku analyst, 53 s)

The seat had read-only tools, so it marked rows 2 and 5 NOT RUN. The writer ran both
commands: row 2 output shows `, 2)` at lines 122 and 169 on `origin/main`; row 5
`git diff origin/main --stat` on `run_completion_gate.py` prints nothing.

Findings and fixes:

- Row 9 quoted single backticks; the source uses double. Fixed.
- The amendment stated the refused-session claim as fact while row 10 is INFERRED.
  The amendment now says it is inferred.
- The amendment said "the github skill scripts" while the ledger checks one script.
  The amendment now says "some github skill scripts, such as `get_pr_context.py`".

Result after fixes: VERIFIED, no open factual finding.
