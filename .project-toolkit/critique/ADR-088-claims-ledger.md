# ADR-088 claims ledger, 2026-11-25

Claims in the 2026-11-25 amendment of ADR-088, "the weekly activation workflow is deleted".

Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| software-engineering-library-activation.yml no longer exists | absence | `test ! -e .github/workflows/software-engineering-library-activation.yml && echo absent` | VERIFIED: absent |
| Commit 3f145f26fd (2026-11-25) deleted it | behavior | `git show --format=%cs --name-status 3f145f26fd -- .github/workflows/software-engineering-library-activation.yml \| tr '\n' ' '` | VERIFIED: 2026-11-25 D .github/workflows/software-engineering-library-activation.yml |
| The workflow ran on a weekly schedule | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -n 'cron'` | VERIFIED: 5: - cron: "30 6 * * 1" |
| The workflow ran the live activation eval | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -c 'software_engineering_library_activation_ci.py live-eval'` | VERIFIED: 1 |
| The workflow kept the rollback streak in the Actions cache | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -c 'actions/cache/'` | VERIFIED: 2 |
| The workflow opened or updated the rollback alert issue | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -n 'rollback alert issue\\|alert-issue' \| tr '\n' ' '` | VERIFIED: 98: - name: Create or update rollback alert issue 102: run: uv run python scripts/eval/software_engineering_library_activation_ci.py alert-issue |
| Issue #5951 amendment text: raises the existing rollback alert | quote | `grep -n 'raises the existing rollback alert' .project-toolkit/architecture/ADR-088-progressive-disclosure-book-rules.md \| head -n 1` | VERIFIED: 220:reference that stops activating raises the existing rollback alert. |
| No file under .github runs the activation eval scripts | absence | `git grep -l 'software_engineering_library_activation' -- .github \| wc -l` | VERIFIED: 0 |
| scripts/eval/README.md states Cadence: manual | quote | `grep -n '^Cadence: manual' scripts/eval/README.md` | VERIFIED: 1048:Cadence: manual. The CI workflow that ran this weekly was removed on 2026-11-25 |
| Both scripts named for the manual run exist | path | `ls scripts/eval/software_engineering_library_activation_ci.py scripts/eval/software_engineering_library_activation_gate.py \| tr '\n' ' '` | VERIFIED: scripts/eval/software_engineering_library_activation_ci.py scripts/eval/software_engineering_library_activation_gate.py |
| The rollback streak lives in a local state file and checkouts do not share it | quote | `sed -n '1052,1055p' scripts/eval/README.md \| tr '\n' ' '` | VERIFIED: Persistent state lives in a local file at `.eval-state/software-engineering-library-activation-state.json`, relative to the directory you run from. The Actions cache that carried it between weekly runs went away with the workflow, so separate checkouts do not share a rollback streak. Run |
| 2026-11-24 amendment text: a scheduled activation monitor | quote | `tr '\n' ' ' < .project-toolkit/architecture/ADR-088-progressive-disclosure-book-rules.md \| grep -o 'into a scheduled activation monitor' \| head -n 1` | VERIFIED: into a scheduled activation monitor |
| No workflow with a schedule trigger mentions activation | absence | `for f in $(git grep -l -i 'activation' -- .github/workflows); do grep -l '^  schedule:' "$f"; done \| wc -l` | VERIFIED: 0 |
| Workflows that mention activation at all (context for the row above) | behavior | `git grep -l -i 'activation' -- .github/workflows \| tr '\n' ' '` | VERIFIED: .github/workflows/validate-rule-activation-coverage.yml |
| No job under .github declares an agent-* environment now (the "every other job" clause) | absence | `git grep -n -E '^\s*environment:\s*agent-' -- .github \| wc -l` | VERIFIED: 0 |

## Third pass, 2026-11-26

Rows for the text the reduced panel added on 2026-11-26: the manual-cadence detail and the paragraph that ties the loss to the Negative consequence. Commands ran on 2026-11-26 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| `scripts/eval/README.md` says cadence is manual and names the three change triggers | quote | `sed -n '1046,1055p' scripts/eval/README.md \| grep -o -E 'Cadence: manual\|by hand when the skill, fixtures, or eval script change' \| tr '\n' ';'` | VERIFIED: Cadence: manual;by hand when the skill, fixtures, or eval script change; |
| The Negative consequence carries the quoted phrase (line-wrapped at 148 to 150) | quote | `sed -n '148,150p' .project-toolkit/architecture/ADR-088-progressive-disclosure-book-rules.md \| tr -s ' \n' ' ' \| grep -c -F 'an owner, cadence, persisted consecutive-run state, and CI or scheduled invocation'` | VERIFIED: 1 |
| The deleted workflow had a schedule trigger | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -n -E '^  schedule:\|cron:' \| tr '\n' ' '` | VERIFIED: 4:  schedule: 5:    - cron: "30 6 * * 1" |
| The deleted workflow kept state in the Actions cache | behavior | `git show 3f145f26fd^:.github/workflows/software-engineering-library-activation.yml \| grep -c -E 'actions/cache'` | VERIFIED: 2 |
| No file under .github names the activation eval now | absence | `git grep -l 'software_engineering_library_activation' -- .github \| wc -l` | VERIFIED: 0 |
| No tracked file outside scripts/eval, tests and .project-toolkit names the eval scripts (so no other scheduler calls them) | absence | `git grep -l 'software_engineering_library_activation' -- . ':!tests' ':!scripts/eval' ':!.project-toolkit' \| wc -l` | VERIFIED: 0 |
| The state file is local and not shared between checkouts | quote | `sed -n '1046,1058p' scripts/eval/README.md \| grep -c -F 'separate checkouts do not share a rollback streak'` | VERIFIED: 1 |
| The README cadence paragraph (lines 1048 to 1050) names no model, CLI, or harness trigger | absence | `sed -n '1048,1050p' scripts/eval/README.md \| grep -c -i -E 'model\|\bcli\b\|harness'` | VERIFIED: 0 |
