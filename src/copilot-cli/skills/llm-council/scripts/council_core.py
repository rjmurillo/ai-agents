"""Shared pieces of the LLM council: members, prompts, ranking, and the artifact.

No I/O and no model calls, so the script route (``council.py``) and the
delegate route (``council_steps.py``) build the same prompts and run the same
Borda count.

Flow (Karpathy-inspired, via thevgavini/ghcp-llm-council):
  1. N councillors answer in parallel.
  2. Each surviving councillor ranks all responses anonymously (Borda count).
  3. A chairman synthesizes the final answer.
"""

from __future__ import annotations

import datetime as dt
import re

# Models routed through Copilot CLI (frontier tier, charges AI Credits).
# Keep this list synchronized with `copilot help config`'s model catalog.
COPILOT_MODELS = {
    "claude-opus-5.5",
    "claude-opus-4.7",
    "claude-sonnet-5",
    "claude-sonnet-4.6",
    "claude-haiku-4.5",
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6.2-astra",
    "gpt-6.2-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5-mini",
    "gemini-3.8-flash",
    "gemini-4-argon",
    "grok-4.5",
    "grok-4.7",
    "kimi-k3",
}

# Task-shaped frontier councils. The ordering documents the primary lens for
# the shape; every surviving response is still ranked.
COUNCILS_BY_MODE = {
    # Astra: ambiguous objectives and acceptance ownership; Opus: broad judgment.
    "general": ["gpt-6.2-astra", "claude-opus-5.5", "gpt-6.2-sol", "grok-4.7"],
    "design": ["gpt-6.2-astra", "claude-opus-5.5", "gpt-6.2-sol", "grok-4.7"],
    # Sol handles technical reasoning. Grok checks assumptions and evidence.
    "plan": ["gpt-6.2-astra", "gpt-6.2-sol", "grok-4.7", "claude-opus-5.5"],
    "research": ["gpt-6.2-sol", "claude-opus-5.5", "grok-4.7", "gpt-6.2-astra"],
    "review": ["gpt-6.2-sol", "claude-opus-5.5", "grok-4.7", "gpt-6.2-astra"],
}
DEFAULT_COUNCIL = COUNCILS_BY_MODE["general"]
CHAIRMEN_BY_MODE = {
    "general": "gpt-6.2-astra",
    "design": "gpt-6.2-astra",
    "plan": "gpt-6.2-astra",
    "research": "claude-opus-5.5",
    "review": "claude-opus-5.5",
}
DEFAULT_CHAIRMAN = CHAIRMEN_BY_MODE["general"]

# Cheap-tier council (no AI Credits).
CHEAP_COUNCIL = [
    "meta/llama-3.3-70b-instruct",
    "deepseek/deepseek-v3-0324",
    "mistral-ai/mistral-medium-2505",
    "openai/gpt-4.1",
]
CHEAP_CHAIRMAN = "openai/gpt-4.1"
DEFAULT_MIN_RESPONSES = 3

COUNCILLOR_PROMPT = """You are a councillor on a panel of LLMs answering a user's question.

Constraints:
- Answer from your own knowledge only.
- Do not use any tools.
- Do not read files. Do not search. Do not browse the web.
- Be concise but substantive. Aim for 4-8 short paragraphs unless the question is trivial.
- Do not refer to other councillors; your peers are answering the same question independently.
- Do not preface with "Great question" or similar filler.

The user's question follows.
"""

RANKER_PROMPT = """You are evaluating different responses to the following question:

Question: {question}

Here are the responses from different models (anonymised):

{responses}

Your task:
1. First, evaluate each response individually. For each, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add other text in the ranking section

Constraints: answer from your own knowledge only. Do not use tools.
"""

_CHAIRMAN_HEAD = """QUESTION:
{question}

STAGE 1: {stage1_label}
{stage1}

STAGE 2: {stage2_label}
{stage2}

"""

_CHAIRMAN_TASKS = {
    "general": (
        "You are the Chairman synthesizing a final answer for the user.",
        "each councillor's first opinion (with model attribution):",
        "peer rankings (each councillor ranked the anonymised responses):",
        "Your task: write the final synthesis. Lead with the answer (decision, recommendation, or "
        "finding) in the first sentence. Integrate the strongest reasoning across councillors. Where "
        "they disagreed, name the disagreement and pick a side with justification. Surface anything "
        'the council MISSED that you can add from your own knowledge. Do not pad. No "Great '
        'question" filler. No "I" or "we" voice; write as the verdict.',
    ),
    "review": (
        "You are the Chairman synthesizing a code review.",
        "each councillor's review:",
        "peer rankings:",
        "Produce the final review: severity-ordered findings (CRITICAL / HIGH / MEDIUM / LOW), "
        "one-line root cause per finding, concrete fix. Cite line numbers when councillors did. "
        "Where councillors disagreed on a finding, name the disagreement and pick a side. Skip "
        "kudos sections.",
    ),
    "design": (
        "You are the Chairman synthesizing an architectural decision.",
        "each councillor's take:",
        "peer rankings:",
        "Lead with the recommendation in sentence one. Then: (a) the load-bearing tradeoffs the "
        "council surfaced, (b) where councillors disagreed and which side wins, (c) what the "
        "council MISSED that's worth naming, (d) the concrete next move.",
    ),
    "plan": (
        "You are the Chairman synthesizing an implementation plan.",
        "each councillor's plan:",
        "peer rankings:",
        "Produce a numbered step-by-step plan. Each step: action + expected output + how to "
        "verify. Order by dependency. Where councillors disagreed on sequencing, pick one and "
        "justify in a footnote.",
    ),
    "research": (
        "You are the Chairman synthesizing a research summary.",
        "each councillor's explanation:",
        "peer rankings:",
        "Synthesize the explanation. Where councillors disagreed on a fact or framing, name the "
        "disagreement and flag which side appears better supported (and why). Do not invent "
        "citations.",
    ),
}
MODES = tuple(_CHAIRMAN_TASKS)


def safe_substitute(template: str, replacements: dict[str, str]) -> str:
    """Single-pass placeholder substitution that prevents injection.

    Unlike chained .replace() calls, this replaces all placeholders at once,
    so values containing placeholder-like text are not affected by later
    substitutions.
    """
    if not replacements:
        return template
    pattern = re.compile("|".join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], template)


def chairman_template(mode: str) -> str:
    """Return the chairman prompt template for ``mode``."""
    intro, stage1_label, stage2_label, task = _CHAIRMAN_TASKS[mode]
    head = _CHAIRMAN_HEAD.replace("{stage1_label}", stage1_label).replace(
        "{stage2_label}", stage2_label
    )
    return f"{intro}\n\n{head}{task}\n"


def is_copilot_model(mid: str) -> bool:
    return mid in COPILOT_MODELS


def resolve_members(
    mode: str, models: str | None, cheap: bool, chairman: str | None
) -> tuple[list[str], str]:
    """Return (council, chairman) from the mode and any overrides."""
    if models:
        council = [m.strip() for m in models.split(",") if m.strip()]
    elif cheap:
        council = list(CHEAP_COUNCIL)
    else:
        council = list(COUNCILS_BY_MODE[mode])
    return council, chairman or (CHEAP_CHAIRMAN if cheap else CHAIRMEN_BY_MODE[mode])


def member_slug(model: str) -> str:
    """File-name-safe form of a member id, for reply files in a run directory."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model)


def slug_collision(members: list[str]) -> str:
    """Error text naming two different ids that share one reply file, or "" when none do."""
    seen: dict[str, str] = {}
    for member in members:
        slug = member_slug(member)
        first = seen.setdefault(slug, member)
        if first != member:
            return (
                f"member ids '{first}' and '{member}' share the reply file '{slug}.md'; rename one"
            )
    return ""


def members_error(members: list[str]) -> str:
    """Error text for an empty council or colliding reply files, else ""."""
    if not members:
        return "the council is empty: --models named no model ids"
    return slug_collision(members)


def min_responses_error(value: int) -> str:
    """Error text when --min-responses is below 1, else "". Zero survivors cannot be ranked."""
    return "" if value >= 1 else f"--min-responses must be at least 1, got {value}"


def stage1_prompt(question: str) -> str:
    return COUNCILLOR_PROMPT + "\n\n" + question


def labels_for(count: int) -> list[str]:
    return [f"Response {chr(65 + i)}" for i in range(count)]


def ranker_prompt(question: str, survivors: list[str], responses: dict[str, str]) -> str:
    labels = labels_for(len(survivors))
    block = "\n\n".join(f"{lbl}:\n{responses[survivors[i]]}" for i, lbl in enumerate(labels))
    return safe_substitute(RANKER_PROMPT, {"{question}": question, "{responses}": block})


def chairman_prompt(
    mode: str,
    question: str,
    survivors: list[str],
    responses: dict[str, str],
    rankings_raw: dict[str, str],
) -> str:
    stage1 = "\n\n".join(f"Model: {m}\nResponse: {responses[m]}" for m in survivors)
    stage2 = "\n\n".join(f"Model: {m}\nRanking: {rankings_raw[m]}" for m in rankings_raw)
    return safe_substitute(
        chairman_template(mode), {"{question}": question, "{stage1}": stage1, "{stage2}": stage2}
    )


_RANKING_HEADER = re.compile(
    r"(?:#+\s*)?\*{0,2}FINAL\s+RANKING:?\*{0,2}\s*\n(.*)", re.DOTALL | re.IGNORECASE
)
_RANKING_ENTRY = re.compile(r"\d+[.)]\s*\*{0,2}(Response\s+[A-Z])\*{0,2}", re.IGNORECASE)


def parse_ranking(text: str, labels: list[str]) -> list[str] | None:
    """Parse the FINAL RANKING block from a ranker's response.

    Block terminator: end of text. Lines after the marker that do not match
    the ranking pattern (blank lines, trailing prose, markdown bullets) are
    skipped; they do not end the block. Tolerated header variants: plain
    `FINAL RANKING:`, bolded `**FINAL RANKING:**`, markdown heading
    `## FINAL RANKING:`. Tolerated entry variants: `1. Response A`,
    `1. **Response A**`, `1) Response A`. Returns None unless every label is
    accounted for exactly once.
    """
    match = _RANKING_HEADER.search(text)
    if not match:
        return None
    out: list[str] = []
    for line in match.group(1).splitlines():
        entry = _RANKING_ENTRY.match(line.strip())
        if not entry:
            continue
        label = entry.group(1).title()
        if label in labels and label not in out:
            out.append(label)
    return out if len(out) == len(labels) else None


def borda(rankings: dict[str, list[str]], labels: list[str]) -> list[tuple[str, float]]:
    """Average rank position per label, best (lowest) first."""
    scores: dict[str, list[int]] = {label: [] for label in labels}
    for order in rankings.values():
        for pos, label in enumerate(order, 1):
            scores[label].append(pos)
    avg = [(label, sum(s) / len(s) if s else 99) for label, s in scores.items()]
    avg.sort(key=lambda x: x[1])
    return avg


def render_artifact(run: dict) -> str:
    """Render the markdown artifact for one council run.

    ``run`` holds mode, chairman, council, errors, question, synthesis,
    survivors, responses, aggregate, label_map, and rankings_raw.
    """
    survivors = run["survivors"]
    labels = labels_for(len(survivors))
    md = [f"# LLM Council: {run['mode']} mode\n"]
    md.append(f"**Generated:** {dt.datetime.now().isoformat(timespec='seconds')}\n")
    md.append(f"**Chairman:** `{run['chairman']}`\n")
    md.append(f"**Council:** {', '.join(f'`{m}`' for m in run['council'])}\n")
    if run["errors"]:
        md.append(
            "**Errors:** " + "; ".join(f"`{m}`: {e}" for m, e in run["errors"].items()) + "\n"
        )
    md.append(f"\n## Question\n\n{run['question']}\n")
    md.append("\n## Chairman Synthesis\n\n" + run["synthesis"] + "\n")
    if run["aggregate"]:
        md.append("\n## Borda Ranking (lower = better)\n")
        md.extend(
            f"- {round(score, 2)}: `{run['label_map'][lbl]}`" for lbl, score in run["aggregate"]
        )
        md.append("")
    md.append("\n## Stage 1: Councillor Responses\n")
    md.extend(f"### {labels[i]}: `{m}`\n\n{run['responses'][m]}\n" for i, m in enumerate(survivors))
    md.append("\n## Stage 2: Peer Rankings\n")
    md.extend(f"### Ranker `{m}`\n\n{raw}\n" for m, raw in run["rankings_raw"].items())
    return "\n".join(md)
