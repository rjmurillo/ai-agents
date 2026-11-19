# EUREKA: Codex and Muse Code could run our agents; the blocker was our literal Task( syntax

## Question

Why do the Codex and Muse trees ship no agents, and is it because those hosts cannot run them?

## Conventional answer

"Codex and Muse cannot run our agents." The build skips any platform whose `artifacts` block has no `agents` stanza, and ADR-115 Decision 7 recorded that Codex loads custom agents only from `.codex/agents/`. The reasonable reading was that the hosts lack the capability.

## First-principles position

The host capability exists. What failed was our own text.

- Codex 0.167.1 loads custom agents from `.codex/agents/*.toml` and spawns them with `spawn_agent(agent_type=...)`. The gap is the plugin format, which has no `agents` field, so shipping them needs an install step.
- Muse Code agents are Markdown files with YAML frontmatter, close to `src/claude/agents/*.md`. The spawn tool is `subagent_spawn`.
- Nobody decided "no agents" for Muse. Muse copied the Codex skills-only tree (PR 7041).
- Shipped skills copied Claude's `Task(subagent_type="X")` and `AskUserQuestion` verbatim. Neither tool exists on those hosts. At `fa6a20250` on 2026-11-11, 20 files per tree named `Task(` and 15 named `AskUserQuestion`. A model following that text called a tool that does not exist.

Both the PR 7307 and PR 7309 changes are merged. ADR-115 Decision 13 now has the source text name the intent and each host's tool once, with a fallback when the host has no subagent tool.

## What is not proven

- The Codex and Muse agent branches (`feat/7226-codex-agents`, `feat/7226-muse-agents`) were not merged when this was written. The claim that the hosts can run our agents rests on Codex source read at tag `rust-v0.167.1`, Meta's published docs, and a login-free skill validation. No agent has been run end to end on either host.
- The Codex source paths and the Meta docs claims come from the research comment. This memory's author did not re-open them. The merged ADR-115 text and PR 7309 were read directly.
- The logged-in Muse Code check required by ADR-115 Decision 8 was not done.
- Muse names two products. Decision 13 targets Muse Code. The Muse personal agent documents no spawn tool.

## Evidence

- Issue 7226, research comment dated 2026-11-11 (`issue-7226-part3-research`), with Codex source paths pinned to `rust-v0.167.1`.
- PR 7307 (`828bf6f78`): ADR-115 amendment. PR 7309 (merged 2026-11-11): names each host's spawn and ask tool. PR 7310 and PR 7312: review fallback and skill dispatch text.
- `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`, Decision 13, read on `origin/main` 2026-11-11.

## Relations

- **related_to**: [decision-codex-and-muse-have-login-free-commands-that-test-shipped-files](decision-codex-and-muse-have-login-free-commands-that-test-shipped-files.md)
