# Saturation Experiments on the 50-Pair `flash` Subset

## Summary

On the 10-pair `flash_10` subset, `solo` and `coop --git` with `gemini-3.8-flash` were within 1 pair of each other, too close to separate on 10 pairs ([model_thinking_stepcounter_flash10.md](model_thinking_stepcounter_flash10.md)). The 500-step, 64K-compaction "saturation" runs below measure single-agent capability limits and multi-agent coordination losses on the 50-pair `flash` subset without budget starvation:

- **`low` thinking matches or beats `high` thinking in `solo` at one-quarter the cost.** `solo` scored **36/50 (72%)** for `$25.70` at `low` thinking and **34/50 (68%)** for `$110.14` at `high` thinking. Across both runs, `solo` solved **37/50 (74%)**, leaving **13/50 (26%)** unsolved at either thinking level.
- **On 50 pairs, `solo` beats `coop --git` by 12 percentage points (`36/50` vs. `30/50`).** With the exact same `low` saturation setup, `coop --git` scored **30/50 (60%)** for `$39.85`, retaining 83% of `solo` `low` passes (`30/36`) and solving **0** pairs that `solo` `low` missed.
- **The 6-pair coordination drop happens with zero step-limit cutoffs and zero git merge conflicts.** All 100 `coop` agents submitted well below the 500-step limit (max 186 steps), and all 50 pairs merged without text conflicts. Notably, on 2 of the 6 lost pairs, agents introduced semantic bugs specifically to avoid editing the same call line in git.

## Setup

Every run below uses `gemini-3.8-flash` on the 50-pair `flash` subset, a 500-step limit per agent, compaction at 64K tokens, the per-turn step counter ("Step n of 500: k left"), and a `$40` per-agent cost cap. Terms are defined in [runs.md](runs.md).

| Setting | Thinking | Passed | At step limit | Merge conflicts | Median steps / agent | Median compactions / agent | Cost | Wall time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| [`solo`](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-low/summary.md) | `low` | **36/50 (72%)** | 0/50 | n/a | 84 | 0 | `$25.70` | 98 min |
| [`solo`](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-high/summary.md) | `high` | **34/50 (68%)** | 2/50 | n/a | 169 | 7 | `$110.14` | 417 min |
| [`coop --git`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-saturation-low/summary.md) | `low` | **30/50 (60%)** | 0/100 | 0/50 | 87 | 0 | `$39.85` | 346 min |

Additional runs in progress with the same 500-step, 64K setup (`coop --git` at `high`, `team` at `low`, messaging-only `coop` at `low`, a `solo` `low` control without the step counter, and matching runs on `core`) will be added here as they finish.

## `solo` Capability Ceiling: `low` vs. `high` Thinking

Comparing the two `solo` runs pair by pair shows what `gemini-3.8-flash` can solve when one agent sees both feature prompts and has ample steps:

| Outcome across `solo` `low` and `solo` `high` | Pairs | Details |
| :--- | :---: | :--- |
| Passed at both `low` and `high` | 33 | Core solvable set |
| Passed only at `low` | 3 | `pallets_click_task/2068` (5,11), `pallets_click_task/2956` (1,8), `pillow_task/290` (3,5) |
| Passed only at `high` | 1 | `samuelcolvin_dirty_equals_task/43` (2,3) |
| Failed at both `low` and `high` | 13 | Unsolved by `solo` at either thinking level |

- **More reasoning tokens did not raise accuracy.** At `high`, agents generated about 220K reasoning tokens each (11.0M across the run), compacted a median of 7 times, and cost `$2.20` per pair vs. `$0.51` at `low`, solving only 1 pair `low` missed while losing 3.
- **250 steps with the counter covers nearly all `low` passes.** Of the 36 `solo` `low` passes, 22 finished within 100 steps and 35 within 250 steps (max 345). At `high`, 26 of 34 passes finished within 250 steps and 8 needed 295 to 500 steps.
- **The 13 pairs unsolved by `solo` at both levels:** `dspy_task/8394` (3,5), `go_chi_task/56` (1,5), `huggingface_datasets_task/3997` (2,4), `llama_index_task/18813` (1,5) and (2,5), `openai_tiktoken_task/0` (2,9), `pallets_click_task/2068` (2,10), `pallets_click_task/2800` (1,3), `pillow_task/25` (1,5), `pillow_task/290` (2,3) and (4,5), `pillow_task/68` (1,5), and `samuelcolvin_dirty_equals_task/43` (3,7). In nearly all of these, one feature passed its hidden tests and the other missed an edge case in the specification.

## `solo` vs. `coop --git` at `low` Thinking

On 10 pairs (`flash_10`), `solo` and `coop --git` at `low` thinking scored 6/10 and 7/10. On 50 pairs with ample budget, the coordination penalty is clear:

| Outcome (`solo` `low` vs. `coop --git` `low`) | Pairs | Share |
| :--- | :---: | :---: |
| Both passed | 30 | 60% |
| `solo` passed, `coop --git` failed | **6** | **12%** |
| `coop --git` passed, `solo` failed | 0 | 0% |
| Both failed | 14 | 28% |

What stands out in the `coop --git` traces:

1. **Spatial coordination succeeded completely.** Every pair exchanged between 12 and 66 messages (median 28), negotiated file and line placement, ran trial merges before submitting, and produced **0 merge conflicts** across all 50 pairs (43 clean three-way merges and 7 identical pre-merged branches).
2. **Conflict avoidance itself caused semantic bugs (2 of the 6 losses).** In `pallets_click_task/2068` (6,7) and `pallets_click_task/2068` (7,10), both features add a new parameter to the same wrapper function and helper class. To avoid touching the same constructor call line in git, the peers explicitly agreed in chat to leave that call unchanged and attach their new setting as a class or instance attribute afterward. That kept `git merge` conflict-free and passed their own tests, and then broke the hidden unit tests that check constructor arguments.
3. **Trial-merge checks stopped at "no git conflicts and existing tests pass" (4 of the 6 losses).** In `pallets_click_task/2800` (2,7), `pallets_click_task/2956` (1,8), `pallets_jinja_task/1621` (4,5), and `pillow_task/290` (3,5), one feature passed and one failed because of a state or edge-case bug (clearing a callback on first exit so context reuse broke, updating raw palette bytes without updating the palette wrapper object, returning `None` instead of an empty completion list, or failing to ignore malformed tuple entries). Each peer verified that `git merge` succeeded cleanly and that tests passed, without reviewing the partner's logic or shared state invariants against the feature requirements.

## Implications for Coordination Interventions

- **`low` thinking with 250 to 500 steps, 64K compaction, and the step counter is a fast, clean baseline for 50-pair experiments:** `$26` to `$40` per 50-pair run, zero step-limit noise, and a 6-pair coordination gap on `flash` where every `coop` loss is on a task the same model solves alone.
- **Interventions that only prevent text merge conflicts cannot raise `coop --git` above 30/50 here,** because conflict rate is already 0/50. Worse, pressuring agents to avoid overlapping line edits encourages fragile workarounds around shared call sites.
- **Closing the remaining gap requires semantic verification rather than line-locking:** specifically, encouraging clean signature/call-site integration (solving deliberate two-side edits cleanly rather than routing around constructors) and checking post-merge behavior and edge cases against each feature's contract rather than treating a conflict-free `git merge` as sufficient.
