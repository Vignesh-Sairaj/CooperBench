# Project Notes: Map of Contents

## Setup & Configuration Notes

| Note | Summary | Updated |
| :--- | :--- | :--- |
| [workflow.md](workflow.md) | Start here: one-time setup, then how to run a benchmark, export results, archive logs, and commit. | 2026-10-31 |
| [tasks.md](tasks.md) | Open and finished tasks with owners, including the concurrency model and step-budget tests. | 2026-10-31 |
| [model_config.md](model_config.md) | Reference setup, `HIGH` thinking, `$10` cost cap, and the input-TPM concurrency table (`-c 10` `solo`, `-c 5` `coop`/`team`). | 2026-10-31 |
| [logs_archive.md](logs_archive.md) | How to access, upload, and download raw run logs in our private Hugging Face dataset. | 2026-10-31 |
| [results_format.md](results_format.md) | Run naming, the files in `results/<run_name>/` (including `load` stats), every CSV column, and how to compare runs. | 2026-10-31 |
| [harness_limits.md](harness_limits.md) | How 28K vs. 64K compaction, step limits, publish-only grading, and upstream timeout/clock bugs affect runs. | 2026-11-01 |
| [baseline_ablation_flash10.md](baseline_ablation_flash10.md) | Wave 1 `flash_10` step-budget and compaction results (`0%`-`10%` to `70%` `solo`, `30%` to `80%` `coop --git`) and Wave 2 queue. | 2026-11-01 |

## Coordination Intervention Notes

*(Add notes here as we design and implement the shared hook layer, structured messaging, partner-diff sync / shared blackboard, pre-submit commitment verifier, and hierarchical team evaluation.)*

## Benchmark Runs (`results/`)

| Run | Setting | Subset | Config / Variant | Pass rate | Cost | Summary |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| `solo-msa_v2-gemini-3-8-flash-flash_10` | `solo` | `flash_10` | Reference (100 steps, 28K) | 1/10 (10%) | `$8.92` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) |
| `solo-msa_v2-gemini-3-8-flash-flash_10-r2` | `solo` | `flash_10` | Reference repeat (100 steps, 28K) | 0/10 (0%) | `$8.99` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10-r2/summary.md) |
| `solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt` | `solo` | `flash_10` | Static 100-step prompt notice, 28K | 0/10 (0%) | `$8.41` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt/summary.md) |
| `solo-msa_v2-gemini-3-8-flash-flash_10-steps250` | `solo` | `flash_10` | 250 steps, 28K | 2/10 (20%) | `$18.75` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) |
| `solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k` | `solo` | `flash_10` | 250 steps, 64K compaction | 7/10 (70%) | `$19.63` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) |
| `coop-msa_v2-git-gemini-3-8-flash-flash_10` | `coop --git` | `flash_10` | Reference (100 steps, 28K) | 3/10 (30%) | `$11.93` | [summary.md](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10/summary.md) |
| `coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250` | `coop --git` | `flash_10` | 250 steps, 28K | 8/10 (80%) | `$19.87` | [summary.md](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250/summary.md) |
