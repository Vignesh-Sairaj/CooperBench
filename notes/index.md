# Project Notes: Map of Contents

## Setup & Configuration Notes

| Note | Summary | Updated |
| :--- | :--- | :--- |
| [workflow.md](workflow.md) | Start here: one-time setup, then how to run a benchmark (including parallel runs on separate GCP project keys with `KEY_SLOT`), export results, archive logs, and commit. | 2026-11-01 |
| [tasks.md](tasks.md) | Open and finished tasks with owners, including the concurrency model and step-budget tests. | 2026-10-31 |
| [model_config.md](model_config.md) | Reference setup, `HIGH` thinking, `$10` cost cap, and the input-TPM concurrency table (`-c 8` `solo`, `-c 4` `coop`/`team` at 28K). | 2026-11-01 |
| [logs_archive.md](logs_archive.md) | How to access, upload, and download raw run logs in our private Hugging Face dataset. | 2026-10-31 |
| [results_format.md](results_format.md) | Run naming, the files in `results/<run_name>/` (including `load` stats), every CSV column, and how to compare runs. | 2026-10-31 |
| [harness_limits.md](harness_limits.md) | How 28K vs. 64K compaction, step limits, publish-only grading, and upstream timeout/clock bugs affect runs. | 2026-11-01 |
| [baseline_ablation_flash10.md](baseline_ablation_flash10.md) | Wave 1 `flash_10` step-budget and compaction results (`0%`-`10%` to `70%` `solo`, `30%` to `80%` `coop --git`) and Wave 2 queue. | 2026-11-01 |

## Coordination Intervention Notes

*(Add notes here as we design and implement the shared hook layer, structured messaging, partner-diff sync / shared blackboard, pre-submit commitment verifier, and hierarchical team evaluation.)*

## Benchmark Runs (`results/`)

How to read this table:

- **Setting:** `solo` is one agent implementing both features. `coop` is two agents, one feature each, who can message each other. `coop --git` adds a shared git remote where they can push and pull each other's branches. `team` is a lead plus a member with a shared task list.
- **Subset:** `flash_10` is 10 hand-picked feature pairs (one per task, 9 repos), used for cheap screening.
- **Step limit:** the maximum number of model responses per agent. The agent is then stopped, and only work it pushed counts. Upstream default: 100.
- **Compaction:** once a request reaches this many tokens, the harness replaces older turns with a model-written summary and keeps only the last 2 turns verbatim. Upstream default: 28K.
- **Passed:** both features' hidden tests pass (in `coop`, after merging the two agents' patches).
- Every run uses `gemini-3.8-flash` with `HIGH` thinking and a `$10` per-agent cost cap ([model_config.md](model_config.md)). With 10 pairs, a difference of 1 to 2 pairs is within run-to-run variation ([baseline_ablation_flash10.md](baseline_ablation_flash10.md)).

| Run (summary) | Setting | Step limit | Compaction | Other change | Question it answers | Passed | Cost |
| :--- | :--- | :---: | :---: | :--- | :--- | :---: | ---: |
| [`solo-...-flash_10`](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) | `solo` | 100 | 28K | None | Baseline with upstream budgets | 1/10 | `$8.92` |
| [`solo-...-flash_10-r2`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-r2/summary.md) | `solo` | 100 | 28K | None (repeat) | How much does the same setup vary? | 0/10 | `$8.99` |
| [`solo-...-flash_10-budgetprompt`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt/summary.md) | `solo` | 100 | 28K | Task prompt states the step limit | Does telling the agent the limit help? | 0/10 | `$8.41` |
| [`solo-...-flash_10-steps250`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `solo` | 250 | 28K | None | Do agents finish with more steps? | 2/10 | `$18.75` |
| [`solo-...-flash_10-steps250-compact64k`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `solo` | 250 | 64K | None | Does one agent need more context for two features? | 7/10 | `$19.63` |
| [`coop-...-git-...-flash_10`](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10/summary.md) | `coop --git` | 100 | 28K | None | Baseline with upstream budgets | 3/10 | `$11.93` |
| [`coop-...-git-...-flash_10-steps250`](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop --git` | 250 | 28K | None | Do agents finish with more steps? | 8/10 | `$19.87` |
| [`coop-...-flash_10-steps250`](../results/coop-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop` | 250 | 28K | No shared git | Does the shared git remote matter? | 8/10 | `$23.05` |

Full run names follow `<setting>-msa_v2-[git-]gemini-3-8-flash-<subset>[-<variant>]` ([results_format.md](results_format.md)).
