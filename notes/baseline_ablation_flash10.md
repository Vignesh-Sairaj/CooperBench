# Step-Budget and Compaction Ablation (`flash_10`)

Proposal: Adopt `250 steps + 64K compaction` (`configs/variants/steps250_compact64k.yaml`) as our primary `HIGH`-thinking evaluation regime so both `solo` (`7/10`) and `coop --git` (`8/10` at 28K; 64K queued next) submit reliably instead of timing out unpushed under upstream's `100-step / 28K` defaults (`0/10` to `1/10` `solo`, `3/10` `coop --git`).

## Summary of `flash_10` Runs (`gemini/gemini-3.8-flash`, `HIGH` thinking)

| Run | Setting | Steps | Compaction | `-c` | Passed | Pushed | Med. compactions | Cost | Wall | Peak tok/min | `429` / `5xx` |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: | ---: | :---: |
| [ref](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) | `solo` | 100 | 28K | 10 | 1/10 (10%) | 1/10 | 9 (5..22) | `$8.92` | 49m | 947.6K | 0 / 0 |
| [r2](../results/solo-msa_v2-gemini-3-8-flash-flash_10-r2/summary.md) | `solo` | 100 | 28K | 10 | 0/10 (0%) | 0/10 | 8 (5..15) | `$8.99` | 107m* | 1,043.2K | 9 / 0 |
| [budgetprompt](../results/solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt/summary.md) | `solo` | 100 + prompt | 28K | 10 | 0/10 (0%) | 0/10 | 9 (5..17) | `$8.41` | 49m | 1,183.1K | 41 / 1 |
| [steps250](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `solo` | 250 | 28K | 10 | 2/10 (20%) | 2/10 | 24 (15..31) | `$18.75` | 90m | 1,271.9K | 64 / 2 |
| [steps250-compact64k](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `solo` | 250 | 64K | 4 | **7/10 (70%)** | 7/10 | 6 (2..22) | `$19.63` | 128m | 1,083.1K | 1 / 0 |
| [coop --git ref](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10/summary.md) | `coop --git` | 100 | 28K | 5 | 3/10 (30%) | 9/20 | 6 (2..12) | `$11.93` | 59m | 986.3K | 7 / 2 |
| [coop --git steps250](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop --git` | 250 | 28K | 5 | **8/10 (80%)** | 16/20 | 6 (2..25) | `$19.87` | 124m | 1,046.2K | 6 / 4 |

\*`r2` wall time includes an 83-minute `grep -rn "gh-pr" /` hang inside `go_chi_task/26` before manual process termination (see [harness_limits.md](harness_limits.md)). All 7 runs finished with `0` agent errors and `0` merge conflicts.

## Pair-by-Pair Outcomes

| Pair | `solo` 100/28K | `solo` `r2` | `solo` `budgetprompt` | `solo` 250/28K | `solo` 250/64K | `coop --git` 100/28K | `coop --git` 250/28K |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `dottxt_ai_outlines_task/1655` (7,10) | - | - | - | pass | pass | pass | pass |
| `dspy_task/8394` (3,4) | - | - | - | - | - | A only | pass |
| `go_chi_task/26` (1,2) | - | - | - | - | pass | A only | pass |
| `huggingface_datasets_task/6252` (4,6) | - | - | - | - | pass | B only | pass |
| `openai_tiktoken_task/0` (6,8) | - | - | - | - | pass | pass | pass |
| `pallets_click_task/2800` (1,7) | - | - | - | - | pass | - | pass |
| `pallets_jinja_task/1559` (4,8) | - | - | - | - | - | - | - |
| `pallets_jinja_task/1621` (4,5) | pass | - | - | pass | pass | pass | pass |
| `pillow_task/290` (4,5) | - | - | - | - | - | - | - |
| `typst_task/6554` (7,8) | - | - | - | - | pass | - | pass |

## Why the Results Moved

1. **Static prompt budget notices (`budgetprompt`) fail because compaction erases turn-count cues.** Across all 10 `budgetprompt` trajectories (including `HIGH` thinking traces), zero assistant messages mentioned the step cap. Because `DefaultAgent._compact_messages()` replaces older history every ~9 steps and retains only `compaction_keep_recent_turns: 2` while tool observations carry no step counter, the model never sees more than ~2 to 10 recent turns and cannot tell whether it is on step 12 or step 95. Any effective step-budget warning must inject remaining steps into per-turn tool observations in `default.py`.
2. **A 2-feature `solo` agent needs both 250 steps and 64K context (`7/10`), whereas two single-feature `coop` peers already hold `2 x 28K = 56K` aggregate context (`8/10` at 250 steps).** Raising `solo` to 250 steps at 28K lifted pass rate only from `1/10` to `2/10` because holding two features in a 28K window caused `15` to `31` compactions per agent (median `24`). Raising `solo`'s compaction trigger to `64K` cut median compactions from `24` to `6`, let 7 of 10 agents finish in `96` to `229` steps (`7/7` submitted passed both features), and kept run cost flat (`$19.63` vs. `$18.75`) because passing agents stopped early instead of running all 250 steps.
3. **Upstream's `100-step / 28K` defaults invert `solo` vs. `coop` on `HIGH`-thinking `gemini-3.8-flash`.** At 100 steps / 28K, `coop --git` (`30%`) appears 6x better than `solo` (`0%` to `10%`, mean `5%`) simply because splitting two features across two 100-step / 28K budgets lets one-feature peers finish before step 100. Giving `solo` matched context and step room (`250 steps / 64K`) restores a meaningful `70%` single-agent baseline.
4. **10 agents per key is too many at 28K (`0` agent errors, but frequent `429` retries).** `solo` at `-c 10` peaked at `0.95M` to `1.27M` input tok/min across four runs (`0` to `64` `429` retries), and `coop --git` at `-c 5` (also 10 agents) peaked at `986K` and `1,046K` (`7` and `6` `429` retries). `-c 4` for `solo` at 64K peaked at `1,083K` tok/min (`1` `429` retry, `0` `5xx` retries). We now use about 8 agents per key at 28K (`-c 8` `solo`, `-c 4` `coop`/`team`) and 4 at 64K; see [model_config.md](model_config.md#concurrency).

## Reference Setup Options for Team Decision

| Option | `solo` vs. `coop` signal | Cost per 10-pair run | Tradeoff |
| :--- | :--- | :---: | :--- |
| **`(Recommended)` `250 steps + 64K compaction` for all modes** (`steps250_compact64k.yaml`, `-c 4` `solo` / `-c 2` `coop`,`team`) | High (`70%` `solo`; equal per-agent context) | ~`$20`-`$25` | Slower concurrency (`4` agents/key); requires Wave 2 `coop --git` 64K check. |
| `250 steps + 28K compaction` (`steps250.yaml`, `-c 8` `solo` / `-c 4` `coop`,`team`) | Skewed (`20%` `solo` vs. `80%` `coop --git`) | ~`$19`-`$20` | Faster (`8` agents/key), but starves 2-feature `solo` on context. |
| Upstream `100 steps + 28K` + harness step-countdown hook (`default.py`, behind flag) | Untested (requires harness code flag) | ~`$9`-`$12` | Cheapest, but forces rushed commits instead of letting `HIGH` thinking finish. |

## Wave 2 Queue (Next Experiments on `flash_10`)

1. **`coop` (Redis messaging only, no `--git`) at 250 steps / 28K (`-c 5`)**: Isolates how much of `coop --git`'s `8/10` (`80%`) comes from shared git branch visibility vs. splitting the two features across two agents with Redis messaging, and measures baseline merge-conflict frequency without shared git.
2. **`coop --git` at 250 steps + 64K compaction (`-c 2`)**: Completes the 2x2 `{solo, coop --git} x {28K, 64K}` table at 250 steps for an apples-to-apples per-agent context comparison against `solo` `steps250-compact64k` (`7/10`).
3. **`team` mode at 250 steps / 28K (`-c 4`)**: Completes all four baseline topologies (`solo`, `coop`, `coop --git`, `team`) at 250 steps and checks genuine merges vs. lead-solo fallbacks.
