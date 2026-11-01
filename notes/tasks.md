# Tasks

Open work for the project. Put your GitHub handle in **Owner** when you pick something up, and move it to **Done** with a link to the note or result when finished.

## Open

| Task | Owner | Details |
| :--- | :--- | :--- |
| Pre-pull the `flash_10` task images | | Each teammate on their own machine: `tools/pull_images.sh flash_10`. |
| Run the four baselines on `flash_10` | | `solo` (`1/10`, `0/10` repeat) and `coop --git` (`3/10` at 100 steps, `8/10` at 250 steps) done; running `coop` (no `--git`) and `team` at 250 steps plus `coop --git` at 250 steps + 64K next. See [baseline_ablation_flash10.md](baseline_ablation_flash10.md). |
| Review the `results/` format | | Drafted in [results_format.md](results_format.md), with [`tools/run.sh`](../tools/run.sh) and [`tools/export_results.py`](../tools/export_results.py). Seven `flash_10` runs committed under `results/`. |
| Join the Hugging Face logs archive | | Each teammate: accept the org invite, set `HF_TOKEN`, and test a download of a `setup-checks/` folder. See [logs_archive.md](logs_archive.md). |
| Freeze team step-limit and compaction settings | | Wave 1 `flash_10` ablation done: static `budgetprompt` scored `0/10`, `solo` `steps250` scored `2/10`, `coop --git` `steps250` scored `8/10`, and `solo` `steps250-compact64k` scored `7/10`. Review [baseline_ablation_flash10.md](baseline_ablation_flash10.md) after Wave 2 completes. |
| Team-size experiment with 3 and 4 agents (later) | | `coop` and `team` already start one agent per feature (`-f 1,2,3` runs 3 agents), and `team3_250` / `team3_all` list three-feature groups. Blocker: the grader only checks two features (the local path uses the first two features; the batch path crashes on three). Extend it to merge all patches and require every feature's tests to pass. About 10 agents fit per API key, so only 3 groups of three at a time. |
| Confirm `HIGH` thinking with the team | | The status report left the thinking setting open. Share [model_config.md](model_config.md). |

## Concurrency Probe

**Question:** What is the highest `-c` we can run without losing agents to the 120-second `docker run` timeout or slowing down on Gemini API rate limits?

**Finding:** The 1M input-tokens-per-minute (TPM) cap per API key sets the limit (~10 concurrent agents per key at 28K compaction, ~4 at 64K). Because `coop` agents average ~80K to 82K input tok/min/agent (similar to `solo`'s ~76K), use `-c 10` (`-c 8` for zero launch-burst `429` retries) for `solo` and `-c 5` for `coop` and `team` at 28K compaction, and `-c 4` (`solo`) and `-c 2` (`coop` and `team`) at 64K. Verified across 7 `flash_10` runs (`0` agent errors); see [model_config.md](model_config.md#concurrency) and [baseline_ablation_flash10.md](baseline_ablation_flash10.md).

## Step Budget Options

Nothing in the prompts or the agent loop mentions the 100-step limit, so agents keep exploring until they are cut off, and work they never pushed is graded as an empty patch. Each option below changes the harness or agent config:

| Option | Effect | Downside |
| :--- | :--- | :--- |
| State the budget in the task prompt (`configs/variants/budgetprompt.yaml`) | Agents can plan and leave time to submit. | Small prompt change, differs from upstream. |
| Warn near the end (for example at step 85: "15 steps left: commit, push, and open your PR") | Directly targets the "never submitted" failure. | Pass rates rise for a reason unrelated to coordination. |
| Raise the step limit to 250 (`configs/variants/steps250.yaml`) | Closer to real coding agents, which rarely stop at a fixed step count. | ~2x more time and cost per pair, and less comparable with upstream. |

- Whichever we pick applies to every setting we compare (`solo`, `coop`, `coop --git`, `team`) after team agreement.

## Done

| Task | Owner | Result |
| :--- | :--- | :--- |
| Local setup: Docker, Redis, Python env, all tests passing | | 447 tests pass. |
| First end-to-end run (one `coop --git` pair, no config file) | | Setup works; the pair failed (merge conflict). |
| Check `HIGH` thinking on one pair | | Config works (about 800 reasoning tokens per call vs. 0 without it). Pair still failed: feature 1 passed, agent2 never wrote a patch for feature 2. |
| Pick default model and thinking level | | [model_config.md](model_config.md) |
| Set up the raw logs archive | | Private Hugging Face dataset, setup-check and `solo` baseline runs uploaded. See [logs_archive.md](logs_archive.md). |
| Write the run and export tools | | [`tools/run.sh`](../tools/run.sh) launches a run with `AGENT_CONFIG` / `RUN_SUFFIX` and records `launch.json`; [`tools/export_results.py`](../tools/export_results.py) writes `results/<run_name>/` including API load and retry stats. |
| Test 64K compaction threshold and model concurrency | | 64K cut compactions 1.4x to 3.5x on 3 pairs without fixing 0 submissions at 100 steps; derived per-mode `-c` table (`-c 10` `solo`, `-c 5` `coop`/`team`). See [harness_limits.md](harness_limits.md) and [model_config.md](model_config.md#concurrency). |
