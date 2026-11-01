# Workflow

How to go from a fresh clone to a committed benchmark result. Details live in the linked notes.

## One-Time Setup

1. **Docker:** install Docker and make sure you can run `docker ps` without `sudo` (add yourself to the `docker` group, then log in again).
2. **Redis** (agents send messages through it):

   ```bash
   docker run -d --name cooperbench-redis --restart unless-stopped -p 6379:6379 redis:7
   ```

3. **Python environment** (needs [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync --frozen --extra dev
   ```

4. **Keys** in `.env` at the repo root (gitignored, never commit it):

   ```bash
   GEMINI_API_KEY=...   # AI Studio key for gemini/gemini-3.8-flash
   HF_TOKEN=hf_...      # for the raw logs archive, see logs_archive.md

   # Optional, for parallel runs (KEY_SLOT=<n> picks GEMINI_API_KEY_<n>).
   # Use one key per GCP project: rate limits apply per project, not per key.
   GEMINI_API_KEY_1=... # project 1 (can be the same key as GEMINI_API_KEY)
   GEMINI_API_KEY_2=... # project 2
   GEMINI_API_KEY_3=... # project 3
   ```

   With only `GEMINI_API_KEY`, runs go one at a time. Add `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, and so on (one per GCP project) to run different experiments in parallel; see step 2 under [Run a Benchmark](#run-a-benchmark).

5. **Raw logs archive:** join the Hugging Face organization and create your token, as described in [logs_archive.md](logs_archive.md).

## Run a Benchmark

1. **Pre-pull the task images** for the subset:

   ```bash
   tools/pull_images.sh flash_10
   ```

2. **Run** with the [reference setup](model_config.md#reference-setup). `tools/run.sh` fills in the model, agent config, and backend, and names the run:

   ```bash
   tools/run.sh solo flash_10 8               # solo-msa_v2-gemini-3-8-flash-flash_10
   tools/run.sh coop flash_10 4 --git         # coop-msa_v2-git-gemini-3-8-flash-flash_10
   RUN_SUFFIX=verifier tools/run.sh coop flash_10 4 --git --verifier    # intervention arm (--verifier is a future flag)
   ```

   Run one benchmark at a time per GCP project key (see [Concurrency](model_config.md#concurrency)). A run over `flash_10` takes one to two hours. Grading runs automatically at the end.

   To run different experiments in parallel, give each run its own key with `KEY_SLOT` (each in its own terminal, after `set -a; source .env; set +a`). Each parallel run needs a distinct run name:

   ```bash
   KEY_SLOT=1 tools/run.sh solo flash_10 8
   KEY_SLOT=2 tools/run.sh team flash_10 4
   KEY_SLOT=3 RUN_SUFFIX=steps250 AGENT_CONFIG=configs/variants/steps250.yaml tools/run.sh coop flash_10 4 --git
   ```

   `launch.json` and `run.json` record the slot number (never the key). `resources.log` counts every container on the machine, including other parallel runs.

3. **Watch it** (optional): `tail -f logs/<run_name>/console.log`, and `logs/<run_name>/resources.log` for load, memory, and container count.

4. **Check for throttling:** `tools/run.sh` prints the model retry count at the end. If it is not zero, the Gemini rate limit slowed the agents; rerun at a lower `-c` or on a key from another GCP project before using the results.

Rerunning with the same name skips pairs that already have results; add `--force` to `tools/run.sh` to redo them. To redo only the grading: `uv run --frozen cooperbench eval -n <run_name> --backend docker --force`.

## Record the Results

1. **Export** the run into `results/` (see [results_format.md](results_format.md)):

   ```bash
   uv run --frozen python tools/export_results.py <run_name>
   ```

2. **Describe the run:** in `results/<run_name>/summary.md`, fill in the two hand-written sections. Re-exporting keeps both.
   - **Experiment:** what the run tests, how it differs from other runs, and why we ran it, in plain words for a teammate with no context.
   - **Observations:** a few bullets on what we saw in the traces. Avoid internal field names and flags; say what happened.
3. **Archive the raw logs** on Hugging Face (see [logs_archive.md](logs_archive.md)):

   ```bash
   set -a; source .env; set +a
   uv run --frozen hf upload agent-coordination-lab/cooperbench-run-logs \
     logs/<run_name> <run_name> --repo-type dataset
   ```

4. **Index it:** add a row for the run in [runs.md](runs.md).
5. **Commit and push** `results/<run_name>/` and `notes/runs.md`, after the checks in `AGENTS.md`.
