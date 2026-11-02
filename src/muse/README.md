# Muse plugin packs

The project-toolkit skills, ported for Muse (Meta's personal agent).
Muse consumes skills as plain directories holding a `SKILL.md`, so this
tree keeps the two-pack split from `src/hermes/` and reduces each
`SKILL.md` frontmatter to the two fields Muse custom skills use:
`name` and `description`. Bodies are unchanged from the Hermes packs.

A pack holds the skills listed under it and one copy of `lib/`.
Skills in one pack never refer to skills in another pack.

## Install

```bash
src/muse/install.sh
```

This copies all 91 skills into `~/workspace/custom-skills`
(override with `MUSE_SKILLS_DIR`). Existing skill directories are
skipped unless `--force` is passed.

## Regenerate

The port is mechanical. After the Hermes packs change, re-run:

```bash
python3 src/muse/port.py
```

`port.py` copies `src/hermes/` again and re-applies the frontmatter
reduction. Do not hand-edit the copied trees; edit the Hermes packs or
the Claude sources and re-port.

## What did not port

- The 13 skills the Hermes port already excludes stay Claude Code only:
  `adr-review`, `cva-analysis`, `memory-gate`, `memory-maintenance`,
  `memory-reflexion`, `memory-search`, `planner`, `review`,
  `security-detection`, `security-scan`, `ship`, `spec-generator`,
  `stuck-detection`. The `memory-*` set would collide with Muse's own
  memory system; the rest are lifecycle front doors bound to the
  Claude Code harness.
- `plugin.json` manifests: Muse has no plugin manifest surface, so
  the packs ship without one.
- Claude Code `agents/`, `hooks/`, `hooks.json`, and `rules/` from
  `src/claude/`: no Muse equivalent surface. Out of scope for this port.

## project-toolkit-knowledge

Project Toolkit skills for memory, context, decisions, requirements, strategy, and documentation.

- `adr-generator`
- `analysis-provenance`
- `autoplan`
- `avoiding-manufactured-work`
- `business-strategy`
- `buy-vs-build-framework`
- `checkpoint`
- `chestertons-fence`
- `codebase-documenter`
- `context-gather`
- `context-hub-setup`
- `context-optimizer`
- `curating-memories`
- `cynefin-classifier`
- `decision-critic`
- `decision-question`
- `domain-design`
- `evidence-provenance`
- `memory`
- `memory-consolidate`
- `memory-documentary`
- `memory-enhancement`
- `negotiation`
- `panning-for-gold`
- `pre-mortem`
- `programming-advisor`
- `prompt-engineer`
- `prose-self-check`
- `reflect`
- `requirements-interview`
- `retro`
- `retrospective`
- `skill-bootstrap`
- `skillforge`
- `skillify`
- `skillopt`
- `software-engineering-library`
- `spec`
- `using-serena-symbols`
- `work-operating-model`
- `world-model-diagnostic`

## project-toolkit-delivery

Project Toolkit skills for GitHub pull request work, build, test, and quality gates, security review, and operations.

- `agent-harness-reference`
- `ai-agents-external-claims`
- `analyze`
- `api-doc-authoring`
- `benchmark-models`
- `build`
- `chaos-experiment`
- `code-qualities-assessment`
- `codeql-scan`
- `destructive-change-safety`
- `doc-accuracy`
- `dx-review`
- `execution-plans`
- `fix-markdown-fences`
- `git-advanced-workflows`
- `github`
- `github-url-intercept`
- `golden-principles`
- `maintainer-review`
- `merge-resolver`
- `metrics`
- `observability`
- `orphan-ref-validator`
- `pipeline-validator`
- `plan`
- `pr-autofix`
- `pr-comment-responder`
- `pr-quality-all`
- `pr-quality-analyst`
- `pr-quality-architect`
- `pr-quality-devops`
- `pr-quality-qa`
- `pr-quality-roadmap`
- `pr-quality-security`
- `pr-review`
- `push-pr`
- `quality-grades`
- `research`
- `reviewer-findings`
- `security-review`
- `slo-designer`
- `steering-matcher`
- `style-enforcement`
- `sync`
- `taste-lints`
- `test`
- `threat-modeling`
- `validate-pr-description`
- `validation-authority`
- `windows-image-updater`
