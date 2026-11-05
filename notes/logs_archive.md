# Raw Run Logs (`logs/`)

Raw run logs (`logs/<run_name>/`: trajectories, patches, messages, eval output) are gitignored and kept **on local disk only**. Never upload `logs/` to Hugging Face or any external storage service; all paper tables, figures, and run comparisons are reproducible from the compact summaries exported to `results/<run_name>/` in Git (see [results_format.md](results_format.md)).

## Layout

- `logs/<run_name>/`: one folder per benchmark run on the machine that executed it, named to match `results/<run_name>/`.
- `logs/setup-checks/`: single-pair runs from setting up the environment. Not used in results.

Inside a run folder, each pair has its own folder. The path is built from the four pair columns in `pairs.csv` and `agents.csv`:

```text
logs/<run_name>/<setting>/<repo>/<task_id>/f<feature_a>_f<feature_b>/
```

For example, `pallets_jinja_task,1559,4,8` in a `coop` run is `logs/<run_name>/coop/pallets_jinja_task/1559/f4_f8/`. Each pair folder holds:

| File | Contents |
| :--- | :--- |
| `result.json` | How each agent ended (status, steps, cost, patch size). |
| `eval.json` | Grading: whether the patches applied and merged, and each feature's test results. |
| `<agent>_full_traj.json` | The agent's complete history, including turns later replaced by compaction summaries (only written if the agent compacted at least once). |
| `agent<feature>_traj.json` or `solo_traj.json` | The agent's final context as the model last saw it (`agent<feature>` uses the feature number, e.g. `agent4`). |
| `agent<feature>.patch` or `solo.patch` | The patch that was graded. |
| `conversation.json` | Messages the agents sent each other (`coop` and `team` only). |
