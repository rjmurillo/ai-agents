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
| `frontmatter.py` | Internal helper module: shared YAML frontmatter parsing (imported, not run directly) |
| `_constants.py` | Internal helper module: shared constants and thresholds (imported, not run directly) |
| `_inflection.py` | Internal helper module: shared word-inflection matching for discovery and triage (imported, not run directly) |

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
