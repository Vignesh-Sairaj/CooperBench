# Project Notes: Map of Contents

## Setup & Configuration Notes

| Note | Summary | Updated |
| :--- | :--- | :--- |
| [workflow.md](workflow.md) | Start here: one-time setup, then how to run a benchmark, export results, archive logs, and commit. | 2026-10-31 |
| [tasks.md](tasks.md) | Open and finished tasks with owners, including the concurrency probe. | 2026-10-31 |
| [model_config.md](model_config.md) | Default harness, model, `HIGH` thinking, `$10` cost cap, and why every run needs the config file. | 2026-10-31 |
| [logs_archive.md](logs_archive.md) | How to access, upload, and download raw run logs in our private Hugging Face dataset. | 2026-10-31 |
| [results_format.md](results_format.md) | Run naming, the files in `results/<run_name>/`, every CSV column, and how to compare runs. | 2026-10-31 |
| [harness_limits.md](harness_limits.md) | How the harness's 28K compaction, 100-step limit, and bash-only tools differ from real coding agents, and the trade-offs of raising them. | 2026-10-31 |

## Coordination Intervention Notes

*(Add notes here as we design and implement the shared hook layer, structured messaging, partner-diff sync / shared blackboard, pre-submit commitment verifier, and hierarchical team evaluation.)*

## Benchmark Runs (`results/`)

*(Export completed runs to `results/<run_name>/` and link each run in a row here.)*
