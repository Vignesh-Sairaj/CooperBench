# Tasks

Open work for the project. Put your GitHub handle in **Owner** when you pick something up, and move it to **Done** with a link to the note or result when finished.

## Open

| Task | Owner | Details |
| :--- | :--- | :--- |
| Check `coop` and `team` at `-c 10` for throttling | | First `coop` or `team` run at `-c 10` (20 agents): check its retry count. See [Concurrency Probe](#concurrency-probe). |
| Pre-pull the `flash_10` task images | | Each teammate on their own machine: `tools/pull_images.sh flash_10`. |
| Run the four baselines on `flash_10` | | `solo`, `coop`, `coop --git`, `team` with the [reference setup](model_config.md#reference-setup). Gates which interventions we build. A first `solo` run passed 1/10; on hold until the compaction and step-budget tests settle the reference setup. |
| Review the `results/` format | | Drafted in [results_format.md](results_format.md), with [`tools/run.sh`](../tools/run.sh) and [`tools/export_results.py`](../tools/export_results.py). Everyone: comment before we export the baselines. |
| Join the Hugging Face logs archive | | Each teammate: accept the org invite, set `HF_TOKEN`, and test a download of a `setup-checks/` folder. See [logs_archive.md](logs_archive.md). |
| Decide the compaction threshold | | Agents compact every ~10 steps at the upstream 28K tokens. `includeThoughts: false` did not help; next, test a higher threshold on the same 3 pairs. See [harness_limits.md](harness_limits.md). |
| Decide how agents handle the 100-step limit | | Agents are never told about the limit, and 9 of 10 `solo` agents ran out of steps without pushing. See [Step Budget Options](#step-budget-options). |
| Team-size experiment with 3 and 4 agents (later) | | `coop` and `team` already start one agent per feature (`-f 1,2,3` runs 3 agents), and `team3_250` / `team3_all` list three-feature groups. Blocker: the grader only checks two features (the local path uses the first two features; the batch path crashes on three). Extend it to merge all patches and require every feature's tests to pass. About 10 agents fit per API key, so only 3 groups of three at a time. |
| Confirm `HIGH` thinking with the team | | The status report left the thinking setting open. Share [model_config.md](model_config.md). |

## Concurrency Probe

**Question:** What is the highest `-c` we can run without losing agents to the 120-second `docker run` timeout or slowing down on Gemini API rate limits?

**Finding so far:** The API, not the machine, sets the limit. At `-c 10` with `solo` (10 agents), the machine was nearly idle while input tokens peaked at 946K per minute against a 1M limit. Current recommendation: `-c 10`, one run at a time per key. Details in [model_config.md](model_config.md#concurrency).

**Still open:** `coop` and `team` at `-c 10` run 20 agents. If their runs log retries, drop to `-c 5` or split runs across teammates' keys, and update [model_config.md](model_config.md#concurrency) and `AGENTS.md`.

## Step Budget Options

Nothing in the prompts or the agent loop mentions the 100-step limit, so agents keep exploring until they are cut off, and work they never pushed is graded as an empty patch. Each option below changes the harness:

| Option | Effect | Downside |
| :--- | :--- | :--- |
| State the budget in the task prompt ("you have 100 steps") | Agents can plan and leave time to submit. | Small prompt change, but differs from upstream. |
| Warn near the end (for example at step 85: "15 steps left: commit, push, and open your PR") | Directly targets the "never submitted" failure. | Pass rates rise for a reason unrelated to coordination. |
| Raise the step limit (for example to 200 or 250) | Closer to real coding agents, which rarely stop at a fixed step count. | More time and cost per pair, and less comparable with upstream. |

- Any option goes behind an opt-in flag (see `AGENTS.md`) and needs team agreement.
- Whichever we pick applies to every setting we compare (`solo`, `coop`, `coop --git`, `team`).
- Test on the same 3 `solo` pairs as the compaction tests, separately from the compaction threshold change: the threshold targets wasted steps, the step budget targets never submitting.

## Done

| Task | Owner | Result |
| :--- | :--- | :--- |
| Local setup: Docker, Redis, Python env, all tests passing | | 447 tests pass. |
| First end-to-end run (one `coop --git` pair, no config file) | | Setup works; the pair failed (merge conflict). |
| Check `HIGH` thinking on one pair | | Config works (about 800 reasoning tokens per call vs. 0 without it). Pair still failed: feature 1 passed, agent2 never wrote a patch for feature 2. |
| Pick default model and thinking level | | [model_config.md](model_config.md) |
| Set up the raw logs archive | | Private Hugging Face dataset, setup-check runs uploaded. See [logs_archive.md](logs_archive.md). |
| Write the run and export tools | | [`tools/run.sh`](../tools/run.sh) launches a run with the reference setup and records `launch.json`; [`tools/export_results.py`](../tools/export_results.py) writes `results/<run_name>/`. |
