# Model, Thinking Level, and Step Counter Experiments (`flash_10`)

## Summary

Follow-ups to the [step limit and compaction experiments](baseline_ablation_flash10.md): two Gemini models at different thinking levels, a per-turn step counter, and the `team` setting. All runs use `flash_10` with upstream budgets (100 steps, 28K compaction) unless noted.

- **The fork reproduces unmodified upstream.** With upstream's default thinking levels, runs on the fork and on unmodified upstream code agree within 2 pairs on all four comparisons.
- **The paper's "`solo` beats `coop`" holds for the older model, not the newer one.** `gemini-3-flash-preview` does as well or better alone at every thinking level, and its `coop` runs had 3 to 4 merge conflicts each. `gemini-3.8-flash` had 0 to 1 merge conflicts per run, and `coop` matched or beat `solo`.
- **The thinking level decides whether `gemini-3.8-flash` finishes within 100 steps.** At `low` it passed 6/10 `solo` and 7/10 `coop --git`. At `high` it passed 0 or 1 of 10 `solo` and 3/10 `coop --git`, because agents ran out of steps before pushing.
- **Showing the step count on every turn fixes the 100-step budget.** With "Step n of 100: k left" after each turn, `gemini-3.8-flash` at `high` went from 0 or 1 of 10 to **7/10** `solo`, and from 3/10 to **8/10** `coop --git`, at the same cost. With 250 steps and 64K compaction, the counter took `solo` to **9/10**, the best `solo` result.
- **`team` (a lead plus a member) did worse than two equal peers,** with or without the counter: 5/10 and 4/10, vs. 8/10 for `coop --git` with the same model and budgets.

## Terms

- **Fork vs. upstream code:** "upstream code" is the unmodified CooperBench repository (`63b9d44`). "The fork" is our copy of it, with opt-in flags (such as the step counter) that are off unless a config turns them on.
- **Models:** `gemini-3.8-flash` is the model our proposal uses. `gemini-3-flash-preview` is an earlier Gemini 3 Flash, upstream CooperBench's default model.
- **Thinking level:** how much the model reasons before answering (`minimal`, `low`, `high`). Upstream sets none, and LiteLLM (the library that calls the model) then picks `minimal` for `gemini-3-flash-preview` and `low` for `gemini-3.8-flash`; our reference setup uses `high`. `gemini-3.8-flash` does not support `minimal`.
- **Step counter:** a line added after every turn: "Step n of N: k left. When no steps are left you are stopped, and only work you have pushed and submitted is graded." Without it, agents cannot tell how many steps they have used, because compaction removes the history they could count from.
- Settings, step limit, compaction, and "passed" are defined in [runs.md](runs.md).

## Model and Thinking Level

Runs on unmodified upstream code (`63b9d44`, no agent config, so each model's default thinking level) scored differently from the reference setup (`gemini-3.8-flash` at `high`). The runs below repeat them on the fork and separate the effect of the model from the thinking level. All use 100 steps, 28K compaction, and 3 pairs running in parallel. "Not run" marks combinations that were only run on the fork:

| Model, thinking | `solo` (fork) | `solo` (upstream code) | `coop --git` (fork) | `coop --git` (upstream code) | Merge conflicts in `coop --git` (fork / upstream code) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `gemini-3-flash-preview`, minimal | 7/10 | 7/10 | 4/10 | 3/10 | 4 / 4 |
| `gemini-3-flash-preview`, low | 5/10 | not run | 5/10 | not run | 4 / not run |
| `gemini-3-flash-preview`, high | 5/10 | not run | 4/10 | not run | 3 / not run |
| `gemini-3.8-flash`, low | 6/10 | 4/10 | 7/10 | 7/10 | 1 / 0 |
| `gemini-3.8-flash`, high | 1/10, 0/10 | not run | 3/10 | not run | 0 / not run |

- **Reproduction:** all four comparisons are within 2 pairs, a normal amount of variation on 10 pairs. Thought summaries were on in the fork runs and off in the upstream-code runs, which made no visible difference.
- **`gemini-3-flash-preview`:** more thinking did not help. At `high` it reasoned about 4,500 tokens per call (none at `minimal` or `low`), took 117 minutes instead of 12, and cost about 9 times as much, for 5/10 instead of 7/10.
- **`gemini-3.8-flash`, `low` vs. `high` (`solo`):** at `low`, 4 of 10 agents hit the step limit and agents compacted 1.7 times each; at `high`, 9 to 10 of 10 hit the limit and compacted 8 to 9 times each.
- **Merge conflicts depend on the model:** `gemini-3-flash-preview` agents produced conflicting patches on 3 to 4 of 10 pairs in every `coop` run; `gemini-3.8-flash` agents on 0 to 1.
- **Caveat:** at `minimal` and `low`, both models answer fast enough to hit the API rate limit even with 6 agents (60 to 105 retries per `coop` run). A slowed agent can make its partner give up waiting, so these `coop` scores are slightly less reliable. See [model_config.md](model_config.md#concurrency) for agents per key by model and thinking level.

## Step Counter

`gemini-3.8-flash` at `high`. The first three result columns use 100 steps and 28K compaction; "not run" marks combinations without a run:

| Setting | No counter | Limit stated once in the prompt | Step counter | 250 steps, no counter | 250 steps, 64K, step counter |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `solo` | 1/10, 0/10 | 0/10 | **7/10** | 2/10 (28K), 7/10 (64K) | **9/10** |
| `coop --git` | 3/10 | not run | **8/10** | 8/10 (28K and 64K) | not run |
| `team` | not run | not run | 4/10 | 5/10 (28K) | not run |

- **The counter changes when agents publish, not how long they work.** In `solo`, 6 of 10 agents still used all 100 steps, but 9 of 10 pushed work before being stopped (0 to 1 of 10 without the counter). Most agents pushed several times along the way, so their last pushed version was graded. In `coop --git`, 19 of 20 agents pushed work (9 of 20 without it).
- **It also helps at a larger budget:** with 250 steps and 64K compaction, `solo` with the counter passed 9/10 (7/10 without it), every agent pushed work, and none hit the step limit.
- **Cost stayed the same:** `$9.11` (`solo`) and `$12.53` (`coop --git`), similar to the runs without the counter.
- **On harder pairs it is not enough:** on the `core` subset (which includes three pairs where both features change the same function), `solo` with the counter scored 5/10, and all 10 agents used every step. `coop --git` scored 4/10 there, and its only two merge conflicts were on same-function pairs (`dspy_task/8563`, `react_hook_form_task/153`).

## `team` Baseline

In `team`, a lead and a member each implement one feature, share a task list, and the lead integrates and submits.

- **250 steps, 28K, no counter:** 5/10, against 8/10 for both `coop` and `coop --git`. In 4 of the 5 passes the two patches merged cleanly. `typst_task/6554` passed only because the lead had written both features: after the merge conflict, the grader falls back to testing the lead's patch alone. Agents sent no direct messages and coordinated through the shared task list. One lead crashed because of a harness bug, since fixed in the fork ([harness_limits.md](harness_limits.md)).
- **100 steps, 28K, step counter:** 4/10, against 8/10 for `coop --git`. The lead, which also integrates, used all 100 steps in 6 of 10 pairs (the member in 3 of 10), and in 2 pairs the lead pushed nothing.

## Conclusions

1. **Use `gemini-3.8-flash`.** It is our proposal's model and current. The `gemini-3-flash-preview` runs connect our setup to the paper's result.
2. **Make the step counter standard for every setting.** It gives agents information they need, it is cheap, and it applies equally to `solo`, `coop`, and `team`. It is our one prompt change from upstream, and it should be documented as such.
3. **Pick the thinking level and budget from `solo` saturation runs.** On the 50-pair `flash` subset with 500 steps, 64K compaction, and the counter, `solo` solved 36/50 at `low` (`$25.70`) vs. 34/50 at `high` (`$110.14`, 37/50 combined), and `coop --git` at `low` dropped to 30/50 (`$39.85`) despite 0 step-limit cutoffs and 0 merge conflicts. See [saturation_flash.md](saturation_flash.md) for the full comparison.
4. **10 pairs are too few to rank close settings.** Differences of 1 to 2 pairs are within run-to-run variation; the 50-pair runs address this.
