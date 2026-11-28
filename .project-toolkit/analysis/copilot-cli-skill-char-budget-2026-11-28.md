# Copilot CLI skill listing budget: about 15,000 characters

Date: 2026-11-28. Tree: `main` at f8398e1b2d (2026-11-28).
Related: #7779 (description diet), #7831 (budget gate fix), #7801 (routing under a listing cap).

## Finding

Copilot CLI shows a skill's description to the model only while the skill list fits a character budget.
The budget is the environment variable `SKILL_CHAR_BUDGET`.
On the owner's machine the budget in effect is about 15,000 characters.
Past the budget, a skill is listed by name only, with no description.

This repo ships more skills than that budget can describe.
At f8398e1b2d (2026-11-28), `src/copilot-cli/skills` needs 42,453 listing characters for 103 skills.
At that budget, a model predicts that only 36 of the 103 keep a description (f8398e1b2d, 2026-11-28).
The model fills the catalog in name order. Copilot's fill order is not determined (receipt B), so the count and the named omissions are INFERRED, not observed.
In that model, skills such as `review`, `ship`, `test`, and the `pr-*` skills fall past it.

The repo gate does not measure this limit.
`scripts/skill_description_budget.json` caps description characters only, at 31,400 for the Copilot tree.
That cap is about twice the budget Copilot applies, and it leaves out the 93 characters of markup per entry.

## What this finding does not say

- It does not say which default Copilot ships. Two upstream sources disagree: 15,000 and 30,000.
- It does not say how often the model picks a name-only skill. That is unmeasured. #7801 tracks the Claude Code side.
- It does not choose a fix. The owner decides between a larger budget, fewer Copilot skills, or a new gate anchor.

## Evidence

| Claim | State | Source |
|---|---|---|
| The budget is named `SKILL_CHAR_BUDGET` | VERIFIED | Upstream sources 1 and 2; strings in the runtime binary (receipt A) |
| Past the budget, skills are listed by name only | VERIFIED | Upstream sources 2 and 3; the line format in every session log (receipt B) |
| The budget in effect here is 14,915 to 15,063 characters | VERIFIED lower bound, INFERRED upper bound | Receipt B |
| The published default is 15,000 | Disputed | Source 1 says 15,000; source 2 says 30,000 |
| 36 of 103 Copilot skills keep a description | INFERRED at f8398e1b2d (2026-11-28): a model that assumes a 15,000 budget and name-order fill | Receipt C |
| No override is set on this machine | VERIFIED for the files searched; NOT RUN for process environments of past sessions | Receipt E |

### Upstream sources

Fetched on 2026-11-28 through the GitHub API. Quotes are exact.

1. microsoft/vscode#336335, closed, opened 2026-09-15: "pass the effective budget to the Copilot SDK as `SKILL_CHAR_BUDGET`, preserving the runtime default of 15,000 characters".
2. github/copilot-cli#5488, open, opened 2026-11-17: "exceeds `SKILL_CHAR_BUDGET` (30,000 characters by default)". The same issue says it reproduced on `@github/copilot-sdk` with a runtime default of 30,000.
3. github/copilot-cli#2416, maintainer comment on 2026-04-17: "When it hits the token limit for name+description, it will switch to appending the remaining names (not including description)."
4. Copilot CLI changelog, version 1.0.32 (2026-04-17): "Skills that exceed the token limit are still discoverable and invocable by name".
5. The Agent Skills specification (agentskills.io/specification, read 2026-11-28) sets no limit on the whole list. It caps one `description` at 1,024 characters.

Copilot CLI is closed source. The `github/copilot-cli` repository holds a README, a changelog, an install script, and a license. No source code was available to read.

### How the budget behaves (receipt B)

The probe read every local Copilot session log on 2026-11-28.

- 9,390 sessions hold an `<available_skills>` block (2026-11-28). Copilot versions run from 1.0.32 to 1.0.116.
- The full entries in a session total 1,209 to 14,915 characters (2026-11-28). No session exceeds 15,000.
- 9,386 of the 9,390 sessions list at least one skill by name only (2026-11-28).
- A full entry costs 93 characters plus the name plus the description, when its location is `project`.
- If the default were 30,000, sessions that dropped about 200 skills would carry up to 30,000 characters. None does.

The upper bound comes from three sessions in this repo, before #7779 merged.
Each showed 24 full entries, `adr-generator` through `benchmark-models`, totaling 14,392 characters.
The next skill, `build`, had a 672-character entry at `d31aa71e60^`. Adding it makes 15,064, and it was dropped.
This bound is INFERRED. It rests on four assumptions:

- Those sessions ran in this repo. The probe picks them by their first and last skill names, not by the working directory or session date recorded in the log.
- They ran on a checkout with the `d31aa71e60^` text for `build`.
- Copilot tested `build` next, in name order, before it stopped.
- Copilot counts the entry text the probe measures, with no separator. If it counts one newline per entry, the same sessions give 14,416 plus 673, and the upper bound moves from 15,063 to 15,088.

Two points stay open:

- Order. In 833 of the 2,160 sessions that showed only project skills, the full entries were sorted by name (2026-11-28). The rest were not. The fill order is not determined.
- Skip rule. `business-strategy` (603 characters) would have fit after 14,392 and was still dropped. The probe cannot tell whether Copilot stops at the first entry that does not fit, or counts separators it does not see.

### What fits in this repo (receipt C)

Each count below assumes a full entry costs 93 plus the name plus the description, filled in name order.

| Tree at f8398e1b2d (2026-11-28) | Skills | Description chars | Listing chars | Full at 15,000 | Full at 30,000 |
|---|---|---|---|---|---|
| `src/copilot-cli/skills` | 103 | 31,398 | 42,453 | 36, then `github-url-intercept` drops | 72, then `review` drops |
| `.claude/skills` | 121 | 37,136 | 50,344 | 34, then `context-hub-setup` drops | 71, then `planner` drops |

To fit all 103 Copilot skills in 15,000 characters, the mean description must be about 38 characters.
Trimming descriptions alone cannot reach that and keep the trigger phrases.

The repo gate at f8398e1b2d (2026-11-28):

```text
[OK] .claude/skills: 121 skill(s), 37136 chars (~9284 est. tokens), budget 37200 chars (~9300 est. tokens)
[OK] src/copilot-cli/skills: 103 skill(s), 31398 chars (~7850 est. tokens), budget 31400 chars (~7850 est. tokens)
```

Command: `uv run --frozen python scripts/skill_description_budget.py --budget-file scripts/skill_description_budget.json`.
The Copilot tree has 2 characters of headroom (f8398e1b2d, 2026-11-28).

## Options for the owner

None is chosen here.

| Option | What a Copilot user gets | Cost |
|---|---|---|
| Set `SKILL_CHAR_BUDGET` to about 43,000 where this repo launches Copilot | Every skill keeps a description | About 27,500 more prompt characters in every Copilot session, about 6,900 tokens at 4 characters per token |
| Ship fewer skills to the Copilot tree | The shipped skills keep descriptions | Users lose the skills that are cut |
| Re-anchor the gate on listing characters at 15,000 | The gate measures what Copilot shows | Needs a cut list first; the tree is at 42,453 (f8398e1b2d, 2026-11-28) |
| Keep the gate as is | No change | About 67 Copilot skills stay name-only in the name-order model (f8398e1b2d, 2026-11-28) |

## Noticed

The `_comment` in `scripts/skill_description_budget.json` says the cap is "Not a measured limit of any model host".
That stays true of the 31,400 number.
A host limit now exists for Copilot, and the comment does not mention it.
No change made here; the owner decides whether the gate should cite it.

## Reproduce

### Receipt A, B, C, D: the probe

Read-only. It prints counts, sizes, short hashes, and skill names from this repo.
It prints no prompt or response text.

Prerequisites. Save the code block below as `probe.py` in the repo root.
Receipts A and B need the owner's setup: a Copilot CLI launcher at `~/.local/bin/copilot` and session logs under `~/.copilot/session-state/`.
Without the launcher, receipt A raises `FileNotFoundError`. With no matching session logs, receipt B raises `ValueError`. Either error stops the script before receipts C and D.
Receipt C needs only this checkout, and receipt D needs network access to the GitHub API.
Run it from the repo root:

```bash
uv run --frozen python probe.py --fetch
```

<details>
<summary>probe.py</summary>

```python
"""Collect receipts for the Copilot CLI skill listing budget note.

Read-only. Prints counts, sizes, hashes, and skill names from this repo only.
Run from the repo root: uv run --frozen python <this file> [--fetch]
"""

import collections
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

import yaml

HOME = os.path.expanduser("~")
OVERHEAD = 93  # XML chars per full entry with <location>project</location>


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def binaries():
    print("## A. Binaries")
    paths = [f"{HOME}/.local/bin/copilot"] + sorted(
        glob.glob(f"{HOME}/.copilot/pkg/linux-x64/*/prebuilds/linux-x64/runtime.node")
    )
    needles = [
        b"SKILL_CHAR_BUDGET",
        b"skillCharBudget",
        b"skills_get_skill_char_budget",
        b"Additional skills available (invoke by name)",
    ]
    for p in paths:
        real = os.path.realpath(p)
        data = open(real, "rb").read()
        counts = {n.decode(): data.count(n) for n in needles}
        shown = p.replace(HOME, "~", 1)
        print(f"{shown} size={len(data)} sha256={hashlib.sha256(data).hexdigest()[:16]} {counts}")
    print(sh(f"{HOME}/.local/bin/copilot", "--version").splitlines()[0])


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def first_block(path):
    start, block = {}, None
    with open(path, errors="replace") as f:
        for line in f:
            if not start and '"session.start"' in line:
                try:
                    start = json.loads(line).get("data", {}) or {}
                except ValueError:
                    pass
            if block is None and "available_skills" in line:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                for t in strings(ev):
                    m = re.search(r"<available_skills>(.*?)</available_skills>", t, re.S)
                    if m:
                        block = m.group(1)
                        break
            if block is not None and start:
                break
    return start, block


def sessions():
    print("\n## B. Local Copilot sessions (~/.copilot/session-state/*/events.jsonl)")
    files = [
        p for p in glob.glob(f"{HOME}/.copilot/session-state/*/events.jsonl") if os.path.isfile(p)
    ]
    rows = []
    for p in files:
        start, block = first_block(p)
        if block is None:
            continue
        ents = re.findall(r"<skill>.*?</skill>", block, re.S)
        names = [re.search(r"<name>(.*?)</name>", e, re.S).group(1) for e in ents]
        locs = collections.Counter(
            (re.search(r"<location>(.*?)</location>", e, re.S) or [None, "?"])[1] for e in ents
        )
        extra = re.search(r"Additional skills available \(invoke by name\):\s*(.*)", block)
        dropped = [x.strip() for x in extra.group(1).split(",")] if extra else []
        rows.append(
            {
                "ver": start.get("copilotVersion"),
                "producer": start.get("producer"),
                "full": len(ents),
                "chars": sum(len(e) for e in ents),
                "chars_nl": sum(len(e) + 1 for e in ents),
                "dropped": len(dropped),
                "project_only": set(locs) == {"project"},
                "names": names,
                "dropped_names": dropped,
            }
        )
    print(f"event files scanned={len(files)} with <available_skills>={len(rows)}")
    vers = [r["ver"] for r in rows if r["ver"] and r["ver"] != "0.0.0"]
    key = lambda s: [int(x) for x in re.findall(r"\d+", s)]  # noqa: E731
    print(f"with copilotVersion={len(vers)}; range {min(vers, key=key)} to {max(vers, key=key)}")
    print("producers:", dict(collections.Counter(r["producer"] for r in rows)))
    print("full-entry chars min/max:", min(r["chars"] for r in rows), max(r["chars"] for r in rows))
    print("full-entry chars incl. one newline each, max:", max(r["chars_nl"] for r in rows))
    print("sessions over 15000 chars:", sum(r["chars"] > 15000 for r in rows))
    print("sessions with no dropped skill:", sum(r["dropped"] == 0 for r in rows))
    print(
        "full-entry count histogram:", sorted(collections.Counter(r["full"] for r in rows).items())
    )
    po = [r for r in rows if r["project_only"]]
    print(
        f"project-only sessions={len(po)}; full set sorted by name="
        f"{sum(r['names'] == sorted(r['names']) for r in po)}"
    )
    repo = [
        r
        for r in po
        if r["names"] and r["names"][-1] == "benchmark-models" and r["names"][0] == "adr-generator"
    ]
    if repo:
        print(
            f"ai-agents sessions, adr-generator..benchmark-models={len(repo)}: "
            f"full counts={sorted(set(r['full'] for r in repo))} "
            f"chars min/max={min(r['chars'] for r in repo)}/{max(r['chars'] for r in repo)} "
            f"build first dropped={sum(r['dropped_names'][:1] == ['build'] for r in repo)}"
        )
        r = min(repo, key=lambda x: x["chars"])
        print(
            f"  smallest: full={r['full']} chars={r['chars']} next dropped={r['dropped_names'][:2]}"
        )
    return repo


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def repo_fit():
    print("\n## C. Repo fit (entry = 93 + name + description)")
    head = sh("git", "rev-parse", "--short=10", "HEAD").strip()
    for root in (".claude/skills", "src/copilot-cli/skills"):
        sk = []
        for p in sorted(glob.glob(f"{root}/*/SKILL.md")):
            d = frontmatter(open(p, encoding="utf-8").read())
            sk.append(
                (
                    str(d.get("name") or os.path.basename(os.path.dirname(p))),
                    str(d.get("description") or "").strip(),
                )
            )
        sk.sort()
        desc = sum(len(d) for _, d in sk)
        listing = sum(OVERHEAD + len(n) + len(d) for n, d in sk)
        out = []
        for budget in (15000, 30000):
            cum = n = 0
            for name, d in sk:
                e = OVERHEAD + len(name) + len(d)
                if cum + e > budget:
                    break
                cum += e
                n += 1
            out.append(f"@{budget}: {n} full, first name-only={sk[n][0]}")
        print(
            f"{root} at {head}: skills={len(sk)} desc_chars={desc} listing_chars={listing} | "
            + " | ".join(out)
        )
    print("pre-#7779 entries (d31aa71e60^):")
    for name in ("benchmark-models", "build", "business-strategy"):
        d = frontmatter(sh("git", "show", f"d31aa71e60^:src/claude/skills/{name}/SKILL.md"))
        desc = str(d.get("description") or "").strip()
        print(f"  {name}: entry={OVERHEAD + len(name) + len(desc)}")


SOURCES = [
    ("https://api.github.com/repos/microsoft/vscode/issues/336335", r"[^\n]*15,000[^\n]*"),
    ("https://api.github.com/repos/github/copilot-cli/issues/5488", r"[^\n]*30,000[^\n]*"),
    (
        "https://api.github.com/repos/github/copilot-cli/issues/2416/comments?per_page=100",
        r"[^\n\"]*hits the token limit[^\n\"]*",
    ),
    (
        "https://raw.githubusercontent.com/github/copilot-cli/main/changelog.md",
        r"[^\n]*exceed the token limit[^\n]*",
    ),
]


def fetch():
    print("\n## D. Upstream sources")
    hdr = {"User-Agent": "generic-client", "Accept": "application/vnd.github+json"}
    for url, pat in SOURCES:
        try:
            body = (
                urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=25)
                .read()
                .decode()
            )
        except OSError as exc:
            print(f"{url}: FAILED {exc}")
            continue
        if url.startswith("https://api.github.com") and not url.endswith("per_page=100"):
            d = json.loads(body)
            print(
                f"{url}: state={d['state']} created={d['created_at']} author={d['user']['login']}"
            )
            body = d.get("body") or ""
        elif url.endswith("per_page=100"):
            body = "\n".join(
                f"{c['user']['login']} {c['created_at']}: {c['body']}" for c in json.loads(body)
            )
        hits = re.findall(pat, body)
        for h in hits[:2]:
            print("   ", h.strip()[:300])
        if not hits:
            print("    no match")


if __name__ == "__main__":
    binaries()
    sessions()
    repo_fit()
    if "--fetch" in sys.argv:
        fetch()
```

</details>

Raw output, run at 2026-11-28T04:56:57Z on checkout f8398e1b2d:

```text
## A. Binaries
~/.local/bin/copilot size=233588888 sha256=ad56928aff9b9f7f {'SKILL_CHAR_BUDGET': 0, 'skillCharBudget': 0, 'skills_get_skill_char_budget': 0, 'Additional skills available (invoke by name)': 0}
~/.copilot/pkg/linux-x64/1.0.113/prebuilds/linux-x64/runtime.node size=172110432 sha256=8f6fc59b19e4e837 {'SKILL_CHAR_BUDGET': 1, 'skillCharBudget': 2, 'skills_get_skill_char_budget': 1, 'Additional skills available (invoke by name)': 1}
~/.copilot/pkg/linux-x64/1.0.114/prebuilds/linux-x64/runtime.node size=172286304 sha256=f5be2e88fcfa45ee {'SKILL_CHAR_BUDGET': 1, 'skillCharBudget': 2, 'skills_get_skill_char_budget': 1, 'Additional skills available (invoke by name)': 1}
~/.copilot/pkg/linux-x64/1.0.115/prebuilds/linux-x64/runtime.node size=223106272 sha256=990ea7ca958f8c9f {'SKILL_CHAR_BUDGET': 1, 'skillCharBudget': 3, 'skills_get_skill_char_budget': 1, 'Additional skills available (invoke by name)': 1}
GitHub Copilot CLI 1.0.116.

## B. Local Copilot sessions (~/.copilot/session-state/*/events.jsonl)
event files scanned=11163 with <available_skills>=9390
with copilotVersion=9389; range 1.0.32 to 1.0.116
producers: {'copilot-agent': 9390}
full-entry chars min/max: 1209 14915
full-entry chars incl. one newline each, max: 14943
sessions over 15000 chars: 0
sessions with no dropped skill: 4
full-entry count histogram: [(3, 4), (14, 2), (22, 6332), (23, 725), (24, 2046), (25, 54), (26, 12), (29, 1), (30, 68), (31, 1), (33, 28), (34, 42), (40, 9), (41, 51), (42, 15)]
project-only sessions=2160; full set sorted by name=833
ai-agents sessions, adr-generator..benchmark-models=3: full counts=[24] chars min/max=14392/14392 build first dropped=3
  smallest: full=24 chars=14392 next dropped=['build', 'business-strategy']

## C. Repo fit (entry = 93 + name + description)
.claude/skills at f8398e1b2d: skills=121 desc_chars=37136 listing_chars=50344 | @15000: 34 full, first name-only=context-hub-setup | @30000: 71 full, first name-only=planner
src/copilot-cli/skills at f8398e1b2d: skills=103 desc_chars=31398 listing_chars=42453 | @15000: 36 full, first name-only=github-url-intercept | @30000: 72 full, first name-only=review
pre-#7779 entries (d31aa71e60^):
  benchmark-models: entry=586
  build: entry=672
  business-strategy: entry=603

## D. Upstream sources
https://api.github.com/repos/microsoft/vscode/issues/336335: state=closed created=2026-09-15T21:31:52Z author=roblourens
    - pass the effective budget to the Copilot SDK as `SKILL_CHAR_BUDGET`, preserving the runtime default of 15,000 characters
https://api.github.com/repos/github/copilot-cli/issues/5488: state=open created=2026-11-17T18:56:26Z author=smw-ms
    When a session has enough active skills that the `<available_skills>` catalog exceeds `SKILL_CHAR_BUDGET` (30,000 characters by default), the Copilot runtime stops emitting full [...]
    - **Reproduced on `@github/copilot-sdk` (runtime `SKILL_CHAR_BUDGET` default 30,000):**
    stephentoub 2026-04-17T16:38:43Z: This has been improved for the next CLI release. When it hits the token limit for name+description, it will switch to appending the remaining names (not including description).
    - Skills that exceed the token limit are still discoverable and invocable by name
```

Notes on receipt A. The 1.0.116 launcher at `~/.local/bin/copilot` holds none of the strings in plain text.
The unpacked runtimes for 1.0.113 through 1.0.115 hold all four.
Whether 1.0.116 packs its runtime is not checked.

### Receipt E: override search

Command, run on 2026-11-28:

```bash
grep -l -E 'SKILL_CHAR_BUDGET|skillCharBudget' ~/.zshrc ~/.zshenv ~/.zprofile ~/.profile \
  ~/.bashrc ~/.bash_profile /etc/environment ~/.copilot/settings.json ~/.copilot/config.json
```

Result: 0 files matched, of 7 that exist.
The environment of each past session's process was not recorded, so a launcher could still have set it.
The session logs do not name the launcher beyond `producer: copilot-agent`.
