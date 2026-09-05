# Prior Art: OpenAI's Curated `openai-docs` Skill and Its Curation Model

**Date**: 2026-09-05
**Source**: `openai/skills`, `skills/.curated/openai-docs/SKILL.md`, pinned at commit `49f948faa9258a0c61caceaf225e179651397431` (2026-06-23)
**Local checkout used for evidence**: `/home/user/openai/skills` (shallow clone, read-only)
**This repo at**: `5f7a987b2e990c41069b9f0b02061746c461ee9d`
**Named consumer**: Issue #5384 (classify every skill's routing role and gate uncategorized catalog growth), parent epic #5390.

> **Provenance caution.** `openai/skills` carries a deprecation banner in its `README.md`: the repository is deprecated and current Codex skill and plugin examples live at `github.com/openai/plugins` (verified reachable, HTTP 200, 2026-09-05). Everything below is evidence from the deprecated tree at the pinned commit. Treat the patterns as prior art, not as a live contract. Re-verify against `openai/plugins` before citing any of it as current OpenAI guidance.

---

## Executive summary

OpenAI ships a skill catalog with an explicit distribution tier that this repo does not have, and that gap is measurable in tokens.

| Measure | `openai/skills` | `rjmurillo/ai-agents` |
|---|---|---|
| Skills always loaded | 5 (`skills/.system/`) | 94 (the whole `.claude` tree ships as one `project-toolkit` plugin) |
| Description budget always in context | ~1,864 chars, ~466 tokens | ~39,909 chars, ~9,977 tokens |
| Skills loaded only on opt-in install | 39 (`skills/.curated/`, installed by name) | 0 |
| Median `SKILL.md` size | 7,126 bytes | 10,780 bytes |

Method: description budgets are the concatenated `description:` frontmatter values across each tier, whitespace-normalized, counted in characters and divided by 4 for a token estimate. Body sizes are `SKILL.md` file sizes. Both are reproducible from the commands in the Appendix.

The reading that matters for #5384: **routing role and distribution tier are different axes, and the manifest that issue asks for should carry both.** A skill classified `nested-helper` still pays its description cost in every session as long as it ships in the same always-installed bundle as the `front-door` skills. Role answers "who invokes it". Tier answers "is it loaded at all". OpenAI separates them; this repo currently has only the first axis in the design and neither axis enforced.

Beyond tiering, the `openai-docs` skill itself is a well-built example of a source-route skill: it names ordered lanes for authoritative facts, forbids treating them as interchangeable, and defines a terminal stop state. Six patterns from it are adoptable here. Three more are already covered by existing repo rules, which is useful as independent corroboration. Two should be rejected outright.

---

## 1. What the source actually is

`skills/.curated/openai-docs/` is 66 KB across 7 files:

| File | Bytes | Role |
|---|---|---|
| `SKILL.md` | 18,302 | The skill: source route, surface map, workflow, quality rules |
| `references/prompting-guide.md` | 14,338 | Bundled offline fallback |
| `references/upgrade-guide.md` | 11,308 | Bundled offline fallback |
| `references/latest-model.md` | 2,028 | Bundled offline fallback, self-declared as drift-prone |
| `scripts/fetch-codex-manual.mjs` | 16,085 | Fetch, verify, cache, and index the remote Codex manual |
| `scripts/resolve-latest-model-info.js` | 3,463 | Parse a machine-readable block out of a remote doc |
| `agents/openai.yaml` | 598 | Interface metadata plus a declared MCP dependency |

The tier layout is three-level by convention (`.system`, `.curated`, `.experimental`), though only `.system` and `.curated` exist in the tree at this commit. `README.md` gives each tier different install mechanics: `.system` is auto-installed with Codex, `.curated` installs by bare name through `$skill-installer`, `.experimental` requires the folder path or a full GitHub directory URL. Install friction rises with the tier's uncertainty. That is the curation control.

---

## 2. Adoptable patterns

### P1. Distribution tier is a separate axis from routing role

**Evidence.** `openai/skills/README.md` defines three install paths keyed to tier. The `.system` tier holds 5 skills; `.curated` holds 39. Descriptions for the 39 cost nothing until a user installs one.

**This repo.** `.claude-plugin/marketplace.json` declares two plugins: `claude-agents` (source `./src/claude`) and `project-toolkit` (source `./.claude`). `project-toolkit` ships the entire `.claude` tree, so installing it loads all 94 skill descriptions, ~9,977 tokens, whether or not a session ever routes to any of them. Issue #5384 already measured that only 43 of 95 skills are reachable from the `/autoplan` plus lifecycle surface and that 7 have no inbound reference at all.

**Recommendation.** Add a `distribution` field to the routing manifest #5384 specifies, with values along the lines of `core` (always shipped), `opt-in` (shipped in a separate bundle), and `deprecated`. Validate the pairing: a `nested-helper` or `explicit-only` skill in the `core` tier needs a written reason, because it is paying always-on description cost for a route that never fires from a cold session.

**Effort.** Small if folded into #5384's manifest work (one field plus one validator rule). Large as a retrofit after the manifest ships without it.

**Caveat I did not verify.** Whether Claude Code loads every installed skill's description eagerly or lazily is a harness behavior, not a repo fact. The 9,977-token figure is the size of the description corpus, not a measured context delta. Before this recommendation drives a split, run the measurement per `ai-agents-empirical-probe-toolkit`.

### P2. A source route with a per-claim terminal stop state

**Evidence.** `SKILL.md:41` states the manual and the docs MCP server are "different lanes, not interchangeable official-doc sources". `SKILL.md:64`: "If the manual resolves a Codex claim, answer from it and stop expanding sources for that claim". `SKILL.md:76`: if the route does not establish a claim, "return bounded uncertainty or route to support, an admin, or product feedback instead of widening the investigation."

**This repo.** `.claude/rules/search-before-building.md:48` bounds the search at three unproductive tool calls, per task. `.claude/skills/ai-agents-external-claims/SKILL.md:48` maps claim type to primary source. Neither defines what to output when the route is exhausted, and both bound per task rather than per claim. A task with four claims can therefore burn its budget on the first and go unsourced on the rest.

**Recommendation.** Give `ai-agents-external-claims` a terminal state named in the skill: when the primary source does not establish the claim, the output is a bounded-uncertainty statement naming what was searched and what remains unknown, not a widened search and not a confident paraphrase. Move the bound from per task to per claim.

**Effort.** Small. One section in one skill.

### P3. Capability facts come from a command result, never from a guess

**Evidence.** `SKILL.md:56`: "Treat helper availability as established by explicit read-only/no-shell policy or an actual command result. A guessed sandbox or guessed helper failure is not enough to switch to Docs MCP or web lookup."

**This repo.** `.claude/rules/universal.md:89` (MUST NOT 9) bans asserting an absence from a single probe. `.claude/rules/universal.md:15` (MUST 4) bans calling a red remote check cleared without equivalent evidence. Both were derived here from local incidents.

**Recommendation.** No change. This is independent convergence from an outside team on rules this repo already holds, which raises confidence in them. Worth citing in the rules' own evidence lines when they are next edited, per `ai-agents-external-claims`. Live example from this very session: the `serena` MCP server returned `CONNECT_TIMEOUT`, which is a command result and therefore admissible; guessing that serena is unconfigured would not be.

**Effort.** None.

### P4. A named-exclusion list beats "keep the diff minimal"

**Evidence.** `SKILL.md:129` enumerates exactly what a model upgrade must not touch: "historical docs, examples, eval baselines, fixtures, provider comparisons, provider registries, pricing tables, alias defaults, low-cost fallback paths, and ambiguous older model usage". `SKILL.md:130` adds SDK, tooling, IDE, plugin, shell, auth, and provider-environment migrations to the excluded set.

**This repo.** `.claude/rules/universal.md:30` (SHOULD 4) says "SHOULD NOT introduce unrelated refactors in a change. Keep the blast radius small." That is a principle a motivated agent can argue past, because "unrelated" is the thing under dispute. An enumerated list is checkable by a reviewer and by a validator.

**Recommendation.** In `ai-agents-change-control`, give each change class a named-exclusion list rather than a general minimality principle. The repo already has the incident record to populate it.

**Effort.** Small to medium, depending on how many change classes get lists.

### P5. Preserve the user's explicit target over the skill's default

**Evidence.** `SKILL.md:22`: "if the user names a target model like 'migrate to GPT-5.4', keep that requested target even if `latest-model.md` names a newer model. Mention newer guidance only as optional."

**This repo.** `builder-ethos.md` states User Sovereignty as the top of the precedence stack. That is doctrine. `SKILL.md:22` is the same rule reduced to a parameter-level instruction an agent cannot rationalize past: the named value wins over the skill's own reference data, and the newer option is offered, not applied.

**Recommendation.** Use it as the worked example in `builder-ethos.md`'s precedence stack. The doctrine currently has no example of a skill's own bundled data losing to a user-named value.

**Effort.** Small.

### P6. An escalation ladder for a missing dependency

**Evidence.** `SKILL.md:106-114`: run the install command yourself, then retry with escalated permissions plus a one-sentence justification, then ask the user to run it, then ask for a restart, then re-run the lookup. `agents/openai.yaml` makes that ladder possible by declaring the dependency as data: server name `openaiDeveloperDocs`, transport `streamable_http`, url `https://developers.openai.com/mcp`.

**This repo.** MCP servers are declared repo-wide in `.mcp.json` (`serena`, `deepwiki`), generated by `scripts/sync_mcp_config.py`. That is a workspace-level declaration, not a per-skill one: four skills reference `mcp__serena__*` tools in prose, and a search of `.claude/skills/` for a structured dependency declaration (`transport`, `streamable_http`, `mcpServers`, `type: mcp`) returned no matches, so nothing links a skill to the server it needs. No skill defines what to do when that server is unreachable either. `AGENTS.md` opens with a BLOCKING Serena init step whose fallback is a file path, which covers reads but not the general case. This session's `serena` connect timeout is the failure mode with no ladder.

**Recommendation.** Two parts. First, declare MCP dependencies as data in the skills that require them, so the failure is detectable rather than inferred from a tool error. Second, give the repo one ladder (retry once, then documented fallback, then report the unavailability in the run's output rather than silently degrading). The second half is partly covered by `.claude/rules/search-before-building.md:36` ("When search tools fail"), which already says to drop to the next source, name the failure in the response, and not retry a failed tool more than once per task; the gap is that it covers search tools only and has no install-or-escalate step.

**Effort.** Medium. Touches multiple skills; belongs behind its own issue, not folded into #5384.

### P7. A remote-first reference whose bundled fallback declares its own staleness

**Evidence.** `references/latest-model.md:3`: "This file is a curated helper. Every recommendation here must be verified against current OpenAI docs before it is repeated to a user." Line 37: "If this file conflicts with current docs, the docs win." `SKILL.md:23` and `SKILL.md:127` require the agent to disclose when it fell back to the bundled copy.

**This repo.** `agent-harness-reference` already does the harder version of this: it records versioned probes, dates its verification (`Verified 2026-07-22`), and inverts the precedence so that an empirical probe beats a vendor doc rather than the reverse. That inversion is correct for runtime behavior and is the right call for this repo's evidence rules.

**Recommendation.** Adopt only the disclosure half: when a skill answers from a bundled copy rather than the live source, say so in the output. `agent-harness-reference` records staleness in the file but does not require the answer to carry the disclosure.

**Effort.** Small.

---

## 3. Where this repo is ahead

Recording these so a future reader does not import the weaker form.

1. **Probe beats doc.** `agent-harness-reference` treats a versioned runtime probe as stronger evidence than vendor documentation and keeps both sides on conflict. `openai-docs` treats the doc as source of truth by default (`SKILL.md`, Quality rules) and only prefers current-session behavior when it conflicts (`SKILL.md:70`). This repo's ordering came from the #2205 and #2290 incidents and should not be relaxed toward the doc-first form.
2. **Manufactured-work front gate.** `avoiding-manufactured-work` and the `front-gate-before-pipeline` pattern have no counterpart in the `openai-docs` skill.
3. **Scope-creep enforcement is executable.** This repo's gates run in CI. `openai-docs`'s exclusion list is prose an agent chooses to honor. The pattern in P4 is worth importing; the enforcement model is not something to trade away.

---

## 4. Rejected: do not port

1. **The `openai-docs` skill itself.** It depends on Codex-only MCP tools (`mcp__openaiDeveloperDocs__search_openai_docs`, `fetch_openai_doc`, `get_openapi_spec`), a Codex-specific manual URL, and Codex surface nouns (`.codex/config.toml`, thread automations). This repo's agents do not build on OpenAI APIs, so porting it would produce a skill with no consumer, which `avoiding-manufactured-work` exists to stop. The bundled model table in `references/latest-model.md` would also be a maintenance liability: it lists model IDs that will drift and that no consumer here reads.
2. **The Node.js helper scripts.** ADR-042 mandates Python for new scripts and `AGENTS.md` forbids new bash scripts; adding Node helpers would cut across both. The techniques inside `fetch-codex-manual.mjs` are worth knowing (freshness by `x-content-sha256` header comparison, atomic write via temp file plus rename, `curl` fallback when proxy environment variables are set, abort-controller timeouts, and a generated heading-to-line-range outline so the agent reads targeted sections of a large fetched file). If the repo ever needs a cached remote corpus, reimplement those techniques in Python rather than porting the file.
3. **A parallel interface manifest.** `agents/openai.yaml` carries display name, icons, and a default prompt alongside the dependency declaration. Claude Code plugins have their own manifest contract; inventing a second one would fight `ai-agents-generation-and-release`. Take only the dependency-as-data idea from P6.

---

## 5. Also noted: the surface map gap

`SKILL.md:80-94` lists nine durable-instruction surfaces (prompt or thread context, `AGENTS.md`, project config, global config, skill, plugin, MCP server or connector, automation, hook), tells the agent to pick the smallest surface matching the scope, and adds a split rule: "Split mixed-scope requests instead of forcing one answer", with a worked example ("always do X, but only for this PR").

`.claude/rules/universal.md:103` has the equivalent section, "Choosing a persistence surface", with three tiers: ephemeral, retrieval aid, and durable rule file. The repo has more surfaces than the section names. Missing from it: hooks, slash commands, agent templates, ADRs, and skills themselves. There is also no split rule, so a mixed-scope request ("always run the dash check, but only on this branch") has no documented answer.

This is a real gap in a rule file every session loads, so it is worth its own issue rather than a note buried here. Estimated effort: small. It is out of scope for this change, which is analysis only.

---

## 6. What I did not verify

- Whether Claude Code loads all installed skill descriptions eagerly. The P1 token figure is corpus size, not a measured context delta.
- Whether `openai/plugins` reproduces the `.system` and `.curated` tiering. Only the successor repo's reachability was checked.
- The `.experimental` tier's contents. `README.md` documents it; it does not exist in the tree at this commit.
- Any claim about how Codex behaves at runtime. Every Codex statement here is quoted from the deprecated tree, not probed.

---

## Appendix: reproducing the measurements

```bash
# This repo's canonical skill count
find .claude/skills -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l

# Description budget for a tier (character count, /4 for a token estimate)
python3 - <<'PY'
import re, glob
tot = 0
for f in glob.glob('.claude/skills/*/SKILL.md'):
    t = open(f, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---\n', t, re.S)
    if not m:
        continue
    d = re.search(r'^description:\s*(.*?)(?=^\w+:|\Z)', m.group(1), re.S | re.M)
    if d:
        tot += len(' '.join(d.group(1).split()))
print(tot, 'chars ~', tot // 4, 'tokens')
PY

# The source tree, pinned
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/openai/skills
git -C skills rev-parse HEAD   # expect 49f948faa9258a0c61caceaf225e179651397431
```
