# Scripts and validation

Read this from `SKILL.md` before you pick a script, act on a validator's exit
code, or validate a skill that lives in another checkout.

## Scripts

| Script | Purpose |
|--------|---------|
| `triage_skill_request.py` | Phase 0 triage: classify an input and route to build, improve, or reuse |
| `discover_skills.py` | Ecosystem scan: enumerate existing skills before creating a new one |
| `init_skill.py` | Scaffold a new skill directory from the standard structure |
| `validate-skill.py` | Full validation of a generated skill against SkillForge standards |
| `quick_validate.py` | Fast structural check of frontmatter and required sections |
| `skill_modularity_audit.py` | Audit SKILL.md size and flag progressive-disclosure violations |
| `package_skill.py` | Package a completed skill for distribution |
| `check_docs_safety.py` | Safety scan of generated documentation |
| `conformance.py` | agentskills.io conformance: every spec and guide rule, with its level and source |
| `frontmatter.py` | Internal helper module: shared YAML frontmatter parsing (imported, not run directly) |
| `_constants.py` | Internal helper module: shared constants and thresholds (imported, not run directly) |
| `_inflection.py` | Internal helper module: shared word-inflection matching for discovery and triage (imported, not run directly) |
| `_conformance_parse.py`, `_conformance_checks.py`, `_conformance_files.py`, `_conformance_rules.py`, `_conformance_guides.py` | Internal helper modules for `conformance.py`: the frontmatter reader, the static checks, and the spec and guide rule catalogs (imported, not run directly) |

## Validator exit codes and `--root`

Every validator takes the skill directory and answers `--help`. `skill_modularity_audit.py`
exits `0` without `--ci` even for an oversized skill; with `--ci` it exits `1`. In either mode it
exits `2` when it audited nothing (wrong path, or every `SKILL.md` unreadable). With `--ci`, any
unreadable `SKILL.md` also exits `2`. An exit `2` is never a pass.

To validate a skill in another checkout without `cd` or copying, pass
`--root DIR` to `quick_validate.py` or `validate-skill.py`. The skill must
resolve inside `DIR`. A symlinked skill directory, `SKILL.md`, or
script file that escapes it is rejected. The default root stays the
current directory, and an absolute path outside it is still rejected without
`--root`. A relative skill path resolves against the current directory, not
against `DIR`, so pass an absolute path with `--root`:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/skillforge/scripts/quick_validate.py /other/repo/skills/my-skill --root /other/repo; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

## agentskills.io conformance

`conformance.py` checks a skill against the agentskills.io specification and
its skill-creation guides. Every rule has an id, a level, and the URL of the
section it comes from. Print the catalog with `--list`, and add `--format json`
for a machine-readable copy.

- **Levels.** MUST, SHOULD, and MAY follow the source page's wording. A
  guideline the page only recommends is SHOULD.
- **Automated or manual.** A rule a static check can decide runs as a check. A
  rule only a reader can judge, such as "says what the skill does and when to
  use it", reports MANUAL. Pass `--manual` to list those for review.
- **Static only.** The checks read files. They never run the skill's scripts.
- **Same verdict everywhere.** The frontmatter reader is standard library
  only and never uses PyYAML. A construct it does not read, such as an anchor
  or a tag, makes the dependent rules report NOT_EVALUATED, never PASS.
- **Name characters.** Like the reference validator `skills-ref`, the check
  accepts Unicode lowercase letters after NFKC normalization. The project
  validators accept ASCII only, which is stricter and still conforms.
- **Empty compatibility.** The spec says compatibility "must be 1-500
  characters if provided", so an empty value fails here. `skills-ref` checks
  only the maximum and accepts it.
- **File name.** The spec names the file `SKILL.md`, so a lowercase
  `skill.md` fails `spec.skill-md.present`. `skills-ref` accepts either.
- **Root boundary.** Every file the checks read stays inside `--root`, or
  inside the skill directory when no root is given. A symlink that leaves it
  is reported, never followed.

Statuses: PASS, FAIL (a MUST rule failed), WARN (a SHOULD or MAY rule failed),
DEVIATION, WAIVED, NOT_APPLICABLE (nothing to check), NOT_EVALUATED, and
MANUAL. Exit code `0` means no FAIL and no MUST rule NOT_EVALUATED. Exit code
`1` means a FAIL or a MUST rule NOT_EVALUATED; `--strict` also fails on WARN
and on any NOT_EVALUATED. Exit code `2` means a usage error, an unknown
`--waive` id, or a path that is missing, not a directory, or outside `--root`.

Profiles:

- `--profile spec`, the default, reports pure agentskills.io conformance. Use
  it for a skill you publish to other clients.
- `--profile project` reports this repository's declared deviations as
  DEVIATION with the reason, not as FAIL or WARN: harness fields at the top
  level, nested `metadata`, YAML-list `allowed-tools`, no PEP 723 blocks, and
  plugin-root script paths. `--list --profile project` shows each reason.

Pass `--waive RULE_ID` once per rule to report a failure your skill accepts
on purpose as WAIVED. Name the reason in the skill, not only in the command.
