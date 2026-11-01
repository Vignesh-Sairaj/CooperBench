# Step Limit and Compaction Experiments (`flash_10`)

## Summary

We ran `solo` and `coop` on the 10-pair `flash_10` subset under different step limits and compaction thresholds, to decide which budgets to use for our baselines and coordination experiments.

- With the upstream defaults (100 steps, 28K compaction), most agents are stopped before they push any work. At these budgets, scores mostly measure whether an agent finishes in time, not how well it coordinates.
- With 250 steps, `coop` reaches 8/10 at either 28K or 64K compaction. `solo` needs both 250 steps and 64K compaction to reach 7/10.
- At the same per-agent budget (250 steps, 64K), `solo` (7/10) and `coop --git` (8/10) are statistically indistinguishable on 10 pairs. These runs do **not** show that `coop` beats `solo`.
- **Proposed default for our experiments (team decision pending):** 250 steps and 64K compaction for every setting.

## Terms

- **Settings:** `solo` is one agent implementing both features. `coop` is two agents, one feature each, who can message each other. `coop --git` adds a shared git remote where they can push and pull each other's branches.
- **Step limit:** the maximum number of model responses per agent. The agent is then stopped, and only work it has pushed is graded. Upstream default: 100.
- **Compaction:** once a request reaches this many tokens, the harness replaces older turns with a model-written summary and keeps only the last 2 turns verbatim. Upstream default: 28K.
- **Passed:** both features' hidden tests pass (in `coop`, after merging the two agents' patches).
- **Subset:** `flash_10` is 10 hand-picked feature pairs from 9 repos, used for cheap screening.

Every run uses `gemini-3.8-flash` with `HIGH` thinking and a `$10` per-agent cost cap.

## What We Ran and Why

| Run | Setting | Step limit | Compaction | Question | Passed | Pushed work | Cost |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: | ---: |
| [solo, upstream budgets](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) | `solo` | 100 | 28K | Baseline with upstream defaults | 1/10 | 1/10 agents | `$8.92` |
| [solo, repeat](../results/solo-msa_v2-gemini-3-8-flash-flash_10-r2/summary.md) | `solo` | 100 | 28K | How much does the same setup vary? | 0/10 | 0/10 agents | `$8.99` |
| [solo, limit in prompt](../results/solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt/summary.md) | `solo` | 100 | 28K | Does stating the limit in the task help? | 0/10 | 0/10 agents | `$8.41` |
| [solo, 250 steps](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `solo` | 250 | 28K | Do agents finish with more steps? | 2/10 | 2/10 agents | `$18.75` |
| [solo, 250 steps, 64K](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `solo` | 250 | 64K | Does one agent need more context for two features? | 7/10 | 7/10 agents | `$19.63` |
| [coop --git, upstream budgets](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10/summary.md) | `coop --git` | 100 | 28K | Baseline with upstream defaults | 3/10 | 9/20 agents | `$11.93` |
| [coop --git, 250 steps](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop --git` | 250 | 28K | Do agents finish with more steps? | 8/10 | 16/20 agents | `$19.87` |
| [coop, 250 steps](../results/coop-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop` | 250 | 28K | Does the shared git remote matter? | 8/10 | 18/20 agents | `$23.05` |
| [coop --git, 250 steps, 64K](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `coop --git` | 250 | 64K | `coop` vs. `solo` at the same per-agent budget | 8/10 | 20/20 agents | `$21.68` |

"Pushed work" counts agents that pushed a non-empty patch before stopping. No run had agent errors or merge conflicts. All runs, including later ones, are listed in [runs.md](runs.md).

## Results per Pair

"A only" or "B only" means only one of the two features passed.

| Pair | `solo` 100 | `solo` 100 repeat | `solo` 100, limit in prompt | `solo` 250 | `solo` 250, 64K | `coop --git` 100 | `coop --git` 250 | `coop` 250 | `coop --git` 250, 64K |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `dottxt_ai_outlines/1655` | - | - | - | pass | pass | pass | pass | pass | pass |
| `dspy/8394` | - | - | - | - | - | A only | pass | pass | pass |
| `go_chi/26` | - | - | - | - | pass | A only | pass | pass | pass |
| `huggingface_datasets/6252` | - | - | - | - | pass | B only | pass | pass | pass |
| `openai_tiktoken/0` | - | - | - | - | pass | pass | pass | pass | pass |
| `pallets_click/2800` | - | - | - | - | pass | - | pass | pass | pass |
| `pallets_jinja/1559` | - | - | - | - | - | - | - | - | - |
| `pallets_jinja/1621` | pass | - | - | pass | pass | pass | pass | pass | pass |
| `pillow/290` | - | - | - | - | - | - | - | B only | B only |
| `typst/6554` | - | - | - | - | pass | - | pass | pass | pass |

## Conclusions

1. **Upstream budgets stop agents before they submit.** At 100 steps and 28K compaction, 9 to 10 of 10 `solo` agents and 11 of 20 `coop --git` agents were stopped with nothing pushed. A `solo` agent has to fit two features into one budget, so it is hit hardest.
2. **Telling the agent the step limit did not help (0/10).** The limit was in the task prompt, which the agent sees on every call, but nothing tells it which step it is on, and compaction drops the history it could count from. No agent mentioned the limit in its reasoning. Showing the current step number on every turn is untested.
3. **More steps help `coop` far more than `solo` at 28K.** At 250 steps, `coop --git` reached 8/10 but `solo` only 2/10. The `solo` agents compacted a median of 24 times, losing file context each time. At 64K, the median dropped to 6 and `solo` reached 7/10 at about the same cost.
4. **`solo` and `coop` are tied at the same per-agent budget.** With 250 steps and 64K compaction, `solo` (7/10) and `coop --git` (8/10) disagree on exactly one pair (`dspy/8394`); so does `coop --git` with 28K compaction. With 10 pairs, a paired test needs about 6 disagreeing pairs, all going the same way, to call a difference real. The total budget still differs: each `coop` agent gets 250 steps for one feature, while `solo` gets 250 for two.
5. **Neither the shared git remote nor 64K compaction changed `coop` results at 250 steps.** All three `coop` runs at 250 steps passed the same 8 pairs. At 64K, `coop` agents compacted far less (median 3 per agent) and finished in fewer steps.
6. **Two pairs fail in every setting.** In `pallets_jinja/1559`, agents usually run out of steps without pushing anything. The one exception (`coop --git`, 250 steps, 64K) still failed: one agent submitted its feature, but its partner hit the step limit with a 1-line patch that did not apply, and in that case the grader tests only the first agent's patch against both features. In `pillow/290`, both `coop` agents submitted at 250 steps (28K and 64K), but feature 4 failed 1 of its 8 tests both times.

## Why This Differs from the Paper

The CooperBench paper reports `solo` well ahead of `coop`. Our numbers should not be read as contradicting it, for three reasons:

- **The harness changed after the paper.** Compaction at 28K and grading only pushed work were both added in April 2026, after the paper. Both hurt a two-feature `solo` agent the most.
- **`flash_10` is not a random sample.** It was hand-picked from easy and mid-difficulty pairs, and no `coop` run on it had a merge conflict. The paper's `coop` losses come largely from pairs whose features touch the same code.
- **The samples are small.** Each arm ran once on 10 pairs. The 95% interval for 7/10 is roughly 40% to 89%.

## Next

- `team` with 250 steps, to complete the four settings.
- `solo` with the current step number shown on every turn, to test whether a visible countdown makes agents submit in time.
- Repeat runs, or the 50-pair `flash` subset, before drawing conclusions about `solo` vs. `coop`.
