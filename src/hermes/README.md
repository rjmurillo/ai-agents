# Hermes plugin packs

Each folder below is a portable Agent Plugins v1 package for Hermes.
A pack holds the skills listed under it and one copy of `lib/`.
Skills in one pack never refer to skills in another pack.

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

## Excluded skills

These skills ship in no pack.

- `adr-review`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `cva-analysis`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `memory-gate`: Refers to excluded skill(s): memory-search.
- `memory-maintenance`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `memory-reflexion`: Refers to excluded skill(s): memory-maintenance and memory-search.
- `memory-search`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `planner`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `review`: Refers to excluded skill(s): security-scan.
- `security-detection`: Refers to excluded skill(s): review.
- `security-scan`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `ship`: Refers to excluded skill(s): review.
- `spec-generator`: Refers to excluded skill(s): review.
- `stuck-detection`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
