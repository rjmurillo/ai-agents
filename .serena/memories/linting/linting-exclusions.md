# Skill-Lint-005: Exclude Generated Directories

**Statement**: Exclude generated artifact directories from linting using `ignores`

**Context**: Managing linting for mixed codebase with generated content

**Atomicity**: 90%

**Impact**: 8/10

## Implementation

In `.markdownlint-cli2.yaml`:

```yaml
ignores:
  - ".agents/**"
  - "**/node_modules/**"
  - "dist/**"
```

Note the leading `**/` on the `node_modules` pattern. `node_modules/**` matches
only a root-level directory; `**/node_modules/**` also catches nested ones such
as `foo/node_modules/a.md`. The live config uses the recursive form.

Do not add a top-level `globs:` key. This config carried one once and it was
removed deliberately, with the reason recorded inline at the removal site:
markdownlint-cli2 ADDS config globs to any files passed on the command line, so
a hook that lints one touched file also walks every `**/*.md` in the repo and
takes minutes per invocation. The current config has exactly two top-level
keys, `config` and `ignores`. That matters beyond the `globs` warning: because
`config` holds no relative paths, no `extends`, and no `customRules`, the file
can be copied to a scratch directory and still behave identically, which is
what the out-of-tree procedure below relies on.

## Why Exclude .agents/

ADRs/plans have different formatting needs:

- Intentional nested code blocks
- Templates with special syntax
- Generated content

## False Positives

Document known false positives in config comments:

```yaml
# Known false positives:
# - retrospective.md: nested templates trigger MD040
# - roadmap.md: nested templates trigger MD040
```

## Verification trap: an excluded path lints green because it never lints

The exclusions make an in-tree run vacuous for the paths they cover. The run
reports success and exits 0 because zero files were selected, not because the
files are clean.

Verified 2026-07-28 on identical bytes (a file with one MD032 violation):

| Run | Output | Exit |
|---|---|---|
| In tree, at `.serena/memories/probe.md` | `Linting: 0 files` / `0 issues in 0 files` | 0 |
| Out of tree, same bytes | `Linting: 1 file` / `1 issue in 1 file`, MD032 reported | 1 |

Read `Linting: N files`, not the summary. `0 issues in 0 files` is a green that
means nothing. The trailing count in the summary is *files with issues*, so
`0 issues in 0 files` and a real clean run are indistinguishable without the
`Linting:` line.

The obvious escape does not work. `--no-globs` does not disable `ignores`. It
only controls whether the config's `globs` key contributes extra input paths,
which is the behaviour described under the out-of-tree procedure below. Measured
2026-08-02 with markdownlint-cli2 v0.23.2:

```bash
markdownlint-cli2 .agents/SESSION-PROTOCOL.md
markdownlint-cli2 --no-globs .agents/SESSION-PROTOCOL.md
```

Both commands print `Linting: 0 files`. Use the out-of-tree procedure instead.

This surface is large. At the time of writing, `ignores` held 44 patterns
covering 89.7% of tracked markdown (3,529 of 3,935 files), including
`.claude/skills/**`, `src/copilot-cli/skills/**`, `.serena/**`, `.agents/**`,
`**/CLAUDE.md`, `.github/agents/**/*.agent.md`, `docs/autonomous-pr-monitor.md`,
and the five lifecycle commands across ten explicit paths (the `.claude/commands/`
files and their `src/copilot-cli/skills/` mirrors).

These figures drift as the config and the tree change. Regenerate them instead
of trusting this text:

```bash
python3 -c "
import subprocess, yaml, pathspec
cfg = yaml.safe_load(open('.markdownlint-cli2.yaml'))
ignores = cfg.get('ignores', [])
files = subprocess.run(['git','ls-files','*.md'], capture_output=True, text=True).stdout.split()
spec = pathspec.PathSpec.from_lines('gitwildmatch', ignores)
hit = sum(1 for f in files if spec.match_file(f))
print('ignore patterns:', len(ignores))
print('disabled rules:', sorted(k for k, v in cfg.get('config', {}).items() if v is False))
print(f'markdown ignored: {hit} of {len(files)} ({100*hit/len(files):.1f}%)')
"
```

Run it under `uv run` if `pathspec` is missing from the ambient interpreter; it
resolves through `uv.lock`. The coverage figure is an estimate: this uses
gitwildmatch semantics while markdownlint-cli2 uses picomatch. The two agree on
the patterns in this config, so treat the percentage as close rather than
exact.

To actually lint an excluded file, copy it to a scratch directory outside the
repo, copy `.markdownlint-cli2.yaml` alongside it, delete the `ignores` and
`globs` keys from that copy, and run the linter there:

```bash
mkdir -p /tmp/mdl && cp path/to/excluded.md /tmp/mdl/
python3 -c "
import yaml
d = yaml.safe_load(open('.markdownlint-cli2.yaml'))
d.pop('ignores', None)
d.pop('globs', None)
yaml.safe_dump(d, open('/tmp/mdl/.markdownlint-cli2.yaml','w'), sort_keys=False)
"
cd /tmp/mdl && npx --yes markdownlint-cli2 "*.md"
```

The `globs` pop is defensive: this repo's config has no `globs` key today, so
the line is a no-op against the current file. It matters because a config
`globs` list does not narrow the command-line argument, it adds to it.
Measured with markdownlint-cli2 v0.23.2: a scratch config carrying
`globs: ['other.md']`, invoked as `markdownlint-cli2 "target.md"`, printed
`Finding: target.md other.md` and `Linting: 2 files`. The verification step
below would then read `2` where you expected `1`, and the summary would mix a
file you did not ask about into the result you are reading.

Confirm the output says `Linting: 1 file` before you read the summary. If it
says `Linting: 0 files` you are still being excluded and the result is
meaningless. Keep the rest of the config: it travels intact for the reason given
under Implementation. Running with the stock default rule set instead produces
false positives, because this repo disables MD003, MD013, MD029, MD048, MD049,
MD050, and MD060 as of this writing. A default run on this memory reported 9
issues, every one of them MD013 line-length or MD060 table-style; the repo rules
with `ignores` stripped reported 0 at `Linting: 1 file`. That count moves with
every edit to this file, so re-run it rather than checking against the number.

Cost of not knowing this: two MD032 errors and a banned word survived into a
commit in `docs/autonomous-pr-monitor.md` because the in-tree run said clean.

## Anti-Pattern

- Disabling rules without documentation
- **Prevention**: Add inline comments explaining why
- Treating a green in-tree markdownlint run as proof a file is clean
- **Prevention**: Check `Linting: N files` shows N > 0, or lint out of tree

## Contradiction: ignores cannot protect process startup

The conventional answer is to put generated roots only in
`.markdownlint-cli2.yaml` `ignores`. That is insufficient when the caller
expands changed paths into command arguments before markdownlint starts.

Issue #4892 measured this failure on 2026-08-11. The branch target builder
included 4,149 untracked Markdown files under `worktrees/`,
`.agent-scratch/`, and `.scratch/`. Passing 4,168 arguments made
markdownlint-cli2 0.23.1 exit 249 before it emitted a finding. The caller then
printed MD040 and MD033 advice despite receiving no lint-rule output.

The fix needs both layers:

1. `scripts/validation/checks_dash.py:_VENDORED_PREFIXES` filters those three
   root prefixes before `checks_tooling._markdown_lint_targets` builds argv.
2. `.markdownlint-cli2.yaml` ignores the same roots during config-driven scans.
3. `checks_tooling.validate_markdown_lint` batches at 100 targets and 7,500
   UTF-16 code units, then reports the real exit code and output stream.

Verification on the issue branch selected all three probe paths before the fix
and zero after it. Targeted tests cover root prefixes, nested lookalikes,
count-based batching, non-BMP Windows command length, continued autofix after
one failed batch, and empty-output failure reporting.

## Related

- [linting-autofix](linting-autofix.md)
- [linting-config](linting-config.md)
- [linting-generic-types](linting-generic-types.md)
- [linting-language-identifiers](linting-language-identifiers.md)
