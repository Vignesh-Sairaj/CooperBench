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

- Run every benchmark with the [reference setup](notes/model_config.md#reference-setup) (use `tools/run.sh`), identical across every run in a comparison. Follow [`notes/workflow.md`](notes/workflow.md) for the full sequence from pre-pulling images to committing results.
- Pre-pull task Docker images before runs (the container start timeout is 120 seconds). Use ~8 concurrent agents per Gemini API key (`-c 8` for `solo`, `-c 4` for `coop` and `team` at 28K compaction), one run at a time per GCP project key (run separate experiments in parallel on keys from separate projects with `KEY_SLOT`, see [`notes/workflow.md`](notes/workflow.md)), and check the retry counts after each run (see [`notes/model_config.md`](notes/model_config.md#concurrency)).

## Before Pushing

Run the CI checks listed in `CLAUDE.md` (with `uv run --frozen`) and confirm `git diff uv.lock` is empty.
