# Skills

A skill is a packaged workflow: steps, checks, and often scripts, for one kind of task. You can start a skill with a slash command, name it in your request, or let the agent load it when your request matches what it does.

Each page below covers one skill: when to use it, what to copy and paste, what you get, and the arguments and scripts advanced users reach for.

New here? Read [Agents and skills](../agents-and-skills.md) for how skills differ from agents, then [Call agents and skills](../call-agents-and-skills.md) for the exact syntax on your host.

## Start here

These skills cover the path from an idea to a merged pull request. Most people need only these at first.

| You want to | Claude Code (plugin install) | GitHub Copilot CLI |
| --- | --- | --- |
| Not pick a skill at all. Describe the task and let the toolkit route it | `/project-toolkit:autoplan` | `Use the /autoplan skill to ...` |
| Turn an idea into testable requirements | `/project-toolkit:spec` | `Use the /spec skill to ...` |
| Break a spec into milestones and tasks | `/project-toolkit:plan` | `Use the /plan skill to ...` |
| Write the code, test-first | `/project-toolkit:build` | `Use the /build skill to ...` |
| Prove the change works | `/project-toolkit:test` | `Use the /test skill to ...` |
| Review the branch before merge | `/project-toolkit:review` | `Use the /review skill to ...` |
| Run pre-flight checks and open the pull request | `/project-toolkit:ship` | `Use the /ship skill to ...` |
| Answer review comments on a pull request | `/project-toolkit:pr-comment-responder` | `Use the /pr-comment-responder skill to ...` |

Claude Code puts plugin skills under the plugin's name, so you type the `project-toolkit:` prefix. In a Claude Code session inside a checkout of `rjmurillo/ai-agents`, the short form such as `/spec` also works. [Call agents and skills](../call-agents-and-skills.md) has the details.

## How to read the tables

The **Slash command** column tells you how the skill is meant to start:

- A command such as `/spec` marks a skill you start by typing it. Its `SKILL.md` sets `user-invocable: true`. Claude Code takes it as `/project-toolkit:spec` after a plugin install. In Copilot CLI, name it with a slash in your prompt: `Use the /spec skill to ...`.
- `by name` marks a skill with explicit-only routing: the `autoplan` router never picks it, so you start it by name. Say `Use the <name> skill to ...`, or in Claude Code type `/project-toolkit:<name>`.
- `match` marks a skill the agent loads on its own when your request matches. To ask for it on any host, say `Use the <name> skill to ...`. In Claude Code you can also type `/project-toolkit:<name>`.

## Lifecycle

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`autoplan`](autoplan.md) | match | Route any request to the right skill or agent chain |
| [`build`](build.md) | `/build` | Implement a planned change in thin, test-first slices |
| [`plan`](plan.md) | `/plan` | Break a spec into milestones, tasks, and a risk register |
| [`push-pr`](push-pr.md) | `/push-pr` | Commit, push, and open a pull request from the real diff |
| [`review`](review.md) | `/review` | Review a branch before merge, across risk-selected axes |
| [`ship`](ship.md) | `/ship` | Run four pre-flight checks, then open the pull request |
| [`spec`](spec.md) | `/spec` | Turn a problem into testable requirements |
| [`test`](test.md) | `/test` | Prove a change works across six gates |

## Pull requests and GitHub

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`git-advanced-workflows`](git-advanced-workflows.md) | match | Rebase, cherry-pick, bisect, and recover with reflog |
| [`github`](github.md) | match | Do PR, issue, label, and merge work through tested scripts |
| [`github-url-intercept`](github-url-intercept.md) | match | Read a pasted GitHub URL through the API, not a web page |
| [`maintainer-review`](maintainer-review.md) | by name | Decide to merge, request changes, supersede, or close |
| [`merge-resolver`](merge-resolver.md) | by name | Resolve merge conflicts from history and commit intent |
| [`modernize`](modernize.md) | `/modernize` | Check an old PR still belongs, then rebase, rework, or close it |
| [`pr-autofix`](pr-autofix.md) | `/pr-autofix` | Fix open PRs: review threads, CI failures, and auto-merge |
| [`pr-babysit`](pr-babysit.md) | `/pr-babysit` | Watch one PR through CI and review until it is ready |
| [`pr-comment-responder`](pr-comment-responder.md) | `/pr-comment-responder` | Work every review thread on one PR to a final status |
| [`pr-review`](pr-review.md) | `/pr-review` | Respond to comments on one or more PRs, then run the completion gate |
| [`reviewer-findings`](reviewer-findings.md) | match | Verify a review finding before you act on it |
| [`takeover`](takeover.md) | `/takeover` | Finish someone else's PR or branch and keep their credit |
| [`validate-pr-description`](validate-pr-description.md) | `/validate-pr-description` | Check a PR title and body against repository rules |

## PR quality axes

Each axis reviews your local diff and returns PASS, WARN, or CRITICAL_FAIL. Run them all with `/pr-quality-all`.

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`pr-quality-all`](pr-quality-all.md) | `/pr-quality-all` | Run all six axes against your working diff |
| [`pr-quality-analyst`](pr-quality-analyst.md) | `/pr-quality-analyst` | Judge code quality, blast radius, and upkeep cost |
| [`pr-quality-architect`](pr-quality-architect.md) | `/pr-quality-architect` | Judge design, boundaries, coupling, and ADR fit |
| [`pr-quality-devops`](pr-quality-devops.md) | `/pr-quality-devops` | Judge CI/CD, build, and infrastructure risk |
| [`pr-quality-qa`](pr-quality-qa.md) | `/pr-quality-qa` | Judge test coverage and error handling |
| [`pr-quality-roadmap`](pr-quality-roadmap.md) | `/pr-quality-roadmap` | Judge scope creep and user value |
| [`pr-quality-security`](pr-quality-security.md) | `/pr-quality-security` | Scan for vulnerabilities and exposed secrets |

## Memory and context

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`checkpoint`](checkpoint.md) | `/checkpoint` | Save a redacted snapshot of decisions and next steps |
| [`context-gather`](context-gather.md) | match | Collect memory, library docs, and web sources before you plan |
| [`context-hub-setup`](context-hub-setup.md) | `/context-hub-setup` | Check that the Serena and Context7 plugins are installed |
| [`curating-memories`](curating-memories.md) | match | Keep Serena memory files current and mark stale content |
| [`memory`](memory.md) | match | Find the right memory operation when you are not sure which |
| [`memory-consolidate`](memory-consolidate.md) | match | Merge and prune memory files in a reflective pass |
| [`memory-documentary`](memory-documentary.md) | match | Write an evidence-based report from all memory systems |
| [`memory-enhancement`](memory-enhancement.md) | match | Add citations to memories and verify the code they point at |
| [`memory-gate`](memory-gate.md) | match | Search memory before you change something, as a blocking gate |
| [`memory-maintenance`](memory-maintenance.md) | match | Run memory health checks and cleanup |
| [`memory-reflexion`](memory-reflexion.md) | match | Record a session episode for later learning |
| [`memory-search`](memory-search.md) | match | Search project memory with a token budget |
| [`reflect`](reflect.md) | match | Capture corrections and patterns so the agent stops repeating mistakes |
| [`retrospective`](retrospective.md) | `/retrospective` | Run a structured retrospective on a session or task |
| [`using-serena-symbols`](using-serena-symbols.md) | match | Find symbols and references with Serena's language server |

## Security

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`codeql-scan`](codeql-scan.md) | match | Run CodeQL scans and get SARIF output |
| [`security-detection`](security-detection.md) | match | Spot changed files that need a security review |
| [`security-review`](security-review.md) | match | Bring security review knowledge into the current session |
| [`security-scan`](security-scan.md) | match | Scan for command injection patterns before a PR |
| [`threat-modeling`](threat-modeling.md) | match | Threat-model a system with STRIDE and the OWASP four questions |

## Safety and evidence

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`ai-agents-external-claims`](ai-agents-external-claims.md) | match | Check vendor and third-party claims against primary sources |
| [`analysis-provenance`](analysis-provenance.md) | `/analysis-provenance` | Find who owns a validator or linter before you change it |
| [`avoiding-manufactured-work`](avoiding-manufactured-work.md) | match | Stop extra work once the deliverable is done |
| [`chestertons-fence`](chestertons-fence.md) | `/chestertons-fence` | Learn why code exists before you remove or change it |
| [`decision-question`](decision-question.md) | match | Ask the user only when blocked, with a complete decision brief |
| [`destructive-change-safety`](destructive-change-safety.md) | `/destructive-change-safety` | Prove blast radius and recovery before a delete or overwrite |
| [`evidence-provenance`](evidence-provenance.md) | `/evidence-provenance` | Check whether evidence is independent and a check really ran |
| [`prose-self-check`](prose-self-check.md) | match | Catch AI-sounding phrasing in the agent's own writing |
| [`stuck-detection`](stuck-detection.md) | match | Detect agent loops and nudge a change of approach |
| [`validation-authority`](validation-authority.md) | match | Treat the upstream validator as the authority and align to it |

## Code quality

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`analyze`](analyze.md) | `/analyze` | Analyze a codebase and get ranked findings with file and line |
| [`code-qualities-assessment`](code-qualities-assessment.md) | match | Score maintainability on cohesion, coupling, and three more qualities |
| [`cva-analysis`](cva-analysis.md) | match | Find the right abstraction with commonality and variability analysis |
| [`golden-principles`](golden-principles.md) | match | Scan for golden principle violations with fixes an agent can apply |
| [`quality-grades`](quality-grades.md) | match | Grade each domain and layer from A to F |
| [`style-enforcement`](style-enforcement.md) | match | Check code against `.editorconfig` and StyleCop rules |
| [`taste-lints`](taste-lints.md) | match | Run taste lints such as file size limits |

## Architecture and design

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`adr-generator`](adr-generator.md) | `/adr-generator` | Write an Architecture Decision Record |
| [`adr-review`](adr-review.md) | match | Run a multi-agent debate on an ADR until the agents agree |
| [`chaos-experiment`](chaos-experiment.md) | `/chaos-experiment` | Design a chaos engineering experiment |
| [`domain-design`](domain-design.md) | `/domain-design` | Design an API, schema, or module boundary from business behavior |
| [`observability`](observability.md) | match | Query agent logs and find slow or failing tool calls |
| [`programming-advisor`](programming-advisor.md) | match | Check for an existing library or prior art before you build |
| [`slo-designer`](slo-designer.md) | match | Design SLOs with indicators, targets, and error budgets |
| [`software-engineering-library`](software-engineering-library.md) | match | Pull the right engineering reference for a design question |

## Planning and decisions

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`business-strategy`](business-strategy.md) | `/business-strategy` | Match a founder problem to the right business framework |
| [`buy-vs-build-framework`](buy-vs-build-framework.md) | match | Decide whether to build, buy, partner, or wait |
| [`cynefin-classifier`](cynefin-classifier.md) | match | Classify a problem as clear, complicated, complex, or chaotic |
| [`decision-critic`](decision-critic.md) | match | Stress-test the reasoning behind one decision |
| [`execution-plans`](execution-plans.md) | match | Keep a versioned plan with progress and a decision log |
| [`negotiation`](negotiation.md) | match | Analyze an offer and draft a counter-proposal |
| [`panning-for-gold`](panning-for-gold.md) | match | Sort a transcript or brain dump into threads worth keeping |
| [`planner`](planner.md) | match | Draft and run a plan one numbered step at a time |
| [`pre-mortem`](pre-mortem.md) | match | Imagine the project failed and list the risks that caused it |
| [`requirements-interview`](requirements-interview.md) | `/requirements-interview` | Get grilled on a design until the requirements are testable |
| [`spec-generator`](spec-generator.md) | `/spec-generator` | Write requirements, design, and task specs with EARS syntax |
| [`sync`](sync.md) | `/sync` | Find specs that point at code that changed or no longer exists |
| [`work-operating-model`](work-operating-model.md) | match | Interview a team about how it really works |
| [`world-model-diagnostic`](world-model-diagnostic.md) | match | Map a team's knowledge to the right world-model approach |

## Documentation and research

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`api-doc-authoring`](api-doc-authoring.md) | `/api-doc-authoring` | Write API docs around a developer task, with tested examples |
| [`codebase-documenter`](codebase-documenter.md) | match | Scaffold README, architecture, and API docs from templates |
| [`doc-accuracy`](doc-accuracy.md) | match | Check docs against the code and list what is wrong |
| [`dx-review`](dx-review.md) | `/dx-review` | Audit developer experience: onboarding, setup, and first run |
| [`fix-markdown-fences`](fix-markdown-fences.md) | match | Repair broken Markdown code fences |
| [`orphan-ref-validator`](orphan-ref-validator.md) | match | Find specs and plans that name skills or scripts that do not exist |
| [`research`](research.md) | `/research` | Research a topic in depth and map it onto your project |

## Skill and agent authoring

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`agent-harness-reference`](agent-harness-reference.md) | match | Look up hook contracts for Claude Code and Copilot CLI |
| [`benchmark-models`](benchmark-models.md) | match | Run one prompt through several models side by side |
| [`context-optimizer`](context-optimizer.md) | `/context-optimizer` | Decide where skill content should live and compress it |
| [`metrics`](metrics.md) | by name | Measure agent usage from git history |
| [`prompt-engineer`](prompt-engineer.md) | by name | Improve a system prompt with proven patterns |
| [`skill-bootstrap`](skill-bootstrap.md) | `/skill-bootstrap` | Mine a repository's history to write its first project skills |
| [`skill-doctor`](skill-doctor.md) | `/skill-doctor` | Score how skills performed in recent sessions and draft fixes |
| [`skillforge`](skillforge.md) | `/skillforge` | Find, improve, or create the right skill for a goal |
| [`skillify`](skillify.md) | `/skillify` | Turn a workflow you just finished into a reusable skill |
| [`skillopt`](skillopt.md) | `/skillopt` | Improve a skill or prompt with small patches and held-out tests |
| [`steering-matcher`](steering-matcher.md) | match | Match file paths to the steering guidance that applies |

## CI and pipelines

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`pipeline-validator`](pipeline-validator.md) | by name | Trigger and watch Azure DevOps validation pipelines |
| [`windows-image-updater`](windows-image-updater.md) | by name | Move OneBranch pipelines to a newer Windows container image |

## Repository maintenance (this repository only)

These skills live only in a checkout of `rjmurillo/ai-agents`. They help people who maintain the toolkit itself. A plugin install does not include them.

| Skill | Use it to |
| --- | --- |
| [`ai-agents-architecture-contract`](ai-agents-architecture-contract.md) | Check a change against this repository's settled design decisions |
| [`ai-agents-build-and-env`](ai-agents-build-and-env.md) | Rebuild the development environment from scratch |
| [`ai-agents-change-control`](ai-agents-change-control.md) | Classify a change and find the gates it must pass |
| [`ai-agents-config-catalog`](ai-agents-config-catalog.md) | Look up an environment variable, marker, or config key |
| [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) | Go from a symptom, such as a blocked push, to its triage steps |
| [`ai-agents-diagnostics-toolkit`](ai-agents-diagnostics-toolkit.md) | Find the right measurement command and its baseline |
| [`ai-agents-docs-of-record`](ai-agents-docs-of-record.md) | Write ADRs, retrospectives, and memories in the right place |
| [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md) | Prove a runtime claim with a probe instead of a guess |
| [`ai-agents-failure-archaeology`](ai-agents-failure-archaeology.md) | Look up a past incident before you repeat it |
| [`ai-agents-generation-and-release`](ai-agents-generation-and-release.md) | Run the generators and the release process |
| [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md) | Port a hook change across Claude Code and Copilot CLI |
| [`ai-agents-research-frontier`](ai-agents-research-frontier.md) | See the open research programs and where they stand |
| [`ai-agents-research-methodology`](ai-agents-research-methodology.md) | Take a hunch to an accepted result |
| [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md) | Learn what counts as evidence and how to produce it |
| [`repository-completion-proof`](repository-completion-proof.md) | Prove a PR is complete after review or recovery |
| [`repository-consumer-proof`](repository-consumer-proof.md) | Verify installed hooks behave right, beyond a green build |
| [`repository-pr-recovery`](repository-pr-recovery.md) | Find why a PR is blocked or a check is missing |

## Related

- [Agents](../agents/README.md): the specialists that run these skills.
- [Lifecycle commands](../workflow-commands.md): the six lifecycle skills in one reference.
- [Write a skill](../SKILL-AUTHORING.md): how to author a new skill.
