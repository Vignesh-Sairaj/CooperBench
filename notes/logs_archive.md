# Raw Logs Archive (Hugging Face)

Raw run logs (`logs/<run_name>/`: trajectories, patches, messages, eval output) are gitignored, but we need them later for failure analysis. We keep them in the private Hugging Face dataset [`agent-coordination-lab/cooperbench-run-logs`](https://huggingface.co/datasets/agent-coordination-lab/cooperbench-run-logs), owned by our free organization `agent-coordination-lab`. Free organizations get 100 GB of private storage; a pair run with `HIGH` thinking is about 15 MB.

## One-Time Setup

1. Create a Hugging Face account with a personal or university email, and ask a teammate to invite you to `agent-coordination-lab` with the write role.
2. At huggingface.co/settings/tokens, create a **Fine-grained** token with write access to the organization's repos.
3. Add the token to your local `.env` (gitignored):

```bash
HF_TOKEN=hf_...
```

## Upload a Run

After a run finishes, upload its whole log folder under the same name:

```bash
set -a; source .env; set +a
uv run --frozen hf upload agent-coordination-lab/cooperbench-run-logs logs/<run_name> <run_name> --repo-type dataset
```

## Download a Run

```bash
set -a; source .env; set +a
uv run --frozen hf download agent-coordination-lab/cooperbench-run-logs --repo-type dataset --include "<run_name>/*" --local-dir logs/
```

## Layout

- `<run_name>/`: one folder per benchmark run, named exactly like the run (and like `results/<run_name>/`). Each run's `summary.md` links to its folder under **Run Details**.
- `setup-checks/`: single-pair runs from setting up the environment. Not used in results.

Inside a run folder, each pair has its own folder. The path is built from the four pair columns in `pairs.csv` and `agents.csv`:

```text
<run_name>/<setting>/<repo>/<task_id>/f<feature_a>_f<feature_b>/
```

For example, `pallets_jinja_task,1559,4,8` in a `coop` run is `<run_name>/coop/pallets_jinja_task/1559/f4_f8/`. Each pair folder holds:

| File | Contents |
| :--- | :--- |
| `result.json` | How each agent ended (status, steps, cost, patch size). |
| `eval.json` | Grading: whether the patches applied and merged, and each feature's test results. |
| `<agent>_full_traj.json` | The agent's complete history, including turns later replaced by compaction summaries (only written if the agent compacted at least once). |
| `agent<feature>_traj.json` or `solo_traj.json` | The agent's final context as the model last saw it (`agent<feature>` uses the feature number, e.g. `agent4`). |
| `agent<feature>.patch` or `solo.patch` | The patch that was graded. |
| `conversation.json` | Messages the agents sent each other (`coop` and `team` only). |

To download one pair instead of a whole run:

```bash
uv run --frozen hf download agent-coordination-lab/cooperbench-run-logs --repo-type dataset \
  --include "<run_name>/coop/pallets_jinja_task/1559/*" --local-dir logs/
```
