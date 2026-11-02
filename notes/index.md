# Project Notes

A map of the notes in this folder.

## Setup and Running

| Note | What it covers |
| :--- | :--- |
| [workflow.md](workflow.md) | Start here: setup, running a benchmark (including parallel runs), exporting and archiving results. |
| [model_config.md](model_config.md) | The model setup every run uses, and how many agents to run per API key. |
| [harness_limits.md](harness_limits.md) | How the harness's step limit, compaction, and grading differ from real coding agents, and harness bugs we hit. |
| [logs_archive.md](logs_archive.md) | Where raw run logs are stored and how to upload or download them. |
| [results_format.md](results_format.md) | Run naming and the files in `results/<run_name>/`. |
| [tasks.md](tasks.md) | Open and finished tasks. |

## Experiments and Results

| Note | What it covers |
| :--- | :--- |
| [runs.md](runs.md) | Every benchmark run: settings, the question it answers, result, and a link to its summary. |
| [baseline_ablation_flash10.md](baseline_ablation_flash10.md) | Step limit and compaction experiments on `flash_10`: why we ran them and what we concluded. |
| [model_thinking_stepcounter_flash10.md](model_thinking_stepcounter_flash10.md) | Two Gemini models at different thinking levels, the per-turn step counter, and the `team` baseline on `flash_10`. |
| [saturation_flash.md](saturation_flash.md) | 50-pair `flash` saturation runs (`solo` `low` vs. `high`, and `solo` vs. `coop --git` with ample budget). |

## Coordination Interventions

*(Add notes here as we design and implement the shared hook layer, structured messaging, partner-diff sync / shared blackboard, pre-submit commitment verifier, and hierarchical team evaluation.)*
