# Model routing by agent and skill

Lightest sufficient is the cheapest model whose mean recall trails the best model on the same ladder by at most 0.10. A cheaper model is kept unless the measured gap exceeds the margin. `(gap unproven)` marks a verdict the corpus cannot prove: the lower bound of the paired bootstrap CI on the gap (95%, Bonferroni-split across the cheaper models) falls below the negative margin.

| Kind | Subject | Fixtures | claude lightest | claude best | gpt6 lightest | gpt6 best |
|---|---|---|---|---|---|---|
| agent | analyst | analyst | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna | gpt-6-luna |
| agent | architect | architect | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna | gpt-6-luna |
| agent | backlog-generator | backlog-generator | claude-haiku-4-5 (gap unproven) | claude-opus-5-5 | gpt-6-luna | gpt-6-luna |
| agent | critic | critic | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-sol (gap unproven) | gpt-6-astra |
| agent | devops | devops | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna | gpt-6-luna |
| agent | explainer | explainer | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| agent | high-level-advisor | high-level-advisor | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| agent | implementer | implementer | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-astra | gpt-6-astra |
| agent | independent-thinker | independent-thinker | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna | gpt-6-luna |
| agent | issue-feature-review | issue-feature-review | claude-haiku-4-5 (gap unproven) | claude-opus-5-5 | gpt-6-luna (gap unproven) | gpt-6-sol |
| agent | milestone-planner | milestone-planner | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| agent | orchestrator | orchestrator | claude-sonnet-5 | claude-sonnet-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| agent | qa | qa | claude-haiku-4-5 (gap unproven) | claude-sonnet-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| agent | roadmap | roadmap | claude-haiku-4-5 (gap unproven) | claude-sonnet-5 | gpt-6-luna | gpt-6-luna |
| agent | security | security | claude-haiku-4-5 (gap unproven) | claude-opus-5-5 | gpt-6-luna | gpt-6-luna |
| agent | skillbook | skillbook | claude-opus-5-5 | claude-opus-5-5 | gpt-6-astra | gpt-6-astra |
| agent | task-decomposer | task-decomposer | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-luna | gpt-6-luna |
| skill | adr-review | architect | claude-haiku-4-5 | claude-haiku-4-5 | gpt-6-sol (gap unproven) | gpt-6-astra |
| skill | analyze | analyst | undecided | undecided | gpt-6-luna | gpt-6-luna |
| skill | plan | milestone-planner | undecided | undecided | gpt-6-luna | gpt-6-luna |
| skill | review | critic | undecided | undecided | gpt-6-luna | gpt-6-luna |
| skill | security-review | security | claude-opus-5-5 | claude-opus-5-5 | gpt-6-luna (gap unproven) | gpt-6-astra |
| skill | spec | explainer | undecided | undecided | gpt-6-sol (gap unproven) | gpt-6-astra |

## Per-model recall

| Subject | Ladder | Model | Routed recall | Headline recall | Headline baseline | Cost USD | Sufficient |
|---|---|---|---|---|---|---|---|
| analyst | claude | claude-haiku-4-5 | 0.80 | 0.82 | 0.86 | 0.37 | True |
| analyst | claude | claude-sonnet-5 | 0.63 | 0.63 | 0.74 | 0.87 | False |
| analyst | claude | claude-opus-5-5 | 0.76 | 0.79 | 0.82 | 1.40 | True |
| analyst | gpt6 | gpt-6-luna | 0.73 | 0.73 | 0.81 | 0.03 | True |
| analyst | gpt6 | gpt-6-sol | 0.68 | 0.68 | 0.76 | 0.63 | True |
| analyst | gpt6 | gpt-6-astra | 0.62 | 0.62 | 0.78 | 3.40 | False |
| architect | claude | claude-haiku-4-5 | 0.69 | 0.69 | 0.69 | 0.21 | True |
| architect | claude | claude-sonnet-5 | 0.65 | 0.65 | 0.60 | 0.44 | True |
| architect | claude | claude-opus-5-5 | 0.67 | 0.60 | 0.60 | 0.85 | True |
| architect | gpt6 | gpt-6-luna | 0.77 | 0.77 | 0.56 | 0.02 | True |
| architect | gpt6 | gpt-6-sol | 0.65 | 0.65 | 0.56 | 0.41 | False |
| architect | gpt6 | gpt-6-astra | 0.62 | 0.62 | 0.71 | 2.13 | False |
| backlog-generator | claude | claude-haiku-4-5 | 0.75 | 0.75 | 0.75 | 0.06 | True |
| backlog-generator | claude | claude-sonnet-5 | 0.81 | 0.81 | 0.73 | 0.16 | True |
| backlog-generator | claude | claude-opus-5-5 | 0.81 | 0.81 | 0.90 | 0.27 | True |
| backlog-generator | gpt6 | gpt-6-luna | 0.88 | 0.90 | 0.90 | 0.01 | True |
| backlog-generator | gpt6 | gpt-6-sol | 0.85 | 0.85 | 0.77 | 0.11 | True |
| backlog-generator | gpt6 | gpt-6-astra | 0.81 | 0.79 | 0.86 | 0.62 | True |
| critic | claude | claude-haiku-4-5 | 0.88 | 0.88 | 0.69 | 0.15 | True |
| critic | claude | claude-sonnet-5 | 0.79 | 0.79 | 0.75 | 0.30 | True |
| critic | claude | claude-opus-5-5 | 0.81 | 0.81 | 0.81 | 0.60 | True |
| critic | gpt6 | gpt-6-luna | 0.77 | 0.77 | 0.79 | 0.01 | False |
| critic | gpt6 | gpt-6-sol | 0.85 | 0.85 | 0.81 | 0.28 | True |
| critic | gpt6 | gpt-6-astra | 0.92 | 0.92 | 0.85 | 1.49 | True |
| devops | claude | claude-haiku-4-5 | 0.79 | 0.80 | 1.00 | 0.08 | True |
| devops | claude | claude-sonnet-5 | 0.67 | 0.67 | 0.46 | 0.18 | False |
| devops | claude | claude-opus-5-5 | 0.65 | 0.70 | 0.80 | 0.32 | False |
| devops | gpt6 | gpt-6-luna | 0.71 | 0.71 | 0.71 | 0.01 | True |
| devops | gpt6 | gpt-6-sol | 0.65 | 0.65 | 0.65 | 0.14 | True |
| devops | gpt6 | gpt-6-astra | 0.60 | 0.60 | 0.71 | 0.76 | False |
| explainer | claude | claude-haiku-4-5 | 0.88 | 0.88 | 0.81 | 0.07 | True |
| explainer | claude | claude-sonnet-5 | 0.79 | 0.79 | 0.54 | 0.19 | True |
| explainer | claude | claude-opus-5-5 | 0.56 | 0.56 | 0.60 | 0.28 | False |
| explainer | gpt6 | gpt-6-luna | 0.56 | 0.56 | 0.62 | 0.01 | True |
| explainer | gpt6 | gpt-6-sol | 0.60 | 0.58 | 0.67 | 0.12 | True |
| explainer | gpt6 | gpt-6-astra | 0.65 | 0.60 | 0.60 | 0.66 | True |
| high-level-advisor | claude | claude-haiku-4-5 | 0.69 | 0.69 | 0.56 | 0.08 | True |
| high-level-advisor | claude | claude-sonnet-5 | 0.54 | 0.54 | 0.73 | 0.17 | False |
| high-level-advisor | claude | claude-opus-5-5 | 0.60 | 0.60 | 0.67 | 0.32 | True |
| high-level-advisor | gpt6 | gpt-6-luna | 0.56 | 0.56 | 0.60 | 0.01 | True |
| high-level-advisor | gpt6 | gpt-6-sol | 0.54 | 0.54 | 0.56 | 0.14 | False |
| high-level-advisor | gpt6 | gpt-6-astra | 0.65 | 0.60 | 0.70 | 0.80 | True |
| implementer | claude | claude-haiku-4-5 | 0.71 | 0.67 | 0.58 | 0.28 | True |
| implementer | claude | claude-sonnet-5 | 0.67 | 0.67 | 0.69 | 0.57 | True |
| implementer | claude | claude-opus-5-5 | 0.65 | 0.65 | 0.58 | 1.15 | True |
| implementer | gpt6 | gpt-6-luna | 0.46 | 0.46 | 0.35 | 0.03 | False |
| implementer | gpt6 | gpt-6-sol | 0.46 | 0.46 | 0.46 | 0.55 | False |
| implementer | gpt6 | gpt-6-astra | 0.62 | 0.58 | 0.50 | 2.81 | True |
| independent-thinker | claude | claude-haiku-4-5 | 0.81 | 0.81 | 0.75 | 0.08 | True |
| independent-thinker | claude | claude-sonnet-5 | 0.73 | 0.73 | 0.67 | 0.20 | True |
| independent-thinker | claude | claude-opus-5-5 | 0.73 | 0.83 | 0.75 | 0.32 | True |
| independent-thinker | gpt6 | gpt-6-luna | 0.88 | 0.88 | 0.73 | 0.01 | True |
| independent-thinker | gpt6 | gpt-6-sol | 0.79 | 0.79 | 0.69 | 0.15 | True |
| independent-thinker | gpt6 | gpt-6-astra | 0.77 | 0.90 | 0.90 | 0.82 | False |
| issue-feature-review | claude | claude-haiku-4-5 | 0.69 | 0.69 | 0.81 | 0.07 | True |
| issue-feature-review | claude | claude-sonnet-5 | 0.54 | 0.54 | 0.69 | 0.19 | False |
| issue-feature-review | claude | claude-opus-5-5 | 0.73 | 0.73 | 0.71 | 0.31 | True |
| issue-feature-review | gpt6 | gpt-6-luna | 0.58 | 0.58 | 0.60 | 0.01 | True |
| issue-feature-review | gpt6 | gpt-6-sol | 0.60 | 0.60 | 0.62 | 0.17 | True |
| issue-feature-review | gpt6 | gpt-6-astra | 0.48 | 0.50 | 0.92 | 1.01 | False |
| milestone-planner | claude | claude-haiku-4-5 | 0.88 | 0.86 | 0.86 | 0.16 | True |
| milestone-planner | claude | claude-sonnet-5 | 0.60 | 0.60 | 0.60 | 0.32 | False |
| milestone-planner | claude | claude-opus-5-5 | 0.62 | 0.62 | 0.73 | 0.50 | False |
| milestone-planner | gpt6 | gpt-6-luna | 0.52 | 0.52 | 0.50 | 0.01 | True |
| milestone-planner | gpt6 | gpt-6-sol | 0.58 | 0.58 | 0.56 | 0.12 | True |
| milestone-planner | gpt6 | gpt-6-astra | 0.60 | 0.70 | 0.70 | 0.94 | True |
| orchestrator | claude | claude-haiku-4-5 | 0.65 | 0.71 | 0.64 | 0.20 | False |
| orchestrator | claude | claude-sonnet-5 | 0.75 | 0.75 | 0.69 | 0.41 | True |
| orchestrator | claude | claude-opus-5-5 | 0.71 | 0.71 | 0.79 | 0.82 | True |
| orchestrator | gpt6 | gpt-6-luna | 0.67 | 0.67 | 0.65 | 0.02 | True |
| orchestrator | gpt6 | gpt-6-sol | 0.65 | 0.65 | 0.54 | 0.38 | True |
| orchestrator | gpt6 | gpt-6-astra | 0.67 | 0.67 | 0.67 | 1.97 | True |
| qa | claude | claude-haiku-4-5 | 0.53 | 0.58 | 0.47 | 0.29 | True |
| qa | claude | claude-sonnet-5 | 0.61 | 0.65 | 0.47 | 0.59 | True |
| qa | claude | claude-opus-5-5 | 0.46 | 0.52 | 0.48 | 1.19 | False |
| qa | gpt6 | gpt-6-luna | 0.33 | 0.40 | 0.40 | 0.03 | True |
| qa | gpt6 | gpt-6-sol | 0.35 | 0.40 | 0.37 | 0.56 | True |
| qa | gpt6 | gpt-6-astra | 0.43 | 0.52 | 0.55 | 2.94 | True |
| roadmap | claude | claude-haiku-4-5 | 0.65 | 0.71 | 0.57 | 0.07 | True |
| roadmap | claude | claude-sonnet-5 | 0.71 | 0.71 | 0.58 | 0.16 | True |
| roadmap | claude | claude-opus-5-5 | 0.62 | 0.62 | 0.48 | 0.28 | True |
| roadmap | gpt6 | gpt-6-luna | 0.60 | 0.60 | 0.52 | 0.01 | True |
| roadmap | gpt6 | gpt-6-sol | 0.52 | 0.52 | 0.48 | 0.12 | True |
| roadmap | gpt6 | gpt-6-astra | 0.50 | 0.50 | 0.54 | 0.68 | False |
| security | claude | claude-haiku-4-5 | 0.76 | 0.79 | 0.32 | 0.47 | True |
| security | claude | claude-sonnet-5 | 0.80 | 0.82 | 0.58 | 0.98 | True |
| security | claude | claude-opus-5-5 | 0.82 | 0.94 | 0.56 | 1.87 | True |
| security | gpt6 | gpt-6-luna | 0.54 | 0.57 | 0.62 | 0.04 | True |
| security | gpt6 | gpt-6-sol | 0.50 | 0.50 | 0.64 | 0.91 | True |
| security | gpt6 | gpt-6-astra | 0.49 | 0.46 | 0.62 | 4.69 | True |
| skillbook | claude | claude-haiku-4-5 | 0.69 | 0.69 | 0.62 | 0.08 | False |
| skillbook | claude | claude-sonnet-5 | 0.75 | 0.75 | 0.81 | 0.16 | False |
| skillbook | claude | claude-opus-5-5 | 0.88 | 0.88 | 0.73 | 0.31 | True |
| skillbook | gpt6 | gpt-6-luna | 0.67 | 0.67 | 0.46 | 0.01 | False |
| skillbook | gpt6 | gpt-6-sol | 0.73 | 0.73 | 0.58 | 0.13 | False |
| skillbook | gpt6 | gpt-6-astra | 0.83 | 0.80 | 0.80 | 0.71 | True |
| task-decomposer | claude | claude-haiku-4-5 | 0.88 | 0.88 | 0.88 | 0.09 | True |
| task-decomposer | claude | claude-sonnet-5 | 0.88 | 0.88 | 0.75 | 0.26 | True |
| task-decomposer | claude | claude-opus-5-5 | 0.83 | 1.00 | 0.90 | 0.36 | True |
| task-decomposer | gpt6 | gpt-6-luna | 0.85 | 0.85 | 0.77 | 0.01 | True |
| task-decomposer | gpt6 | gpt-6-sol | 0.75 | 0.75 | 0.81 | 0.16 | False |
| task-decomposer | gpt6 | gpt-6-astra | 0.69 | 0.69 | 0.83 | 0.90 | False |
| adr-review | claude | claude-haiku-4-5 | 0.75 | 0.75 | 0.69 | 0.29 | True |
| adr-review | claude | claude-sonnet-5 | 0.56 | 0.56 | 0.60 | 0.61 | False |
| adr-review | claude | claude-opus-5-5 | 0.67 | 0.67 | 0.67 | 1.18 | True |
| adr-review | gpt6 | gpt-6-luna | 0.54 | 0.54 | 0.52 | 0.03 | False |
| adr-review | gpt6 | gpt-6-sol | 0.62 | 0.62 | 0.56 | 0.57 | True |
| adr-review | gpt6 | gpt-6-astra | 0.69 | 0.69 | 0.67 | 2.95 | True |
| analyze | claude | undecided: expected one skill report for analyze on claude-sonnet-5 under evals/analyst-spike/reports on the current fixtures, found 0: [] | | | | | |
| analyze | gpt6 | gpt-6-luna | 0.85 | 0.85 | 0.83 | 0.05 | True |
| analyze | gpt6 | gpt-6-sol | 0.76 | 0.76 | 0.73 | 1.02 | True |
| analyze | gpt6 | gpt-6-astra | 0.78 | 0.78 | 0.78 | 5.40 | True |
| plan | claude | undecided: expected one skill report for plan on claude-opus-5-5 under evals/milestone-planner-spike/reports on the current fixtures, found 0: [] | | | | | |
| plan | gpt6 | gpt-6-luna | 0.56 | 0.56 | 0.42 | 0.02 | True |
| plan | gpt6 | gpt-6-sol | 0.44 | 0.44 | 0.54 | 0.34 | False |
| plan | gpt6 | gpt-6-astra | 0.50 | 0.50 | 0.60 | 1.98 | True |
| review | claude | undecided: expected one skill report for review on claude-sonnet-5 under evals/critic-spike/reports on the current fixtures, found 0: [] | | | | | |
| review | gpt6 | gpt-6-luna | 0.81 | 0.81 | 0.83 | 0.03 | True |
| review | gpt6 | gpt-6-sol | 0.81 | 0.81 | 0.83 | 0.59 | True |
| review | gpt6 | gpt-6-astra | 0.77 | 0.81 | 0.86 | 3.06 | True |
| security-review | claude | claude-haiku-4-5 | 0.62 | 0.68 | 0.32 | 0.62 | False |
| security-review | claude | claude-sonnet-5 | 0.66 | 0.72 | 0.58 | 1.30 | False |
| security-review | claude | claude-opus-5-5 | 0.78 | 0.82 | 0.55 | 2.49 | True |
| security-review | gpt6 | gpt-6-luna | 0.58 | 0.62 | 0.60 | 0.06 | True |
| security-review | gpt6 | gpt-6-sol | 0.64 | 0.73 | 0.67 | 1.20 | True |
| security-review | gpt6 | gpt-6-astra | 0.65 | 0.75 | 0.69 | 6.22 | True |
| spec | claude | undecided: expected one skill report for spec on claude-opus-5-5 under evals/explainer-spike/reports on the current fixtures, found 0: [] | | | | | |
| spec | gpt6 | gpt-6-luna | 0.52 | 0.52 | 0.60 | 0.01 | False |
| spec | gpt6 | gpt-6-sol | 0.62 | 0.58 | 0.58 | 0.27 | True |
| spec | gpt6 | gpt-6-astra | 0.71 | 0.71 | 0.69 | 1.48 | True |
