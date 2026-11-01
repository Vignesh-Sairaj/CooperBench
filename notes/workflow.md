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
   ```

5. **Raw logs archive:** join the Hugging Face organization and create your token, as described in [logs_archive.md](logs_archive.md).

## Run a Benchmark

1. **Pre-pull the task images** for the subset:

   ```bash
   tools/pull_images.sh flash_10
   ```

2. **Run** with the [reference setup](model_config.md#reference-setup). `tools/run.sh` fills in the model, agent config, and backend, and names the run:

   ```bash
   tools/run.sh solo flash_10 10              # solo-msa_v2-gemini-3-8-flash-flash_10
   tools/run.sh coop flash_10 10 --git        # coop-msa_v2-git-gemini-3-8-flash-flash_10
   RUN_SUFFIX=verifier tools/run.sh coop flash_10 10 --git --verifier   # intervention arm (--verifier is a future flag)
   ```

   Run one benchmark at a time per API key (see [Concurrency](model_config.md#concurrency)). A run over `flash_10` takes about an hour. Grading runs automatically at the end.

3. **Watch it** (optional): `tail -f logs/<run_name>/console.log`, and `logs/<run_name>/resources.log` for load, memory, and container count.

4. **Check for throttling:** `tools/run.sh` prints the model retry count at the end. If it is not zero, the Gemini rate limit slowed the agents; rerun at a lower `-c` or on another teammate's key before using the results.

Rerunning with the same name skips pairs that already have results; add `--force` to `tools/run.sh` to redo them. To redo only the grading: `uv run --frozen cooperbench eval -n <run_name> --backend docker --force`.

## Record the Results

1. **Export** the run into `results/` (see [results_format.md](results_format.md)):

   ```bash
   uv run --frozen python tools/export_results.py <run_name>
   ```

2. **Write observations:** add a few lines under **Observations** in `results/<run_name>/summary.md`. Re-exporting keeps that section.
3. **Archive the raw logs** on Hugging Face (see [logs_archive.md](logs_archive.md)):

   ```bash
   set -a; source .env; set +a
   uv run --frozen hf upload agent-coordination-lab/cooperbench-run-logs \
     logs/<run_name> <run_name> --repo-type dataset
   ```

4. **Index it:** add a row for the run under **Benchmark Runs** in [index.md](index.md).
5. **Commit and push** `results/<run_name>/` and `notes/index.md`, after the checks in `AGENTS.md`.
