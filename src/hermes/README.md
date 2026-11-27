# Hermes plugin packs

Each folder below is a portable Agent Plugins v1 package for Hermes.
A pack holds the skills listed under it and one copy of `lib/`.
No skill links to a script, reference, or other support file in another pack by path.
Some skills name a skill or script from another pack.
Install every pack for the full set.

## project-toolkit-delivery

Project Toolkit skills for GitHub pull request work, planning, build, test, and review gates.

- `agent-harness-reference`
- `ai-agents-external-claims`
- `analyze`
- `api-doc-authoring`
- `benchmark-models`
- `build`
- `code-qualities-assessment`
- `doc-accuracy`
- `dx-review`
- `execution-plans`
- `git-advanced-workflows`
- `github`
- `github-url-intercept`
- `maintainer-review`
- `merge-resolver`
- `modernize`
- `orphan-ref-validator`
- `plan`
- `pr-autofix`
- `pr-babysit`
- `pr-comment-responder`
- `pr-review`
- `push-pr`
- `quality-grades`
- `research`
- `reviewer-findings`
- `steering-matcher`
- `sync`
- `takeover`
- `taste-lints`
- `test`
- `validate-pr-description`
- `validation-authority`

## project-toolkit-quality

Project Toolkit skills for security and reliability engineering, code and documentation standards, metrics, and independent model review.

- `chaos-experiment`
- `codeql-scan`
- `destructive-change-safety`
- `fix-markdown-fences`
- `golden-principles`
- `llm-council`
- `metrics`
- `observability`
- `security-review`
- `slo-designer`
- `sol-loop`
- `style-enforcement`
- `technical-writing`
- `threat-modeling`

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
- `reflect`
- `requirements-interview`
- `retrospective`
- `software-engineering-library`
- `spec`
- `using-serena-symbols`
- `work-operating-model`
- `world-model-diagnostic`

## project-toolkit-authoring

Project Toolkit skills for creating, measuring, and tuning skills, context placement, and agent prose.

- `context-optimizer`
- `prose-self-check`
- `skill-bootstrap`
- `skillforge`
- `skillify`
- `skillopt`

## project-toolkit-azure-devops

Project Toolkit skills for Azure DevOps pipeline validation and OneBranch pipeline image updates.

- `pipeline-validator`
- `windows-image-updater`

## Excluded skills

These skills ship in no pack.

- `adr-review`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `cva-analysis`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `memory-gate`: Refers to excluded skill(s): memory-search.
- `memory-maintenance`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `memory-reflexion`: Refers to excluded skill(s): memory-maintenance and memory-search.
- `memory-search`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `planner`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `pr-quality`: Refers to excluded skill(s): review.
- `review`: Refers to excluded skill(s): security-scan.
- `security-detection`: Refers to excluded skill(s): review.
- `security-scan`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).
- `ship`: Refers to excluded skill(s): review.
- `skill-doctor`: The bundled renderer asset exceeds Hermes' 1 MiB per-file limit.
- `spec-generator`: Refers to excluded skill(s): review.
- `stuck-detection`: plugin_guard returns dangerous for this skill (ADR-115 Decision 6).

## Excluded files

These files of a shipped skill ship in no pack.

- `build/references/rule-code-quality.md`: Folded path rule; references observability in the quality pack.
- `build/references/rule-csharp.md`: Folded path rule kept out of Hermes pack budget (PR #7541).
- `build/references/rule-powershell.md`: Folded path rule kept out of Hermes pack budget (PR #7541).
- `pr-comment-responder/references/rule-lossless-queue-reads.md`: Folded path rule kept out of Hermes pack budget (PR #7541).
- `push-pr/references/rule-push-lock.md`: Folded path rule kept out of Hermes pack budget (PR #7563).
- `retrospective/scripts/copilot_journal.py`: Needs the skill-doctor parser, which Hermes does not ship, so --journal always reports unavailable there.
- `test/references/rule-testing.md`: Folded path rule kept out of Hermes pack budget (PR #7563).
