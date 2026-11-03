# Agent Instructions

## Upstream Hygiene

- Keep the upstream harness code (`63b9d44`) unchanged by default. Put every new behavior, including coordination interventions, behind an opt-in config flag that is off by default, so runs without it behave exactly as before.
- Don't edit upstream files (`README.md`, `CHANGELOG.md`, `CLAUDE.md`, `docs/`), so upstream merges stay conflict-free.
- This repository is public. Never commit `.env`, API keys, project IDs, internal URLs, personal names, or scratch scripts.
- Run commands with `uv run --frozen` (and install with `uv sync --frozen`), which use `uv.lock` exactly as committed. Change `uv.lock` only on purpose, with `uv lock` or `uv add` as part of a dependency change.

## Notes and Results

- Start each task by reading [`notes/index.md`](notes/index.md), and update it whenever you add, rename, or remove a note.
- Write decisions, setup findings, and experiment writeups to `notes/` as short, scannable Markdown for teammates with no prior context: plain language, terms defined where they are used, no private shorthand.
- Experiment notes cover what was run, why, the results, and the conclusions, without implementation details.
- [`notes/model_config.md`](notes/model_config.md) holds only the frozen reference settings and how to run them. Keep it short: put evidence in the experiment notes and harness quirks in [`notes/harness_limits.md`](notes/harness_limits.md), and don't add sections to it.
- Keep raw trajectories in `logs/` (gitignored) and upload them as described in [`notes/logs_archive.md`](notes/logs_archive.md). Export each run to `results/<run_name>/`, give its `summary.md` plain-language **Experiment** and **Observations** sections, and add a row to [`notes/runs.md`](notes/runs.md).

## Running Benchmarks

- **Always use the reference settings** in [`notes/model_config.md`](notes/model_config.md#reference-setup) (frozen 2026-11-02): `gemini-3.8-flash` on Vertex AI (`global`), `medium` thinking, 500 steps per agent, compaction at 128K tokens, the per-turn step counter, and a `$40` per-agent cost cap. They live in `configs/reference/medium.yaml`, which `tools/run.sh` uses by default.
- **Never edit `configs/reference/`.** For thinking sweeps, use `configs/reference/low.yaml` or `high.yaml` with `RUN_SUFFIX=ref-low` or `ref-high`. For an intervention, copy `configs/reference/medium.yaml` into `configs/variants/`, add only the new flag, run with `AGENT_CONFIG=<that file> RUN_SUFFIX=<name>`, and compare it with a reference run on the same subset, provider, and concurrency.
- **Concurrency per Vertex AI project** (`-c` is pairs at once): `solo` `-c 8`; `coop`, `coop --git`, and `team` `-c 4`, at any hour. To go faster, run more experiments in parallel on separate projects (`KEY_SLOT`) instead of raising `-c`. Check retry counts after each run ([`notes/concurrency.md`](notes/concurrency.md)).
- Pre-pull task Docker images first (containers must start within 120 seconds). [`notes/workflow.md`](notes/workflow.md) has the full sequence from pre-pulling images to committing results.

## Before Pushing

Run the CI checks listed in `CLAUDE.md`, adding `--frozen` to each `uv run`, and confirm `git diff uv.lock` is empty.
