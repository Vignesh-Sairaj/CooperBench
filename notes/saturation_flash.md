# Saturation Experiments on the 50-Pair `flash` Subset

## Summary

On the 10-pair `flash_10` subset, `solo` and `coop --git` with `gemini-3.8-flash` were within 1 pair of each other, too close to separate on 10 pairs ([model_thinking_stepcounter_flash10.md](model_thinking_stepcounter_flash10.md)). The 500-step, 64K-compaction "saturation" runs below measure single-agent capability limits and multi-agent coordination losses on the 50-pair `flash` subset without budget starvation:

- **`low` thinking matches or beats `high` thinking in `solo` at one-quarter the cost.** `solo` scored **36/50 (72%)** for `$25.70` at `low` thinking and **34/50 (68%)** for `$110.14` at `high` thinking. Across both runs, `solo` solved **37/50 (74%)**, leaving **13/50 (26%)** unsolved at either thinking level.
- **At `low` thinking, `solo` beats `coop --git` by 12 percentage points (`36/50` vs. `30/50`) and `team` by 28 percentage points (`36/50` vs. `22/50`); at `high` thinking, `coop --git` catches up to `solo` (`34/50` vs. `34/50`).** `coop --git` rose from **30/50 (60%)** (`$39.85`) at `low` thinking to **34/50 (68%)** (`$96.17`) at `high` thinking, matching `solo` `high` (`34/50`, `$110.14`) and agreeing with it on 48 of 50 pairs (`33` passed in both, `15` failed in both, `1` `solo`-only, and `1` `coop`-only on `samuelcolvin_dirty_equals_task/43` (3,7)).
- **Both `coop --git` runs had zero step-limit cutoffs and zero git merge conflicts, yet conflict-avoidance workarounds persisted at both thinking levels.** All 100 `coop --git` agents submitted well below the 500-step limit (`max 186` at `low`, `max 271` at `high`) and merged cleanly on all 50 pairs. Stronger reasoning eliminated single-feature edge-case bugs that slipped past trial merges at `low` thinking, while peers at both `low` and `high` still avoided editing shared constructor call lines by setting attributes on instances afterward (causing 2 losses at `low` and `coop --git` `high`'s sole loss vs. `solo` `high` on `pallets_click_task/2068` (6,7)).
- **`team` falls behind `coop --git` (`22/50` vs. `30/50` at `low`) largely because of a harness submission mismatch.** Without a shared git server and under conflicting prompt instructions (one telling each agent to push only its own feature to git, another telling the lead to combine both features in a local `patch.txt` file that the grader ignores; see [harness_limits.md](harness_limits.md)), `team` hit **30/50 merge conflicts** and lost 7 `solo`-solvable pairs when the lead's local integration was never pushed to git.

## Setup

Every run below uses `gemini-3.8-flash` on the 50-pair `flash` subset, a 500-step limit per agent, compaction at 64K tokens, the per-turn step counter ("Step n of 500: k left"), and a `$40` per-agent cost cap. Terms are defined in [runs.md](runs.md).

| Setting | Thinking | Passed | At step limit | Merge conflicts | Median steps / agent | Median compactions / agent | Cost | Wall time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| [`solo`](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-low/summary.md) | `low` | **36/50 (72%)** | 0/50 | n/a | 84 | 0 | `$25.70` | 98 min |
| [`solo`](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-high/summary.md) | `high` | **34/50 (68%)** | 2/50 | n/a | 169 | 7 | `$110.14` | 417 min |
| [`coop --git`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-saturation-low/summary.md) | `low` | **30/50 (60%)** | 0/100 | 0/50 | 87 | 0 | `$39.85` | 346 min |
| [`coop --git`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-saturation-high/summary.md) | `high` | **34/50 (68%)** | 0/100 | 0/50 | 104 | 3 | `$96.17` | 476 min |
| [`team`](../results/team-msa_v2-gemini-3-8-flash-flash-saturation-low/summary.md) | `low` | **22/50 (44%)** | 0/100 | 30/50 | 74.5 | 0 | `$35.10` | 433 min |
| [`solo`, no step counter](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-low-nostepcounter/summary.md) | `low` | **32/50 (64%)** | 1/50 | n/a | 84 | 0 | `$25.64` | 309 min |
| [`solo`, repeat on Vertex AI](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-low-vertex/summary.md) | `low` | **32/50 (64%)** | 1/50 | n/a | 74 | 0 | `$33.47` | 180 min |
| [`coop --git`, repeat on Vertex AI](../results/coop-msa_v2-git-gemini-3-8-flash-flash-saturation-low-vertex/summary.md) | `low` | **30/50 (60%)** | 0/100 | 2/50 | 173 per pair | n/a | `$55.29` | 257 min |

Every run uses the step counter except the no-counter control. All runs call the model through AI Studio except the Vertex AI repeat. Runs at `medium` thinking and a messaging-only `coop` run at `low` are in progress and will be added as they finish.

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

## Step Counter With Ample Budget

Turning the step counter off in `solo` at `low` thinking (everything else identical) lowered the score from 36/50 to 32/50 at the same cost (`$25.64` vs. `$25.70`). Pair by pair, 32 passed in both, 14 failed in both, 4 passed only with the counter, and none passed only without it (exact two-sided test, p = 0.125). Step use was nearly identical (median 84 per pair in both). One loss was a budget failure: without the counter, the agent on `pillow_task/290` (3,5) used all 500 steps, while with it the agent finished in 180 and passed. The other three were on-time submissions with one feature failing. The counter costs nothing and hurt no pair, so it is part of the standard setup. On its own, though, this 4-pair difference is within run-to-run variation: repeating the counter run on Vertex AI with identical settings also scored 32/50 (see below).

## Run-to-Run Variation

The same `solo` `low` setup scored 36/50 on AI Studio and 32/50 on Vertex AI. `solo` makes the same model calls on either provider, so the gap is ordinary variation: 31 pairs passed in both runs, 5 only on AI Studio, and 1 only on Vertex AI. Single-run differences of about 4 to 6 pairs on these 50 pairs, including the 6-pair gap between `solo` and `coop --git` at `low` thinking, need repeated runs or paired tests before they count as effects.

The `coop --git` `low` setup was also repeated on Vertex AI and scored 30/50 both times (28 pairs passed in both). Averaged over two runs each, `solo` scores about 34/50 and `coop --git` 30/50, so the coordination gap at `low` thinking is about 4 pairs rather than 6. Five `solo`-solvable pairs failed in both `coop --git` runs, including both `pallets_click_task/2068` pairs where agents work around a line both features need.

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

## `coop --git` at `high` Thinking: Closing the Single-Feature Gap While Conflict-Avoidance Remains

Raising `coop --git` from `low` to `high` thinking lifted accuracy from **30/50 (60%)** to **34/50 (68%)** (`$96.17`), matching `solo` at `high` thinking (`34/50`, `$110.14`):

| Outcome (`solo` `high` vs. `coop --git` `high`) | Pairs | Share |
| :--- | :---: | :---: |
| Both passed | 33 | 66% |
| `solo` `high` passed, `coop --git` `high` failed | **1** | **2%** |
| `coop --git` `high` passed, `solo` `high` failed | **1** | **2%** |
| Both failed | 15 | 30% |

- **Why `high` thinking helped `coop --git` (`30 -> 34`) without helping `solo` (`36 -> 34`):** Each `coop` peer holds one feature instead of two, so at `high` thinking `coop` agents compacted half as often as `solo` `high` agents (median **3** vs. **7** compactions, median **104** vs. **169** steps, and **0** vs. **2** step-limit cutoffs) and cost slightly less (`$96.17` vs. `$110.14`). That extra reasoning recovered single-feature state and edge-case bugs from `coop --git` `low` (`pallets_click_task/2800` (2,7) and `pallets_jinja_task/1621` (4,5)) and solved both `samuelcolvin_dirty_equals_task/43` pairs (`(2,3)` and `(3,7)`), including `(3,7)` which neither `solo` run solved (bringing total solved pairs across all `flash` runs to **38/50, 76%**).
- **Conflict-avoidance workarounds persisted even at `high` thinking.** On both `pallets_click_task/2068` (7,10) and `pallets_click_task/2068` (6,7), the peers again agreed in chat to let only one agent add its parameter to the shared constructor call line while the other assigned an attribute on the created instance afterward so `git merge` would stay conflict-free. On `(7,10)` that split passed because only the first feature's hidden tests checked constructor arguments; on `(6,7)` the second feature's hidden tests mocked the constructor and failed when its keyword argument was missing, accounting for `coop --git` `high`'s sole loss against `solo` `high`.

## `team` vs. `coop --git` at `low` Thinking

In `team` mode (one lead and one member with messaging, a shared task list, and a shared folder, without a shared git server), raising the budget to 500 steps and 64K compaction eliminated all step-limit cutoffs (0/100 agents at the limit, median 74.5 steps, max 212), yet accuracy stayed at **22/50 (44%)**:

| Outcome (`coop --git` `low` vs. `team` `low`) | Pairs | Share |
| :--- | :---: | :---: |
| Both passed | 19 | 38% |
| `coop --git` passed, `team` failed | **11** | **22%** |
| `team` passed, `coop --git` failed | **3** | **6%** |
| Both failed | 17 | 34% |

- **Half of `team`'s losses vs. `solo` (7 of 14) come from unpushed local integrations.** Because the `team` checklist tells the lead to apply the member's patch from the shared folder and save `git diff > patch.txt`, while the base submission prompt says not to push a colleague's changes to git and the grader only reads pushed git branches ([harness_limits.md](harness_limits.md)), 7 leads on `solo`-solvable pairs pushed only their own feature and left the integrated diff in `patch.txt`. When the two standalone branches hit text conflicts on shared files, the grader's lead-alone fallback ran both feature test suites against the lead's unintegrated branch and failed the member's feature.
- **When the lead did push both features to git, single-owner integration helped on shared call sites.** Nine of `team`'s 22 passes succeeded via the grader's lead-alone fallback after the lead's combined two-feature branch conflicted with the member's standalone branch. That single-integrator path accounted for two of `team`'s three wins over `coop --git` (`pallets_click_task/2068` (7,10) and `pallets_click_task/2800` (2,7)), because one agent editing the shared call site directly avoided the constructor-avoidance workarounds that broke two git peers. On 5 other `solo`-solvable pairs where the lead pushed a combined branch, one feature still failed hidden tests.

## Implications for Coordination Interventions

- **`low` thinking with 250 to 500 steps, 64K compaction, and the step counter is a fast, clean baseline for 50-pair experiments:** `$26` to `$40` per 50-pair run, zero step-limit noise, and a 6-pair coordination gap on `flash` where every `coop` loss is on a task the same model solves alone.
- **Interventions that only prevent text merge conflicts cannot raise `coop --git` above 30/50 here,** because conflict rate is already 0/50. Worse, pressuring agents to avoid overlapping line edits encourages fragile workarounds around shared call sites.
- **Closing the remaining gap requires semantic verification rather than line-locking:** specifically, encouraging clean signature/call-site integration (solving deliberate two-side edits cleanly rather than routing around constructors) and checking post-merge behavior and edge cases against each feature's contract rather than treating a conflict-free `git merge` as sufficient.
