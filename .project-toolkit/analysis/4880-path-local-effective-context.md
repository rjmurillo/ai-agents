# Path-Local Effective Context: Before and After (#4880)

**Spec**: `.project-toolkit/specs/SPEC-4880-path-local-effective-context.md`
**Baseline**: `2628d8c1282277ad39bc605eb6a31131eff2d77e` (the issue's own measurement)
**After**: `643e9b4ab` (main when this work started; path-local files are unchanged on this branch)
**Command**: `uv run python -m scripts.validation.effective_context --target <path> --harness both [--rev <sha>] [--json]`

## What the command measures

The command lists each instruction file a harness loads for one target path.
It reports the layer, the bytes, and the reason the file loaded.
It never sums the repository.
The user layer (`~/.claude/CLAUDE.md`, `~/.copilot/copilot-instructions.md`) prints only with `--include-user`.
No ratchet counts it, because CI cannot see it.

The loading rules come from observation, not from file names:

- Copilot CLI 1.0.89: `copilot instruction list --json` from each target directory.
  `--observe` compares that listing with the static set.
  All five frozen targets matched on 2026-09-27.
- Claude Code 2.1.283: root `CLAUDE.md` and its `@` imports, `.claude/CLAUDE.md`, nested `CLAUDE.md` files on the path with their imports, and rules whose `paths:` match.
  Claude has no model-free listing command, so the static model has no live membership check.

## Inventories

Bytes per layer. "Path-local" is the nested layer below the repository root.

| Target | Harness | Before total | Before path-local | After total | After path-local |
|---|---|---:|---:|---:|---:|
| `.github/workflows/pr-validation.yml` | Claude | 113,143 | 170 | 80,768 | 5,190 |
| `.github/workflows/pr-validation.yml` | Copilot | 130,692 | 25,102 | 84,394 | 5,190 |
| `scripts/validation/pre_pr.py` | Claude | 145,497 | 170 | 122,938 | 4,141 |
| `scripts/validation/pre_pr.py` | Copilot | 157,436 | 8,161 | 126,578 | 4,141 |
| `build/scripts/build_all.py` | Claude | 157,767 | 0 | 138,850 | 5,807 |
| `build/scripts/build_all.py` | Copilot | 174,748 | 13,130 | 142,399 | 5,807 |
| `templates/agents/analyst.shared.md` | Claude | 119,398 | 0 | 85,056 | 5,923 |
| `templates/agents/analyst.shared.md` | Copilot | 124,008 | 11,846 | 89,009 | 5,923 |
| `src/claude/agents/analyst.md` | Claude | 121,138 | 0 | 78,760 | 3,183 |
| `src/claude/agents/analyst.md` | Copilot | 126,140 | 12,196 | 85,948 | 6,376 |

`src/claude/agents/analyst.md` did not exist at the baseline.
The resolver walks the directory chain, so the missing file does not matter.

## Findings

1. **Every effective total dropped in both harnesses.** The drop ranges from 12% (`build/`, Claude) to 35% (`.github/`, Copilot).
   Most of it comes from scoped rules that PR #5496 and later work scoped with `paths:`.
2. **Copilot path-local bytes fell by half or more.** `.github/AGENTS.md` fell from 24,932 to 5,008 bytes (PR #5792).
3. **Claude path-local bytes grew, and that is the fix, not a regression.**
   At the baseline, no nested `CLAUDE.md` imported its sibling `AGENTS.md`.
   Claude never loaded `.github/AGENTS.md`, `build/AGENTS.md`, or `templates/AGENTS.md`.
   PR #5713 added those imports, so the `.github/` safeguards now reach Claude too.
4. **`src/claude/AGENTS.md` still reaches Copilot only.** `src/claude/` has no `CLAUDE.md`.
   Claude reads `src/AGENTS.md` through `src/CLAUDE.md` and stops there.
   This work does not change that. It is recorded for the next owner of `src/claude/AGENTS.md`.

## Classification of `.github/AGENTS.md` (after)

| Section | Class | Why it stays |
|---|---|---|
| Matters | Non-inferable local gotcha | Names generated directories and the one hand-authored exception |
| Entry points | Arbitration | Says where job logic lives and that `.github/scripts/ci/` does not exist |
| Where to look | Reference, short | Per-directory owner and edit rule; no per-workflow catalog |
| Skip | Arbitration | Tells a reader what not to open |
| Constraints | Costly-failure safeguard | SHA pins, concurrency registration, `gh` path shape |
| Dangerous assumptions | Non-inferable local gotcha | Four wrong beliefs, each with the correct source |
| Dependencies | Arbitration | Points to the owning guide instead of repeating it |
| Architecture | Local gotcha | Mirror counts differ on purpose |
| Commands | Task procedure, short | Nine commands; each is the gate a section names |

The file no longer carries workflow catalogs, process walkthroughs, or latency estimates.
Seven other guides use the same nine sections since PR #5792: `templates/`, `build/`, `scripts/`, `src/`, `src/claude/`, `.agents/`, and `.claude/`.
The section classes above apply to each of them.
PR #5792 re-verified each line against the tree, so this work adds no content edit.

## Ratchet

`scripts/validation/effective_context.py --ci` runs in the pre-PR sequence, and `tests/validation/test_effective_context_ratchet.py` runs it in the required Python test job.
It checks two things:

- Ten ceilings: the five frozen targets in both harnesses, each equal to its measured path-local bytes.
- One ceiling per directory and harness for every git-tracked directory that holds a nested `CLAUDE.md` or `AGENTS.md` (62 directories, 124 entries today), each equal to that directory's own measured path-local bytes. A single shared ceiling (the original design) let any directory regrow up to the highest-measured one (`.claude/hooks/PreCompact`, Copilot, 11,369 bytes) without tripping; a directory with no entry in the map fails closed instead of passing silently.

Every ceiling is local and measured at the accepted state.
Anthropic publishes no 25 KB, 200-line, or 50-line hard limit for these files, and no ceiling here claims one.

## Behavior (real-harness fixtures)

`scripts/eval/examples/path-local-parity-fixtures.json` holds three frozen tasks, all run from `.github/workflows` with the root and `.github/` instruction files installed:

| Fixture | Safeguard under test | Dry-run controls |
|---|---|---|
| `sha-pin-action` | A new `actions/checkout` step uses a 40-hex SHA | Positive passes, negative fails |
| `untrusted-input-run` | The pull request title reaches `run:` only through `env:` | Positive passes, negative fails |
| `generated-instructions-edit` | A rule edit lands in `templates/rules/`, not the generated mirror | Positive passes, negative fails |

### Claude Code results

Claude Code 2.1.283, `claude-sonnet-5`, three trials per arm, run on 2026-09-27 at commit `a2f1b1c39`.
The before arm reads every installed instruction file from `2628d8c1` with `--instructions-ref`.
The after arm reads them from the working tree.
The CLI used its existing login through `CLAUDE_CODE_OAUTH_TOKEN`, so the isolated profile stayed isolated.

| Fixture | Before | After |
|---|---:|---:|
| `sha-pin-action` | 3/3 | 3/3 |
| `untrusted-input-run` | 3/3 | 3/3 |
| `generated-instructions-edit` | 0/3 | 1/3 |

No fixture regressed.
In the before arm, all three runs edited only the generated mirror.
In the after arm, one run edited only the canonical `templates/rules/testing.md`.
One run edited both files, and one edited only the mirror.
A later, stricter `workflow_untrusted_input` check also rejects `${{ env.NAME }}` in `run:` for a name that reads the title. All six saved `greet.yml` outputs still pass it.
Three trials per arm is a small sample, so read the last row as "no regression", not as a measured gain.

Two harness defects surfaced on the way and are fixed in this branch:

- A nested `cwd` limited Claude's file access to that directory, so the first live run failed on permissions in both arms. The evaluator now adds `--add-dir` with the workspace root.
- Copilot received `--no-custom-instructions` for a fixture with only `path_local` files, which would have disabled the files under test.

### Copilot CLI results

NOT RUN. The isolated Copilot profile (CLI 1.0.88) returned `session.error` with status 402, `quota_exceeded`, before any model turn.
This 1.0.88 differs from the 1.0.89 that the `--observe` listing probes used, because the eval harness resolves the binary through its own isolated profile.
To run the Copilot arm once quota returns:

```bash
uv run python scripts/eval/eval_runtime_parity.py \
  --fixtures scripts/eval/examples/path-local-parity-fixtures.json \
  --instructions-ref 2628d8c1282277ad39bc605eb6a31131eff2d77e \
  --model claude-sonnet-5 --harnesses copilot \
  --output artifacts/runtime-parity/path-local/before.json \
  --workspace-root "$(mktemp -d)"
```

Run it again without `--instructions-ref` for the after arm.
