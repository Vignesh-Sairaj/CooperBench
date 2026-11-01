# Tasks

Open work for the project. Put your GitHub handle in **Owner** when you pick something up, and move it to **Done** with a link to the note or result when finished.

## Open

| Task | Owner | Details |
| :--- | :--- | :--- |
| Find the best concurrency (`-c`) for our machines | | See [Concurrency probe](#concurrency-probe) below. |
| Pre-pull the `flash_10` task images | | Done locally; each teammate needs to pull them on their own machine. |
| Run the four baselines on `flash_10` | | `solo`, `coop`, `coop --git`, `team` with the [default config](model_config.md). Gates which interventions we build. |
| Script to export runs into `results/` | | Turn `logs/<run>/` (`result.json`, `eval.json`) into `results/<run>/metrics.json` and a `summary.md` stub. |
| Join the Hugging Face logs archive | | Each teammate: accept the org invite, set `HF_TOKEN`, and test a download of a `setup-checks/` folder. See [logs_archive.md](logs_archive.md). |
| Confirm `HIGH` thinking with the team | | The status report left the thinking setting open. Share [model_config.md](model_config.md). |

## Concurrency Probe

**Question:** What is the highest `-c` we can run without losing agents to the 120-second `docker run` timeout or slowing down on Gemini API rate limits?

**Why it matters:** Upstream picked `-c 3` after `-c 10` killed agents at container startup (`docs/BENCHMARK_RESULTS.md`), but their images were not pre-pulled. Our machines have 128 cores and 236 GB RAM, and our API key has no quota cap, only rate limits. A higher `-c` could cut a 50-pair run from hours to minutes.

**Plan:**

1. Pre-pull the `flash_10` images, so only container start counts against the 120-second timeout.
2. Run `flash_10` in `coop --git` at `-c 3`, `5`, and `10` (6, 10, and 20 agent containers at once).
3. For each level, record wall time, container start failures, rate-limit (HTTP 429) retries in the logs, and peak CPU and memory.
4. Pick the highest `-c` with zero start failures and few rate-limit retries. Write it into [model_config.md](model_config.md) and update the concurrency line in `AGENTS.md`.

**Note:** The harness retries rate-limited calls instead of failing, so hitting the limit shows up as longer runs, not errors. Compare wall time per pair across levels, not just pass rate.

## Done

| Task | Owner | Result |
| :--- | :--- | :--- |
| Local setup: Docker, Redis, Python env, all tests passing | | 447 tests pass. |
| First end-to-end run (one `coop --git` pair, no config file) | | Setup works; the pair failed (merge conflict). |
| Check `HIGH` thinking on one pair | | Config works (about 800 reasoning tokens per call vs. 0 without it). Pair still failed: feature 1 passed, agent2 never wrote a patch for feature 2. |
| Pick default model and thinking level | | [model_config.md](model_config.md) |
| Set up the raw logs archive | | Private Hugging Face dataset, setup-check runs uploaded. See [logs_archive.md](logs_archive.md). |
