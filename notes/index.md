# Project Notes: Map of Contents

## Setup & Configuration Notes

| Note | Summary | Updated |
| :--- | :--- | :--- |
| [workflow.md](workflow.md) | Start here: one-time setup, then how to run a benchmark, export results, archive logs, and commit. | 2026-10-31 |
| [tasks.md](tasks.md) | Open and finished tasks with owners, including the concurrency model and step-budget tests. | 2026-10-31 |
| [model_config.md](model_config.md) | Reference setup, `HIGH` thinking, `$10` cost cap, and the input-TPM concurrency table (`-c 10` `solo`, `-c 5` `coop`/`team`). | 2026-10-31 |
| [logs_archive.md](logs_archive.md) | How to access, upload, and download raw run logs in our private Hugging Face dataset. | 2026-10-31 |
| [results_format.md](results_format.md) | Run naming, the files in `results/<run_name>/` (including `load` stats), every CSV column, and how to compare runs. | 2026-10-31 |
| [harness_limits.md](harness_limits.md) | How 28K vs. 64K compaction, the unannounced 100-step limit, and publish-only grading affect agent submissions. | 2026-10-31 |

## Coordination Intervention Notes

*(Add notes here as we design and implement the shared hook layer, structured messaging, partner-diff sync / shared blackboard, pre-submit commitment verifier, and hierarchical team evaluation.)*

## Benchmark Runs (`results/`)

| Run | Setting | Subset | Config / Variant | Pass rate | Cost | Summary |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| `solo-msa_v2-gemini-3-8-flash-flash_10` | `solo` | `flash_10` | Reference (100 steps, 28K) | 1/10 (10%) | `$8.92` | [summary.md](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) |
