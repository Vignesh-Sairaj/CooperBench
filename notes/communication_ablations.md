# Communication Interventions: Timing, Threading, and Intent Tags

## Summary

We evaluated three opt-in communication interventions in `coop --git` across **20 runs (360 evaluated task pairs)** spanning two models (`gemini-3-flash-preview` and `gemini-3.8-flash`) and three benchmark subsets (`flash_10`, `core`, and the 50-pair `flash` split). Implementation details, flags, and config files are in [communication_interventions.md](communication_interventions.md).

- **Which communication mechanism helps depends sharply on the model's failure mode and reasoning capacity:**
  - **`gemini-3-flash-preview` (`low` thinking) fails primarily from mid-edit peer interruptions and git merge conflicts** (24 conflicts in 50 pairs on `flash`). **Message Delivery Timing** — a passive harness buffer that holds non-blocking peer messages up to 4 steps until a natural workflow boundary — raised 50-pair `flash` pass rate from **16/50 (32%) to 23/50 (46%, +14 percentage points)** and clean-merge passes from **13/50 (26%) to 20/50 (40%, +14 percentage points)** at identical cost (`$19.60` vs. `$19.72`), while explicit multi-flag protocols (`threading` and `intents`) hurt its solo feature completion.
  - **`gemini-3.8-flash` already avoids most git merge conflicts** (0 conflicts on `flash_10`, 2 on `core`, 7/50 on `flash`) **and instead loses points when open coordination questions get buried in free-form chat.** **Message Intent Tags** (`Proposal`, `Request`, `Response`, `ACK`, `FYI`) raised `core` (`high` thinking) from **4/10 to 6/10 (+20 percentage points over `coop --git` and +10 percentage points over 5/10 `solo`)** with 0 retries, and on 50-pair `flash` (`low` thinking) raised clean-merge passes from **26/50 (52%) to 28/50 (56%, +4 percentage points)** while cutting message volume by **22%** (1,280 to 998).
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

## Conclusions

1. **Match the coordination intervention to the model's bottleneck.** Faster, lower-reasoning agents (`gemini-3-flash-preview` at `low` thinking) are easily derailed when peer messages arrive mid-edit or mid-traceback; passive harness-side **Message Delivery Timing** yields a large, zero-cost gain (**+14 percentage points** on 50 pairs). Stronger reasoning agents (`gemini-3.8-flash`) handle timing interruptions well on their own (`7/50` conflicts vs. `24/50`) and benefit instead from **Message Intent Tags** that surface unanswered `Request` and `Proposal` commitments (**6/10 on `core`**, beating both `coop --git` and `solo`, and **+4 percentage points clean-merge** with **-22% messages** on 50-pair `flash`).
2. **Do not track open threads without speech-act intents.** Treating every message as an open thread creates conversational busywork; only `Proposal` and `Request` messages carry real coordination obligations.
3. **Cap `vertex_ai/gemini-3.8-flash` concurrency at `-c 4` for 50-pair runs** (or refresh peer heartbeats during long LLM calls) so peak-hour server queuing never crosses the 600-second peer-liveness timeout.
