# Model, Thinking Level, and Step Counter Experiments (`flash_10`)

## Summary

We ran two follow-ups to the [step limit and compaction experiments](baseline_ablation_flash10.md): a comparison of two Gemini models at different thinking levels, and a per-turn step counter. All runs use `flash_10` with upstream budgets (100 steps, 28K compaction) unless noted.

- **We reproduced a teammate's runs of vanilla upstream.** Upstream's default thinking levels on our setup landed within 2 pairs of all four of her scores.
- **The paper's "`solo` beats `coop`" holds for the older model, not the newer one.** `gemini-3-flash-preview` does as well or better alone at every thinking level, and its `coop` runs had 3 to 4 merge conflicts each. `gemini-3.8-flash` had 0 to 1 merge conflicts per run, and `coop` matched or beat `solo`.
- **The thinking level decides whether `gemini-3.8-flash` finishes within 100 steps.** At `low` it passed 6/10 `solo` and 7/10 `coop --git`. At `high` it passed 0 to 1 and 3/10, because agents ran out of steps before pushing.
- **Showing the step count on every turn fixes the 100-step budget.** With "Step n of 100: k left" after each turn, `gemini-3.8-flash` at `high` went from 0 to 1 to **7/10** `solo` and from 3 to **8/10** `coop --git`, at the same cost. That matches 250 steps with 64K compaction at under half the cost.
- **`team` (a lead plus a member) did worse than two equal peers:** 5/10 vs. 8/10 for `coop` and `coop --git` with the same model and budgets (250 steps, 28K).

## Terms

- **Models:** `gemini-3.8-flash` is the model our proposal uses. `gemini-3-flash-preview` is an earlier Gemini 3 Flash, upstream CooperBench's default model.
- **Thinking level:** how much the model reasons before answering (`minimal`, `low`, `high`). Upstream sets none, and the client library then picks `minimal` for `gemini-3-flash-preview` and `low` for `gemini-3.8-flash`; our reference setup uses `high`. `gemini-3.8-flash` does not support `minimal`.
- **Step counter:** a line added after every turn: "Step n of N: k left. When no steps are left you are stopped, and only work you have pushed and submitted is graded." Without it, agents cannot tell how many steps they have used, because compaction removes the history they could count from.
- Settings, step limit, compaction, and "passed" are defined in [runs.md](runs.md).

## Model and Thinking Level

A teammate ran vanilla upstream with both models and got different results from ours. These runs reproduce hers and separate the effect of the model from the thinking level (100 steps, 28K compaction, 3 pairs at a time like hers):

| Model, thinking | `solo` | Teammate `solo` | `coop --git` | Teammate `coop --git` | Merge conflicts |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `gemini-3-flash-preview`, minimal | 7/10 | 7/10 | 4/10 | 3/10 | 4 (hers: 4) |
| `gemini-3-flash-preview`, low | 5/10 | | 5/10 | | 4 |
| `gemini-3-flash-preview`, high | 5/10 | | 4/10 | | 3 |
| `gemini-3.8-flash`, low | 6/10 | 4/10 | 7/10 | 7/10 | 1 (hers: 0) |
| `gemini-3.8-flash`, high | 1/10, 0/10 | | 3/10 | | 0 |

- **Reproduction:** all four comparisons are within 2 pairs, a normal amount of variation on 10 pairs. We kept thought summaries on and she had them off, which made no visible difference.
- **`gemini-3-flash-preview`:** more thinking did not help. At `high` it reasoned about 4,500 tokens per call (none at `minimal` or `low`), took 117 minutes instead of 12, and cost about 9 times as much, for 5/10 instead of 7/10.
- **`gemini-3.8-flash`, `low` vs. `high` (`solo`):** at `low`, 4 of 10 agents hit the step limit and agents compacted 1.7 times each; at `high`, 9 to 10 of 10 hit the limit and compacted 8 to 9 times each.
- **Merge conflicts depend on the model:** `gemini-3-flash-preview` agents produced conflicting patches on 3 to 4 of 10 pairs in every `coop` run; `gemini-3.8-flash` agents on 0 to 1.
- **Caveat:** at `minimal` and `low`, both models answer fast enough to hit the API rate limit even with 6 agents (60 to 105 retries per `coop` run). A slowed agent can make its partner give up waiting, so these `coop` scores are slightly less reliable. See [model_config.md](model_config.md#concurrency) for agents per key by model and thinking level.

## Step Counter

`gemini-3.8-flash` at `high`, 100 steps, 28K compaction:

| Setting | No counter | Limit stated once in the prompt | Step counter | 250 steps, no counter |
| :--- | :---: | :---: | :---: | :---: |
| `solo` | 1/10, 0/10 | 0/10 | **7/10** (**9/10** with 250 steps and 64K) | 2/10 (28K), 7/10 (64K) |
| `coop --git` | 3/10 | | **8/10** | 8/10 |

- **The counter changes when agents publish, not how long they work.** In `solo`, 6 of 10 agents still used all 100 steps, but 9 of 10 pushed work before being stopped (0 to 1 of 10 without the counter). Most agents pushed several times along the way, so their last pushed version was graded. In `coop --git`, 19 of 20 agents pushed work (9 of 20 without it).
- **It also helps at a larger budget:** with 250 steps and 64K compaction, `solo` with the counter passed 9/10 (7/10 without it), every agent pushed work, and none hit the step limit.
- **Cost stayed the same:** `$9.11` (`solo`) and `$12.53` (`coop --git`), similar to the runs without the counter.
- **On harder pairs it is not enough:** on the `core` subset (which includes three pairs where both features change the same function), `solo` with the counter scored 5/10, and all 10 agents used every step. `coop --git` scored 4/10 there, and its only two merge conflicts were on same-function pairs (`dspy_task/8563`, `react_hook_form_task/153`).

## `team` Baseline

With 250 steps and 28K compaction, `team` passed 5/10, against 8/10 for both `coop` and `coop --git`. In 4 of the 5 passes the agents' patches merged cleanly. `typst_task/6554` passed only because the lead had written both features, so after the merge conflict the grader's fallback (test the lead's patch alone) succeeded. Agents sent no direct messages and coordinated through the shared task list. One lead crashed because of a harness bug that we have since fixed ([harness_limits.md](harness_limits.md)).

## Conclusions

1. **Use `gemini-3.8-flash`.** It is our proposal's model and current. The `gemini-3-flash-preview` runs connect our setup to the paper's result.
2. **Make the step counter standard for every setting.** It gives agents information they need, it is cheap, and it applies equally to `solo`, `coop`, and `team`. It is our one prompt change from upstream, and it should be documented as such.
3. **Pick the thinking level and budget from a `solo` saturation run.** The open question is which tasks `gemini-3.8-flash` can solve alone when budget is not the limit. A 500-step run at `low` and `high` on the 50-pair `flash` subset, with 64K compaction and the counter, is in progress. Its result will tell us which `coop` failures are coordination failures.
4. **10 pairs are too few to rank close settings.** Differences of 1 to 2 pairs are within run-to-run variation; the 50-pair runs address this.
