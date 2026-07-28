# Skill-Lint-005: Exclude Generated Directories

**Statement**: Exclude generated artifact directories from linting using both globs and ignores

**Context**: Managing linting for mixed codebase with generated content

**Atomicity**: 90%

**Impact**: 8/10

## Implementation

In `.markdownlint-cli2.yaml`:

```yaml
ignores:
  - ".agents/**"
  - "node_modules/**"
  - "dist/**"
globs:
  - "!.agents/**"
```

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

This surface is large. At the time of writing, `ignores` held 44 patterns and
covered most of the markdown that gets edited here: `.claude/skills/**`,
`src/copilot-cli/skills/**`, `.serena/**`, `.agents/**`, `**/CLAUDE.md`,
`.github/agents/**/*.agent.md`, `docs/autonomous-pr-monitor.md`, and the five
lifecycle command files.

Both that count and the disabled-rule list below drift as the config changes.
Regenerate them instead of trusting this text:

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('.markdownlint-cli2.yaml'))
print('ignore patterns:', len(d.get('ignores', [])))
print('disabled rules:', sorted(k for k, v in d.get('config', {}).items() if v is False))
"
```

To actually lint an excluded file, copy it to a scratch directory outside the
repo, copy `.markdownlint-cli2.yaml` alongside it, and delete the `ignores` and
`globs` keys from that copy. Keep the rest of the config. Running with the
stock default rule set instead produces false positives, because this repo
disables MD003, MD013, MD029, MD048, MD049, MD050, and MD060 as of this
writing. Linting this memory with defaults reported 9 issues; with the repo
rules and `ignores` stripped it reported 0 at `Linting: 1 file`.

Cost of not knowing this: two MD032 errors and a banned word survived into a
commit in `docs/autonomous-pr-monitor.md` because the in-tree run said clean.

## Anti-Pattern

- Disabling rules without documentation
- **Prevention**: Add inline comments explaining why
- Treating a green in-tree markdownlint run as proof a file is clean
- **Prevention**: Check `Linting: N files` shows N > 0, or lint out of tree

## Related

- [linting-autofix](linting-autofix.md)
- [linting-config](linting-config.md)
- [linting-generic-types](linting-generic-types.md)
- [linting-language-identifiers](linting-language-identifiers.md)
