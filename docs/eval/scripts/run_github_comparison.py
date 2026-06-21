#!/usr/bin/env python3
"""First comparison table: the code-qualities rubric across multiple vendors
through the GitHub Models transport shipped in PR #2710 (the EVAL_PROVIDER
multi-provider harness). Reproduces the "Reliability" and "Scores" tables in the
doc's first section. Uses the github-models gateway (an OpenAI-compatible endpoint
reachable with a GitHub token), so one transport reaches many vendors.

Prereqs: `pip install openai`, and a token in GITHUB_TOKEN / GH_TOKEN (a
`gh auth token` works). Imports the harness from ../../scripts/eval.
"""
import json
import os
import sys
import time
from pathlib import Path

import evalkit

# Import the #2710 transport from the repo's eval harness.
HARNESS = Path(__file__).resolve().parents[2] / "scripts" / "eval"
sys.path.insert(0, str(HARNESS))
import _providers  # noqa: E402

# github-models model IDs (catalog: https://models.github.ai/catalog/models)
MODELS = [
    "openai/gpt-4o",
    "meta/llama-3.3-70b-instruct",
    "microsoft/phi-4",
    "mistral-ai/mistral-medium-2505",
    "deepseek/deepseek-v3-0324",
]


def main():
    os.environ.setdefault("GITHUB_TOKEN", os.popen("gh auth token").read().strip())
    repo = evalkit.moq_repo()
    files = evalkit.load_files()
    provider = _providers.resolve_provider("github")
    report = {"repo": "rjmurillo/moq.analyzers", "transport": "github-models", "files": {}}
    for rel in files:
        code = open(os.path.join(repo, rel), encoding="utf-8").read()
        report["files"][rel] = {}
        for model in MODELS:
            t = time.monotonic()
            try:
                # github/openai reasoning models need the #2711/#2712 fix; the
                # vendors above are non-reasoning and take max_tokens/temperature.
                text = provider.complete(messages=[{"role": "user", "content": code}],
                                         system=evalkit.RUBRIC, model=model, max_tokens=1500)
                dur = int((time.monotonic() - t) * 1000)
                scores = evalkit.parse_scores(text)
                rec = {"scores": scores, "ms": dur} if scores else {"error": "unparseable", "ms": dur}
            except Exception as exc:  # noqa: BLE001
                rec = {"error": str(exc)[:160], "ms": int((time.monotonic() - t) * 1000)}
            report["files"][rel][model] = rec
            ov = rec.get("scores", {}).get("overall") if "scores" in rec else "ERR"
            print(f"  {rel.split('/')[-1][:32]:32} {model:32} ov={ov} ({rec['ms'] / 1000:.1f}s)", flush=True)
            time.sleep(1.5)  # gentle pacing for github-models rate limits
    out = evalkit.out_dir() / "github_comparison.json"
    json.dump(report, open(out, "w"), indent=2)
    print("\nsaved " + str(out))


if __name__ == "__main__":
    main()
