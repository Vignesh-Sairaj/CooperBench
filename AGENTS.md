# Agent Instructions

## Upstream Hygiene

- Keep the upstream `63b9d44` harness code on `main` unchanged by default. Add each new coordination intervention behind an opt-in flag (for example `--verifier`) that is off by default, so runs without the flag match our reference setup.
- Do not edit upstream files (`README.md`, `CHANGELOG.md`, `CLAUDE.md`, `docs/`) so upstream merges stay conflict-free.
- Never commit `.env`, API keys, or scratch scripts. Use `uv run --frozen` so `uv.lock` is never rewritten.

## Notes and Results

- Start each task by reading [`notes/index.md`](notes/index.md).
- Write decisions, setup findings, and experiment writeups to `notes/` as short, scannable Markdown.
- Write notes and run summaries for teammates with no prior context. Use plain language, define terms where they are used, and avoid our own shorthand. Experiment notes cover what was run, why, the results, and the conclusions; keep implementation details (function names, flags, config files) in the setup notes. Every `results/<run_name>/summary.md` needs a plain-language **Experiment** section (what the run tests and why) and **Observations**.
- Raw trajectories stay in `logs/` (gitignored). Export run summaries to `results/<run_name>/`, and upload the raw logs as described in [`notes/logs_archive.md`](notes/logs_archive.md).
- Update [`notes/index.md`](notes/index.md) whenever you add, rename, or remove a note in `notes/`, and add a row to [`notes/runs.md`](notes/runs.md) for every run exported to `results/`.

## Running Benchmarks

- **Always use the reference settings** in [`notes/model_config.md`](notes/model_config.md#reference-setup) (frozen 2026-11-02): `gemini-3.8-flash` on Vertex AI (`global`), `medium` thinking, 500 steps per agent, compaction at 128K tokens, the per-turn step counter, and a `$40` per-agent cost cap. They live in `configs/reference/medium.yaml`, which `tools/run.sh` uses by default.
- **Never edit `configs/reference/`.** For thinking sweeps, use `configs/reference/low.yaml` (or `high.yaml`) with `RUN_SUFFIX=ref-low`. For an intervention, copy `configs/reference/medium.yaml` into `configs/variants/`, add only the new flag, and run with `AGENT_CONFIG=<that file> RUN_SUFFIX=<name>`.
- **Concurrency per Vertex AI project:** `solo` `-c 8`; `coop`, `coop --git`, and `team` `-c 4`, at any hour. Run more experiments in parallel on separate projects (`KEY_SLOT`) instead of raising `-c`. Check retry counts after each run.
- Pre-pull task Docker images before runs (the container start timeout is 120 seconds). Follow [`notes/workflow.md`](notes/workflow.md) for the full sequence from pre-pulling images to committing results.

## Before Pushing

Run the CI checks listed in `CLAUDE.md` (with `uv run --frozen`) and confirm `git diff uv.lock` is empty.
