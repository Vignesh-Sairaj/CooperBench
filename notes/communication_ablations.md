# Communication Interventions: Timing, Threading, and Intent Tags

## Summary

We evaluated three opt-in communication interventions in `coop --git` across **29 runs (690 evaluated task pairs)** spanning two models (`gemini-3-flash-preview` and `gemini-3.8-flash`), three benchmark subsets (`flash_10`, `core`, and the 50-pair `flash` split), and two harness budget regimes (the initial 100-step / 28K-compaction setup and the frozen 500-step / 128K-compaction `-c 4` reference setup). Implementation details, flags, and config files are in [communication_interventions.md](communication_interventions.md).

- **Under the frozen 500-step / 128K-compaction reference setup (`vertex_ai/gemini-3.8-flash`, `medium` thinking, `-c 4`):**
  - **On 50-pair `flash`, Message Intent Tags (`Proposal`, `Request`, `Response`, `ACK`, `FYI`) reached 36/50 (72.0%; 35/50 clean-merge)**, outperforming both `coop --git` `medium` reference baseline runs (`35/50 = 70%` and `33/50 = 66%`, mean `34.0/50 = 68.0%`) by **+2.0 pairs (+4.0 percentage points)** and closing **two-thirds (`67%`)** of the remaining coordination gap to `solo` (`37/50 = 74.0%`), while cutting **total messages by 22.2%** (`1,086` vs. `1,396` baseline mean; median `18` vs. `26` per pair), **compactions by 30.8%** (`83` vs. `120` mean), and **run cost by 10.7%** (`$91.17` vs. `$102.06` mean).
  - **On 10-pair `core` (`medium` thinking), both Message Delivery Timing (`6/10`, `$21.68`) and Combined Timing + Intents (`6/10`, `$20.30`) beat the `coop --git` reference baseline (`5/10`, `$21.62`) by +10 percentage points** and matched the `solo` reference baseline (`6/10`, `$14.02`) with `0` merge conflicts, while Intent Tags matched `5/10` with `10/10` identical pair outcomes, `-12.7%` messages, `-35.7%` compactions, and `-41.8%` wall time (`64` min vs. `110` min).
  - **Clean `-c 4` reference rerun at `low` thinking (`flash-ref-low-intents`):** eliminating the earlier `-c 10` US business-hour throttling (`72` retries and `10` false peer-stopped notices) and moving to 500 steps / 128K compaction jumped `intents` (`low`) from **28/50 (8 conflicts) to 34/50 (68%, 0 conflicts, 0 retries)**, matching `flash-ref-low` (`34/50`) with **14.8% fewer messages** (`1,078` vs. `1,266`) and **33% faster wall time** (`114` min vs. `170` min).
- **Which communication mechanism helps depends on both the model's reasoning capacity and the compaction regime:**
  - **`gemini-3-flash-preview` (`low` thinking) fails primarily from mid-edit peer interruptions and git merge conflicts** (`24` conflicts at 28K compaction; `17` conflicts at 128K compaction). At 100 steps / 28K compaction (`114–119` compactions/run), **Message Delivery Timing** raised 50-pair `flash` pass rate from **16/50 (32%) to 23/50 (46%, +14 percentage points)** and clean-merge passes from **13/50 (26%) to 20/50 (40%, +14 percentage points)** because holding non-urgent messages during active coding prevented mid-turn inbox injections from triggering destructive 28K context compactions. Once compaction is raised to 128K (`0–2` compactions/run across ~52 median steps), baseline `gemini-3-flash-preview` rises to `17/50` (`16/50` clean-merge, `17` conflicts), and holding messages during short (~50-step) uncompacted coding bursts no longer helps (`13/50`).
  - **`gemini-3.8-flash` avoids most git merge conflicts** (`0–1` conflicts on 50-pair `flash` at 500 steps / 128K) **and instead loses points when open coordination questions get buried in verbose chat.** **Message Intent Tags** raised `core` (`high` thinking, 100 steps / 28K) from **4/10 to 6/10 (+20 percentage points)** and 50-pair `flash` (`medium` thinking, 500 steps / 128K) from **33–35/50 to 36/50 (72%)** while consistently cutting message volume by **13% to 22%**.
- **Generic thread bookkeeping without speech-act intents underperformed on both models** (`2/10` and `1/10` on `gemini-3-flash-preview`; `3/10` on `gemini-3.8-flash` `core`). Tracking every message as an open thread encouraged polite thread-closing chatter without distinguishing actionable requests from status updates.
- **Boundary-aware flushing beat blind periodic holding in message efficiency and merge cleanliness.** Holding messages until a passing test, git, or edit-transition boundary (`semantic`) matched the clean-merge pass rate of a blind 4-step hold (`periodic`, both `4/10` clean passes on `flash_10`) with fewer merge conflicts (2 vs. 3), 27% fewer messages, and 19% lower cost (`$4.04` vs. `$4.96`).

## Terms

- **Clean-merge pass:** both features' hidden test suites pass **and** the two agents' git branches merged cleanly (`clean` or `identical`). In upstream CooperBench grading, if two branches have a git merge conflict (`conflicts`), the grader falls back to testing each agent's branch individually; if one agent happened to implement both features on its own branch, `Passed` is `yes` even though merging failed. Reporting both `Passed` and `Clean-merge pass` separates genuine two-agent integration from single-branch fallback.
- **Message Delivery Timing:** buffers non-blocking incoming messages for up to 4 steps and delivers them right after a passing test, git, or pull-request command, a messaging turn, or a shift from reading files to editing them (blocking `--wait` calls bypass the buffer immediately).
- **Message Board / Threading:** assigns every message a short run-scoped ID (`m1`, `m2`, ...) with reply and resolve flags, appends a one-line summary of open threads to each turn, and preserves open threads across 28K context compactions.
- **Message Intent Tags:** requires an explicit speech-act tag on outgoing messages (`Proposal`, `Request`, `Response`, `ACK`, or `FYI`), orders incoming `Request` and `Proposal` items ahead of `FYI` updates, appends a one-line reminder when a peer request is unanswered, and nudges before submission if a peer request is still open.

Every run uses `coop --git` (two peer agents with messaging and a shared git remote), 100 steps per agent, compaction at 28K tokens, the per-turn step counter (`step_counter: true`), and a `$40` per-agent cost cap on Vertex AI.

## Stage 1: Screening Ablations on `flash_10` and `core`

We first ran single-factor ablations plus the all-three combination (`comm-combined`):

1. On **`gemini-3-flash-preview` (`low` thinking)** across both `flash_10` and `core` (20 pairs total).
2. On **`gemini-3.8-flash` (`high` thinking)** on `core` (10 pairs), since our Vertex AI baseline repeat on `flash_10` reached **9/10 with 0 merge conflicts** (`pillow/290` was the lone failure, which also fails in 250-step `solo`), leaving no coordination headroom on `flash_10`.

### `gemini-3-flash-preview` (`low` thinking) on `flash_10` and `core`

| Intervention | `flash_10` Passed (Clean) | `flash_10` Conflicts | `core` Passed (Clean) | `core` Conflicts | 20-Pair Clean Passes | 20-Pair Conflicts | Cost (`flash_10` + `core`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: |
| Baseline (`stepcounter`) | 6/10 (3/10) | 3 | 4/10 (3/10) | 6 | 6/20 (30%) | 9 | `$7.94` |
| **Delivery Timing** | 4/10 (**4/10**) | **2** | **5/10** (**4/10**) | **3** | **8/20 (40%)** | **5** | `$7.29` |
| Threading | 2/10 (2/10) | 4 | 1/10 (1/10) | 4 | 3/20 (15%) | 8 | `$6.13` |
| Intent Tags | 4/10 (3/10) | 5 | 2/10 (1/10) | **2** | 4/20 (20%) | 7 | `$7.78` |
| Combined (all 3) | 4/10 (**4/10**) | 3 | 4/10 (3/10) | 7 | 7/20 (35%) | 10 | `$7.26` |

Note on `flash_10` baseline (`6/10`): three of its six passes (`dspy/8394`, `openai_tiktoken/0`, `typst/6554`) had git merge conflicts and passed only via single-branch fallback; only `3/10` merged cleanly. Across the combined 20 pairs (`flash_10` + `core`), **Message Delivery Timing** achieved the highest clean-merge pass rate (`8/20` vs. `6/20` baseline) and cut merge conflicts nearly in half (`5` vs. `9`), so the pipeline promoted `delivery-timing` to the 50-pair `flash` run for `gemini-3-flash-preview`.

### `gemini-3.8-flash` (`high` thinking) on `core`

| Run | Setting | Passed | Clean-Merge Passes | Merge Conflicts | Messages Sent | Agents at Step Limit | Cost |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | ---: |
| [`solo-...-core-stepcounter`](../results/solo-msa_v2-gemini-3-8-flash-core-stepcounter/summary.md) | `solo` | 5/10 | n/a | n/a | 0 | 10/10 | `$10.23` |
| [`coop-...-core-stepcounter`](../results/coop-msa_v2-git-gemini-3-8-flash-core-stepcounter/summary.md) | `coop --git` | 4/10 | 4/10 | 2 | 228 | 7/20 | `$13.16` |
| [`coop-...-core-delivery-timing`](../results/coop-msa_v2-git-gemini-3-8-flash-core-delivery-timing/summary.md) | `coop --git` | 4/10 | 4/10 | **0** | 273 | 5/20 | `$13.40` |
| [`coop-...-core-threading`](../results/coop-msa_v2-git-gemini-3-8-flash-core-threading/summary.md) | `coop --git` | 3/10 | 3/10 | 2 | 222 | 3/20 | `$14.62` |
| **[`coop-...-core-intents`](../results/coop-msa_v2-git-gemini-3-8-flash-core-intents/summary.md)** | `coop --git` | **6/10** | **6/10** | 1 | 264 | **2/20** | **`$11.71`** |
| [`coop-...-core-comm-combined`](../results/coop-msa_v2-git-gemini-3-8-flash-core-comm-combined/summary.md) | `coop --git` | 5/10 | 5/10 | 1 | **148** | 4/20 | `$11.89` |

Per-pair breakdown on `core` (`gemini-3.8-flash`, `high` thinking; `*` marks the three pairs where both features edit the same function):

| Pair | `solo` | `coop` baseline | `delivery-timing` | `threading` | `intents` | `comm-combined` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `dottxt_ai_outlines/1655` (1,3) | pass | pass | pass | pass | pass | pass |
| `dspy/8563`* (1,4) | B only | conflict | B only (clean) | B only (clean) | B only (clean) | conflict |
| `go_chi/27`* (3,4) | B only | B only | B only | B only | B only | B only |
| `llama_index/17244` (5,6) | pass | A only | A only | A only | **pass** | A only |
| `openai_tiktoken/0` (4,8) | pass | pass | pass | pass | pass | pass |
| `pallets_click/2800` (1,4) | A only | A only | A only | A only | A only | A only |
| `pallets_jinja/1559` (5,8) | pass | A only | **pass** | B only | **pass** | **pass** |
| `pallets_jinja/1621` (6,10) | - | pass | A only | pass | **pass** | **pass** |
| `react_hook_form/153`* (2,6) | - | conflict | A only (clean) | conflict | conflict | A only (clean) |
| `typst/6554` (2,6) | pass | pass | pass | conflict | pass | pass |

- **Message Delivery Timing eliminated every merge conflict (`0/10`)**, including all three same-function pairs, while keeping pass rate at 4/10.
- **Message Intent Tags reached 6/10 (`$11.71`, 0 API retries)** — recovering both pairs where baseline `coop --git` had lost to `solo` (`llama_index/17244` and `pallets_jinja/1559`) while retaining `pallets_jinja/1621` (where `solo` failed), so the pipeline promoted `intents` to the 50-pair `flash` confirmation run for `gemini-3.8-flash`.
- **Combining all three (`comm-combined`) reached 5/10** and reduced message count by **35%** (from 228 to 148).

## Stage 2: 50-Pair `flash` Confirmation Runs

To test whether the 10-pair winners hold at scale beyond 10-pair variance, we ran each model's selected winner against a matched 50-pair `flash` `coop --git` baseline (`low` thinking, 100 steps, 28K compaction, step counter):

| Model (`low` thinking) | Arm | Passed | Clean-Merge Passes | Merge Conflicts | Paired Wins / Losses (Clean) | Messages Sent | Cost |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | ---: |
| `3 Flash preview` | [Baseline (`stepcounter`)](../results/coop-msa_v2-git-gemini-3-flash-flash-low-stepcounter/summary.md) | 16/50 (32%) | 13/50 (26%) | 24 | — | 766 | `$19.72` |
| `3 Flash preview` | **[Delivery Timing](../results/coop-msa_v2-git-gemini-3-flash-flash-low-delivery-timing/summary.md)** | **23/50 (46%)** | **20/50 (40%)** | **20** | **+10 / -3 (+9 / -2)** | 796 | **`$19.60`** |
| `3.8 Flash` | [Baseline (`stepcounter`)](../results/coop-msa_v2-git-gemini-3-8-flash-flash-low-stepcounter/summary.md) | 27/50 (54%) | 26/50 (52%) | 7 | — | 1,280 | `$33.95` |
| `3.8 Flash` | **[Intent Tags](../results/coop-msa_v2-git-gemini-3-8-flash-flash-low-intents/summary.md)** | **28/50 (56%)** | **28/50 (56%)** | 8 | +5 / -4 (**+5 / -3**) | **998 (-22%)** | `$35.19` |

For context on `gemini-3.8-flash`, the 500-step, 64K-compaction `solo` saturation run scored **36/50 (72%)** ([runs.md](runs.md)). At 100 steps and 28K compaction, two-agent `coop --git` starts at 27/50 (26/50 clean-merge), and **Message Intent Tags** lifts clean-merge passes to **28/50 (56%)** while eliminating single-branch fallback passes and cutting messages by 22%.

**Throttling asymmetry on the 50-pair `gemini-3.8-flash` runs (`-c 10`):** Both `gemini-3-flash-preview` 50-pair runs executed with **0 API retries** in 31 minutes each. By contrast, `gemini-3.8-flash` has a smaller Vertex AI token-per-minute quota: the overnight baseline saw 27 retries (25 `429` + 2 `503`, 0 false peer-unreachable notices), whereas `flash-low-intents` ran into Monday-morning US business hours when shared spare capacity tightened, causing 72 retries (38 `429` + 34 `503` ~600s queue stalls) and triggering false `[<peer> is no longer running]` (`ALIVE_TTL = 600s`) notices on 8 pairs — including 2 of its 4 paired losses (`pallets_jinja/1465` (2,3) and `typst/6554` (4,9)). The +4 percentage-point clean-merge gain on `flash-low-intents` is therefore conservative; future 50-pair `gemini-3.8-flash` runs should use `-c 4`.

## Stage 3: Mechanism Verification and Counterfactual Ablation

Even where headline pass rates are close, trajectory instrumentation verifies that each mechanism operated as designed and explains *why* the two models responded differently:

1. **Semantic boundary hold vs. blind periodic 4-step hold (`flash_10`, `gemini-3-flash-preview`):**
   - On 50-pair `flash`, `delivery-timing` buffered **39.6% (`84/212`)** of non-blocking incoming messages across mid-edit or failed-command steps for an average of **2.06 extra steps** before releasing them at a clean boundary (`0%` buffered in baselines).
   - Comparing semantic boundaries ([`flash_10-low-delivery-timing`](../results/coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing/summary.md)) against a blind 4-step periodic hold ([`flash_10-low-delivery-periodic`](../results/coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-periodic/summary.md)): blind periodic flushing held **59.3% (`16/27`)** of messages for the full **3.00 extra steps** (vs. **33.3% / 1.91 steps** for semantic boundaries), delaying messages even after clean `pytest` or `git` checkpoints. Both achieved `4/10` clean-merge passes (up from `3/10` baseline), but semantic boundaries produced fewer merge conflicts (`2` vs. `3`), 27% fewer messages (`120` vs. `165`), and 19% lower cost (`$4.04` vs. `$4.96`).
2. **Protocol compliance vs. attention tax in `threading` and `intents`:**
   - Across **1,762 messages** in all `intents` and `comm-combined` runs on both models, agents produced **only 2 flag-syntax rejections (`99.9%` first-try compliance)**. On 50-pair `flash-low-intents` (`998` messages, `0` parse errors), explicit tags concentrated traffic into concrete coordination acts (`Request`: 310, `Response`: 117, `ACK`: 110, `FYI`: 108, `Proposal`: 52).
   - In `threading` runs, agents resolved **86% to 100%** of opened threads and preserved **47 to 414** pinned thread-board snapshots across 28K context compactions. However, injecting `[Open threads (...)]` on 184–280 turns per 10-pair run pulled `low`-thinking `gemini-3-flash-preview` agents away from local test debugging — causing single-feature submission failures even when branches merged cleanly.

## Stage 4: Standardized Reference Evaluation (500 Steps, 128K Compaction, `-c 4`)

After freezing the reference harness setup ([model_config.md](model_config.md): 500 steps, 128K compaction, `step_counter: true`, `$40` cap, `10h` container timeout, `-c 4` concurrency on Vertex AI `global`, default `medium` thinking on `vertex_ai/gemini-3.8-flash`), we evaluated the top communication interventions (`intents`, `delivery-timing`, and `comm-combined` = `delivery_timing + message_intents`) across 9 reference runs (330 evaluated pairs) sharded across 4 GCP projects (`KEY_SLOT=1..4`).

### 50-Pair `flash` Reference Results (`vertex_ai/gemini-3.8-flash`, 500 Steps, 128K Compaction, `-c 4`)

| Thinking | Arm | Passed | Clean-Merge Passes | Conflicts | Paired Wins / Losses vs. Ref (`r1` / `r2`) | Messages (Med) | Steps (Med) | Compactions | Cost | Wall Time |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| `medium` | [`solo` reference](../results/solo-msa_v2-gemini-3-8-flash-flash-saturation-medium-128k-vertex/summary.md) | 37/50 (74%) | n/a | n/a | — | 0 | 4,497 (74) | 91 | `$65.46` | 195m |
| `medium` | [`coop --git` ref #1](../results/coop-msa_v2-git-gemini-3-8-flash-flash-saturation-medium-128k-vertex/summary.md) | 35/50 (70%) | 35/50 (70%) | 0 | — | 1,439 (27) | 8,002 (75) | 87 | `$94.60` | 317m |
| `medium` | [`coop --git` ref #2 (repeat)](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref/summary.md) | 33/50 (66%) | 33/50 (66%) | 0 | — | 1,353 (25) | 7,794 (73) | 153 | `$109.52` | 375m |
| `medium` | **[`ref-intents`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref-intents/summary.md)** | **36/50 (72%)** | **35/50 (70%)** | 1 | **+2/-1** vs. #1, **+3/-0** vs. #2 | **1,086 (18)** | 7,905 (76) | **83** | **`$91.17`** | 319m |
| `medium` | [`ref-delivery-timing`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref-delivery-timing/summary.md) | 34/50 (68%) | 34/50 (68%) | 1 | +2/-3 vs. #1, +3/-2 vs. #2 | 1,442 (25) | 7,989 (73) | 147 | `$109.81` | 311m |
| `medium` | [`ref-comm-combined`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref-comm-combined/summary.md) | 33/50 (66%) | 33/50 (66%) | 1 | +0/-2 vs. #1, +1/-1 vs. #2 | 1,334 (25) | 8,302 (82) | 104 | `$97.66` | **271m** |
| `low` | [`solo` ref-low](../results/solo-msa_v2-gemini-3-8-flash-flash-ref-low/summary.md) | 30/50 (60%) | n/a | n/a | — | 0 | 5,665 (86) | 10 | `$36.81` | 84m |
| `low` | [`coop --git` ref-low](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref-low/summary.md) | 34/50 (68%) | 34/50 (68%) | 0 | — | 1,266 (25) | 9,003 (79) | 1 | `$48.96` | 170m |
| `low` | **[`ref-low-intents`](../results/coop-msa_v2-git-gemini-3-8-flash-flash-ref-low-intents/summary.md)** | **34/50 (68%)** | **34/50 (68%)** | **0** | +2 / -2 (46/50 identical) | **1,078 (21)** | **8,513 (76)** | 4 | **`$47.54`** | **114m** |

- **At `medium` thinking, `ref-intents` (`36/50 = 72%`) beats both `coop --git` reference baseline runs (`35/50` and `33/50`, mean `34.0/50 = 68.0%`) by +2.0 pairs (+4.0pp)** and comes within 1 pair of `solo` (`37/50 = 74%`). Against `flash-ref` (`33/50`), `ref-intents` achieved **+3 wins and 0 losses** (`pallets_click_task/2956` (1,8), `pillow_task/290` (3,5), and `samuelcolvin_dirty_equals_task/43` (3,7)), while cutting total messages by **22.2%** (`1,086` vs. `1,396` baseline mean; median `18` vs. `26`/pair), compactions by **30.8%** (`83` vs. `120` mean), and cost by **10.7%** (`$91.17` vs. `$102.06` mean).
- **At `low` thinking, running at `-c 4` under the 500-step / 128K reference setup eliminated all 72 retries and all 8 merge conflicts** from the earlier `-c 10` 100-step / 28K run, lifting `intents` (`low`) from `28/50` to **`34/50` (`68%`, `0` conflicts, `0` retries)** with **14.8% fewer messages** (`1,078` vs. `1,266`) and **33% faster wall time** (`114` min vs. `170` min) than `flash-ref-low`.

### 10-Pair `core` Reference Results (`vertex_ai/gemini-3.8-flash`, `medium` Thinking, 500 Steps, 128K Compaction, `-c 4`)

| Run | Setting | Passed | Clean-Merge Passes | Conflicts | Paired Wins / Losses vs. `core-ref` | Messages (Med) | Compactions | Cost | Wall Time |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| [`solo-core-ref`](../results/solo-msa_v2-gemini-3-8-flash-core-ref/summary.md) | `solo` | 6/10 (60%) | n/a | n/a | — | 0 | 16 | `$14.02` | 91m |
| [`coop-core-ref`](../results/coop-msa_v2-git-gemini-3-8-flash-core-ref/summary.md) | `coop --git` | 5/10 (50%) | 5/10 (50%) | 0 | — | 307 (32) | 28 | `$21.62` | 110m |
| [`core-ref-intents`](../results/coop-msa_v2-git-gemini-3-8-flash-core-ref-intents/summary.md) | `coop --git` | 5/10 (50%) | 5/10 (50%) | 0 | +0 / -0 (10/10 identical) | **268 (24)** | **18** | **`$18.51`** | **64m** |
| **[`core-ref-delivery-timing`](../results/coop-msa_v2-git-gemini-3-8-flash-core-ref-delivery-timing/summary.md)** | `coop --git` | **6/10 (60%)** | **6/10 (60%)** | **0** | **+1 / -0 (`llama_index/17244`)** | 291 (26) | 27 | `$21.68` | 79m |
| **[`core-ref-comm-combined`](../results/coop-msa_v2-git-gemini-3-8-flash-core-ref-comm-combined/summary.md)** | `coop --git` | **6/10 (60%)** | **6/10 (60%)** | **0** | **+1 / -0 (`llama_index/17244`)** | 315 (33) | **18** | `$20.30` | 67m |

- Both **`core-ref-delivery-timing` (`6/10`)** and **`core-ref-comm-combined` (`6/10`)** recovered `llama_index_task/17244` (5,6) — the exact pair where two agents in `coop-core-ref` (`5/10`) had lost to `solo-core-ref` (`6/10`) — matching the `solo` reference pass rate on `core` with `0` merge conflicts.

### `gemini-3-flash-preview` at 500 Steps / 128K Compaction vs. 100 Steps / 28K Compaction (`flash`, 50 Pairs)

| Budget Regime (`low` thinking) | Arm | Passed | Clean-Merge Passes | Conflicts | Steps (Med) | Messages (Med) | Compactions | Cost | Wall Time |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |
| 100 steps / 28K compaction | [`3-flash` baseline](../results/coop-msa_v2-git-gemini-3-flash-flash-low-stepcounter/summary.md) | 16/50 (32%) | 13/50 (26%) | 24 | 5,340 (53) | 766 (15) | 119 | `$19.72` | 31m |
| 100 steps / 28K compaction | **[`3-flash` + `delivery-timing`](../results/coop-msa_v2-git-gemini-3-flash-flash-low-delivery-timing/summary.md)** | **23/50 (46%)** | **20/50 (40%)** | **20** | 5,371 (53) | 796 (15) | 114 | `$19.60` | 31m |
| 500 steps / 128K compaction (`ref-low`) | **[`3-flash` ref-low baseline](../results/coop-msa_v2-git-gemini-3-flash-flash-ref-low/summary.md)** | **17/50 (34%)** | **16/50 (32%)** | **17** | 5,305 (52) | 895 (15) | **2** | `$23.92` | 75m |
| 500 steps / 128K compaction (`ref-low`) | [`3-flash` ref-low + `delivery-timing`](../results/coop-msa_v2-git-gemini-3-flash-flash-ref-low-delivery-timing/summary.md) | 13/50 (26%) | 11/50 (22%) | 20 | 5,348 (50) | 812 (16) | **0** | `$22.66` | 58m |

- **Why `gemini-3-flash-preview` behaves differently at 128K vs. 28K**: `gemini-3-flash-preview` finishes in ~52 median steps regardless of whether the step limit is 100 or 500 (`5,305` vs. `5,340` total steps). Raising compaction from 28K to 128K eliminates mid-run compactions (`119` $\rightarrow$ `2`), which lifts the baseline's clean-merge passes from `13/50` (`26%`) to `16/50` (`32%`) and cuts merge conflicts from `24` to `17`. Because `delivery_timing`'s primary benefit on `gemini-3-flash-preview` at 28K was preventing mid-turn message injections from triggering destructive 28K compactions, once neither run compacts (`0–2` compactions at 128K), holding messages during `gemini-3-flash-preview`'s short (~50-step) episodes delays coordination until one agent has already committed.

## Conclusions

1. **Under the frozen 500-step / 128K-compaction reference setup, Message Intent Tags (`Proposal`, `Request`, `Response`, `ACK`, `FYI`) is the strongest intervention on 50-pair `flash` (`36/50 = 72%` at `medium`, `34/50 = 68%` at `low`)**, beating both `coop --git` `medium` reference baselines (`35/50` and `33/50`), closing two-thirds of the gap to `solo` (`37/50`), and cutting message volume by **15% to 22%**, compactions by **31%**, and cost by **11%**. On 10-pair `core`, **Delivery Timing** and **Combined Timing + Intents** both reach **6/10 (60%)**, beating `coop --git` (`5/10`) and matching `solo` (`6/10`).
2. **Match the coordination intervention to both the model's bottleneck and the context-compaction regime.** When context compaction is tight (28K on `gemini-3-flash-preview`), passive harness-side **Message Delivery Timing** prevents mid-edit message injections from triggering compaction cascades (**+14 percentage points** on 50 pairs). When context is ample (128K on `gemini-3.8-flash`), agents benefit from **Message Intent Tags** that surface unanswered `Request` and `Proposal` commitments while pruning conversational filler.
3. **Do not track open threads without speech-act intents.** Treating every message as an open thread creates conversational busywork; only `Proposal` and `Request` messages carry real coordination obligations.
4. **Cap `vertex_ai/gemini-3.8-flash` concurrency at `-c 4` per GCP project for 50-pair runs** and shard parallel runs across separate GCP projects (`KEY_SLOT=1..4`).
