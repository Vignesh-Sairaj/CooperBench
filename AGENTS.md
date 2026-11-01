# Agent Instructions

## Upstream Hygiene

- `main` must keep reproducing the upstream `63b9d44` baselines. Add each new coordination intervention behind an opt-in flag (for example `--verifier`) that is off by default, so runs without the flag behave exactly like upstream.
- Do not edit upstream files (`README.md`, `CHANGELOG.md`, `CLAUDE.md`, `docs/`) so upstream merges stay conflict-free.
- Never commit `.env`, API keys, or scratch scripts. Use `uv run --frozen` so `uv.lock` is never rewritten.

## Notes and Results

- Start each task by reading [`notes/index.md`](notes/index.md).
- Write decisions, setup findings, and experiment writeups to `notes/` as short, scannable Markdown.
- Raw trajectories stay in `logs/` (gitignored). Export run summaries (`summary.md`, `metrics.json`) to `results/<run_name>/`, and upload the raw logs as described in [`notes/logs_archive.md`](notes/logs_archive.md).
- Update [`notes/index.md`](notes/index.md) whenever you add or change a file in `notes/` or `results/`.

## Running Benchmarks

- Use the defaults in [`notes/model_config.md`](notes/model_config.md), identical across every run in a comparison.
- Pre-pull task Docker images before runs (the container start timeout is 120 seconds). Start at `-c 3` and raise it only after checking the Gemini rate limits (see [`notes/tasks.md`](notes/tasks.md)).

## Before Pushing

Run the CI checks listed in `CLAUDE.md` (with `uv run --frozen`) and confirm `git diff uv.lock` is empty.
