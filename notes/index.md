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
| [saturation_flash.md](saturation_flash.md) | 50-pair `flash` saturation runs (`solo` vs. `coop --git` at `low` and `high`, plus `team` at `low`). |

## Coordination Interventions

| Note | What it covers |
| :--- | :--- |
| [communication_interventions.md](communication_interventions.md) | Opt-in message delivery timing, thread tracking across compactions, and speech-act intent tags: design, lineage, flags, and variant configs. |
| [communication_ablations.md](communication_ablations.md) | Communication ablation and 50-pair `flash` results across `gemini-3-flash-preview` and `gemini-3.8-flash`: what helped each model and why. |
