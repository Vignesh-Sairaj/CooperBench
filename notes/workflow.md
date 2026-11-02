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

4. **Vertex AI and keys** in `.env` at the repo root (gitignored, never commit project IDs or keys):

   Enable the Vertex AI API on your GCP project(s) once and authenticate Application Default Credentials:

   ```bash
   gcloud services enable aiplatform.googleapis.com --project=<your-gcp-project>
   gcloud auth application-default login
   ```

   Then create `.env`:

   ```bash
   VERTEXAI_PROJECT=<your-gcp-project>
   VERTEXAI_LOCATION=global
   HF_TOKEN=hf_...          # for the raw logs archive, see logs_archive.md

   # Optional, for parallel runs across separate GCP projects (KEY_SLOT=<n> picks VERTEXAI_PROJECT_<n>):
   VERTEXAI_PROJECT_1=<project-1>
   VERTEXAI_PROJECT_2=<project-2>
   VERTEXAI_PROJECT_3=<project-3>

   # Optional, only if running AI Studio models via MODEL=gemini/...:
   # GEMINI_API_KEY=...
   # GEMINI_API_KEY_1=...
   ```

   With only `VERTEXAI_PROJECT`, runs go one at a time. Add `VERTEXAI_PROJECT_1`, `VERTEXAI_PROJECT_2`, and so on (the same `gcloud` login works across all projects your account can access) to run different experiments in parallel; see step 2 under [Run a Benchmark](#run-a-benchmark).

5. **Raw logs archive:** join the Hugging Face organization and create your token, as described in [logs_archive.md](logs_archive.md).

## Run a Benchmark

1. **Pre-pull the task images** for the subset:

   ```bash
   tools/pull_images.sh flash_10
   ```

2. **Run** with the [reference setup](model_config.md#reference-setup). First load `.env` (`set -a; source .env; set +a`). `tools/run.sh <setting> <subset> <pairs at once>` fills in the model (`vertex_ai/gemini-3.8-flash`), agent config, and backend, and names the run. On Vertex AI `global`, run 10 pairs at once (`-c 10`); if using AI Studio (`MODEL=gemini/...`), follow the per-key table in [model_config.md](model_config.md#recommended--c-per-api-key):

   ```bash
   set -a; source .env; set +a
   tools/run.sh solo flash_10 10              # solo-msa_v2-gemini-3-8-flash-flash_10
   tools/run.sh coop flash_10 10 --git        # coop-msa_v2-git-gemini-3-8-flash-flash_10
   ```

   To try different budgets, pass a variant config and a name suffix, for example `RUN_SUFFIX=steps250-compact64k AGENT_CONFIG=configs/variants/steps250_compact64k.yaml tools/run.sh solo flash_10 10`. To use another model, set `MODEL`, for example `MODEL=vertex_ai/gemini-3-flash-preview AGENT_CONFIG=configs/variants/thinking_minimal.yaml RUN_SUFFIX=minimal tools/run.sh solo flash_10 10`.

   Run one benchmark at a time per GCP project (see [Concurrency](model_config.md#concurrency)). Grading runs automatically at the end.

   To run different experiments in parallel, give each run its own project slot with `KEY_SLOT` (each in its own terminal, after `set -a; source .env; set +a`). Each parallel run needs a distinct run name:

   ```bash
   KEY_SLOT=1 tools/run.sh solo flash_10 10
   KEY_SLOT=2 tools/run.sh team flash_10 10
   KEY_SLOT=3 RUN_SUFFIX=steps250 AGENT_CONFIG=configs/variants/steps250.yaml tools/run.sh coop flash_10 10 --git
   ```

   `launch.json` and `run.json` record only the slot number, never project IDs or API keys. `resources.log` counts every container on the machine, including other parallel runs.

   To spread one large subset (for example the 50-pair `flash`) over several keys, split it into shards, run one shard per key, and merge them afterwards into a single run ([`tools/shards.py`](../tools/shards.py)):

   ```bash
   uv run --frozen python tools/shards.py split flash 3     # writes logs/_shards/flash-shard{1,2,3}of3
   KEY_SLOT=2 tools/run.sh solo flash-shard1of3 4 --dataset-dir logs/_shards/flash-shard1of3
   KEY_SLOT=3 tools/run.sh solo flash-shard2of3 4 --dataset-dir logs/_shards/flash-shard2of3
   KEY_SLOT=4 tools/run.sh solo flash-shard3of3 4 --dataset-dir logs/_shards/flash-shard3of3
   uv run --frozen python tools/shards.py merge solo-msa_v2-gemini-3-8-flash-flash-shard{1,2,3}of3
   ```

   The merged run is named without the shard part (here `solo-msa_v2-gemini-3-8-flash-flash`); export and archive it like any other run. Use the same `RUN_SUFFIX` and `AGENT_CONFIG` for every shard.

3. **Watch it** (optional): `tail -f logs/<run_name>/console.log`, and `logs/<run_name>/resources.log` for load, memory, and container count.

4. **Check for throttling:** `tools/run.sh` prints how many model calls were retried because of the Gemini rate limit (`429`) or a busy server (`5xx`). A few retries only slow agents down. Dozens of retries in `coop` or `team` can change results, because a slowed agent can make its partner give up waiting; next time run fewer pairs at once or use a key from another GCP project.

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
