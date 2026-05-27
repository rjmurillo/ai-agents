# Skill Eval Triage

Per-skill classification for the 71 skills under `.claude/skills/`. Decides which skills get an agent-vs-baseline spike under `evals/<skill>-spike/` and which are excluded with rationale.

## Scope

This triage covers every `.claude/skills/<name>/SKILL.md` present on `feat/evals-skill-coverage` at 2026-05-26. It extends the prior 15-skill triage (`.serena/memories/skills/triage-eval-2026-05-09.md`) to full skill coverage.

## Two eval systems

The repo runs two skill-related eval harnesses. They answer different questions and use different sources of truth.

| Harness | Source of prompts | Reports land in | Question |
|---|---|---|---|
| `scripts/eval/eval-knowledge-integration.py` | `tests/evals/skills/*.json` | `evals/reports/` | Does the skill's content add unique signal over a no-context baseline? |
| `scripts/eval/eval-agent-vs-baseline.py` | `evals/<spike>/fixtures/*.json` | `evals/<spike>/reports/` | Does an agent specialized for this task outperform a generic baseline? |

The 12 already-covered skills below live under the first harness. The eval-worthy scaffolds in this triage target the second harness because (a) the agent-vs-baseline shape suits skills that drive bounded agent outputs (findings, judgments, designs), and (b) the user requested coverage under `evals/`.

A skill can carry both kinds of eval. Adding an `evals/<skill>-spike/` does not deprecate its `tests/evals/skills/` entry; the two answer different questions.

## Classification

| Category | Count | Action |
|---|---|---|
| Already covered | 12 | No new artifact. Cross-referenced below. |
| Eval-worthy | 39 | Scaffold `evals/<skill>-spike/` with README + fixtures/README placeholders. |
| Utility-skip | 20 | No scaffold. Mechanical or deterministic skill; agent-vs-baseline shape is wrong. |
| **Total** | **71** | |

### Decision rule

A skill is **eval-worthy** when its output is an agent-generated **judgment, finding, design, recommendation, or analysis** whose quality varies with reasoning. A skill is **utility-skip** when its output is **deterministic given its inputs** (regex scan, file validation, lint pass/fail, mechanical wrapper around an external CLI). When the agent's interpretation is the value, scaffold. When the tool's output is the value, skip.

This rule does not say utility skills are unimportant. It says agent-vs-baseline is the wrong measurement; their correctness is verified by unit tests, not by comparing two model variants.

## Already covered (12)

These skills appear in `tests/evals/skills/triage-prompts.json` with six prompts each. The 2026-05-09 triage scored them against a no-context baseline. No new artifact required.

| Skill | Prior triage action (2026-05-09) |
|---|---|
| codebase-documenter | KEEP |
| curating-memories | INVESTIGATE |
| doc-accuracy | KEEP |
| exploring-knowledge-graph | INVESTIGATE |
| memory | DECOMPOSE |
| memory-documentary | KEEP |
| memory-enhancement | KEEP |
| session | KEEP |
| session-log-fixer | KEEP |
| session-migration | SUNSET (legacy migration) |
| session-qa-eligibility | FOLD (into `session` umbrella) |
| using-forgetful-memory | KEEP |

Note: prior triage also covered `doc-coverage`, `doc-sync`, `workflow`. Those skill directories were pruned. The `tests/evals/skills/triage-prompts.json` entries remain as deprecation trackers and are not in scope here.

## Eval-worthy (39, scaffold)

Each gets `evals/<skill>-spike/` with `README.md`, `fixtures/README.md`, `fixtures/.gitkeep`. Fixture authoring is left to the operator who owns the skill.

| Skill | Why eval-worthy |
|---|---|
| SkillForge | Meta-skill that recommends or creates skills. Recommendation quality varies with input shape. |
| adr-generator | Generates ADRs. Format adherence, decision quality, and template detection are judgment-bearing. |
| adr-review | Multi-agent debate orchestration. Verdict quality varies with agent reasoning. |
| analysis-provenance | Investigates code ownership. Conclusions depend on evidence gathering. |
| analyze | Multi-step codebase analysis producing prioritized findings. Pure judgment skill. |
| book-to-skill | Extracts method from a book and hands off to SkillForge. Extraction fidelity is judgment. |
| buy-vs-build-framework | Strategic four-phase evaluation. Recommendation varies with reasoning. |
| chaos-experiment | Designs chaos experiments. Hypothesis and injection-plan quality vary. |
| chestertons-fence | Historical-context investigation. Conclusions depend on archaeology depth. |
| code-qualities-assessment | Scores cohesion, coupling, encapsulation, testability, non-redundancy. Judgment-bearing rubric. |
| context-gather | Delegates to context-retrieval. Coverage breadth is the eval target. |
| context-optimizer | Decides Skill vs Passive Context vs Hybrid placement. Pure judgment. |
| cva-analysis | Abstraction discovery via commonality/variability matrix. Pattern emergence is judgment. |
| cynefin-classifier | Classifies problems into Cynefin domains. Classification accuracy is the eval target. |
| decision-critic | Stress-tests reasoning. Surface quality of adversarial perspectives is judgment. |
| golden-principles | Scans for principle violations with remediation. Remediation quality is judgment. |
| incoherence | Detects contradictions between docs and code. Recall and precision are agent-driven. |
| merge-resolver | Resolves conflicts by analyzing intent. Resolution quality varies with reasoning. |
| negotiation | Offer analysis, counter-proposal drafting. Pure judgment. |
| orphan-ref-validator | Detects orphaned references. Triage of false-positives is judgment. |
| panning-for-gold | Triage of unstructured input into thread inventories. Extraction quality is judgment. |
| planner | Decomposes tasks into milestones. Decomposition quality is judgment. |
| pr-comment-responder | Comment triage and response. Acknowledgment quality varies. |
| pre-mortem | Prospective hindsight on project risks. Risk identification depth is judgment. |
| programming-advisor | Evaluates existing solutions before custom build. Recommendation varies. |
| prompt-engineer | Optimizes system prompts. Pattern selection is judgment. |
| quality-grades | Grades quality per domain with gap tracking. Grading is judgment. |
| reflect | Extracts HIGH/MED/LOW confidence patterns. Pattern recognition is judgment. |
| requirements-interview | Adversarial requirements elicitation. Question coverage is judgment. |
| research-and-incorporate | External research synthesis. Synthesis quality is judgment. |
| review | Nine-axis review across six canonical axes plus three chained skills. Pure judgment surface. |
| serena-code-architecture | Architectural analysis using Serena symbols. Architecture conclusions are judgment. |
| slashcommandcreator | Meta-skill for slash commands. Command design is judgment. |
| slo-designer | Designs SLOs, SLIs, alerting thresholds. Design quality is judgment. |
| threat-modeling | OWASP STRIDE matrix generation. Risk-rating accuracy is judgment. |
| using-serena-symbols | Guidance for symbol analysis. Output adherence is the eval target. |
| validation-authority | Treat upstream validators as authoritative. Behavior under conflict is judgment. |
| work-operating-model | Five-layer interview eliciting team operating model. Elicitation depth is judgment. |
| world-model-diagnostic | Twenty-minute paradigm diagnostic. Diagnostic accuracy is judgment. |

## Utility-skip (20, no scaffold)

Mechanical or deterministic skills. Agent-vs-baseline does not measure their correctness. Unit tests under `.claude/skills/<name>/tests/` are the right verification surface.

| Skill | Why no scaffold |
|---|---|
| codeql-scan | Wraps CodeQL CLI. Output deterministic given the database. |
| encode-repo-serena | Mechanical population of Forgetful from Serena symbols. |
| execution-plans | CRUD on versioned plan artifacts. |
| fix-markdown-fences | Regex repair of malformed fences. |
| git-advanced-workflows | Guidance document (passive context territory). |
| github | Wrapper around `gh` operations. |
| github-url-intercept | Blocking intercept rule; routing decision, no judgment surface. |
| guard-maturity | Aggregates EVENT lines emitted by push guards. |
| metrics | Collects from git history. |
| observability | Queries JSONL event logs. |
| pipeline-validator | Discovers/triggers/monitors ADO pipelines. |
| security-detection | File-path classification. |
| security-scan | Regex scan for CWE-78. |
| session-end | Validates session logs. |
| session-init | Creates JSON logs from auto-derived state. |
| steering-matcher | Glob-pattern matcher. |
| stuck-detection | Topic-signature similarity check. |
| style-enforcement | Validates code against `.editorconfig`/StyleCop. |
| taste-lints | Lints with remediation. |
| windows-image-updater | Automated Windows-container image bump. |

A utility skill that grows a judgment surface (e.g., a future scoring or ranking step) should be reclassified.

## Cross-references

- `.serena/memories/skills/triage-eval-2026-05-09.md`. Prior 15-skill triage.
- `tests/evals/skills/triage-prompts.json`. Knowledge-integration prompt source.
- `scripts/eval/eval-knowledge-integration.py`. Knowledge-integration runner.
- `scripts/eval/eval-agent-vs-baseline.py`. Agent-vs-baseline runner.
- `evals/README.md`. Eval directory scope.
- `evals/security-spike/`. First production agent-vs-baseline spike.
- `evals/reviewer-asymmetry-spike/`. Second production spike (prompt-change).
- ADR-057. Prompt behavioral evaluation.
- REQ-004 / DESIGN-004 / `.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md`. Agent-vs-baseline harness origin.
