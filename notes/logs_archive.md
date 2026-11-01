# Raw Logs Archive (Hugging Face)

Raw run logs (`logs/<run_name>/`: trajectories, patches, messages, eval output) are gitignored, but we need them later for failure analysis. We keep them in a private Hugging Face dataset owned by a free team organization. Free organizations get 100 GB of private storage; a pair run with `HIGH` thinking is about 15 MB.

## One-Time Setup

1. Create a Hugging Face account with a personal or university email, and accept the invite to our organization (ask in the team chat).
2. At huggingface.co/settings/tokens, create a **Fine-grained** token with write access to the organization's repos.
3. Add two lines to your local `.env` (gitignored). The dataset name is in the team chat.

```bash
HF_TOKEN=hf_...
HF_LOGS_REPO=<org>/<dataset>
```

## Upload a Run

After a run finishes, upload its whole log folder under the same name:

```bash
set -a; source .env; set +a
uv run --frozen hf upload "$HF_LOGS_REPO" logs/<run_name> <run_name> --repo-type dataset
```

## Download a Run

```bash
set -a; source .env; set +a
uv run --frozen hf download "$HF_LOGS_REPO" --repo-type dataset --include "<run_name>/*" --local-dir logs/
```

## Layout

- `<run_name>/`: one folder per benchmark run, named exactly like the run (and like `results/<run_name>/`).
- `setup-checks/`: single-pair runs from setting up the environment. Not used in results.
