# Tasks

Open work for the project. Put your GitHub handle in **Owner** when you pick something up, and move it to **Done** with a link to the note or result when finished.

## Open

| Task | Owner | Details |
| :--- | :--- | :--- |
| Pre-pull the `flash_10` task images | | Each teammate on their own machine: `tools/pull_images.sh flash_10`. |
| Finish the four baseline settings on `flash_10` | | `solo`, `coop`, and `coop --git` are done ([runs.md](runs.md)). `team` with 250 steps is running. |
| Decide the step limit and compaction for all experiments | | Proposed: 250 steps and 64K compaction for every setting, because upstream's 100 steps and 28K stop most agents before they submit. See [baseline_ablation_flash10.md](baseline_ablation_flash10.md). Needs team agreement. |
| Test a visible step counter | | Implemented as an opt-in agent flag that adds "Step n of N: k left" to every turn (`configs/variants/stepcounter.yaml`). Next: run `solo` at 100 steps with it and compare with 0/10 for the limit stated only in the task prompt. |
| Repeat the key comparisons on more pairs | | `solo` vs. `coop` is a tie on 10 pairs. Rerun the best settings on the 50-pair `flash` subset before drawing conclusions. |
| Review the `results/` format | | See [results_format.md](results_format.md), [`tools/run.sh`](../tools/run.sh), and [`tools/export_results.py`](../tools/export_results.py). Nine `flash_10` runs are under `results/`. |
| Join the Hugging Face logs archive | | Each teammate: accept the org invite, set `HF_TOKEN`, and test a download of a `setup-checks/` folder. See [logs_archive.md](logs_archive.md). |
| Team-size experiment with 3 and 4 agents (later) | | `coop` and `team` already start one agent per feature (`-f 1,2,3` runs 3 agents), and `team3_250` / `team3_all` list three-feature groups. Blocker: the grader only checks two features (the local path uses the first two; the batch path crashes on three). Extend it to merge all patches and require every feature's tests to pass. |
| Confirm `HIGH` thinking with the team | | Our status report left the thinking setting open. Share [model_config.md](model_config.md). |

## Done

| Task | Owner | Result |
| :--- | :--- | :--- |
| Local setup: Docker, Redis, Python env, all tests passing | | 447 tests pass. |
| First end-to-end run (one `coop --git` pair, no config file) | | Setup works; the pair failed (merge conflict). |
| Check `HIGH` thinking on one pair | | Config works (about 800 reasoning tokens per call vs. 0 without it). Pair still failed: feature 1 passed, agent2 never wrote a patch for feature 2. |
| Pick default model and thinking level | | [model_config.md](model_config.md) |
| Set up the raw logs archive | | Private Hugging Face dataset with every run's logs. See [logs_archive.md](logs_archive.md). |
| Write the run and export tools | | [`tools/run.sh`](../tools/run.sh) starts a run and records how it was launched; [`tools/export_results.py`](../tools/export_results.py) writes `results/<run_name>/`. |
| Find how many agents fit per API key | | The 1M input-tokens-per-minute limit per GCP project sets the limit, not the machine: about 8 agents per key at 28K compaction, 4 at 64K. See [model_config.md](model_config.md#concurrency). |
| Step limit and compaction experiments on `flash_10` | | 9 runs across `solo`, `coop`, and `coop --git`. See [baseline_ablation_flash10.md](baseline_ablation_flash10.md). |
| Run experiments in parallel on several API keys | | `KEY_SLOT` in `tools/run.sh`. See [workflow.md](workflow.md). |
