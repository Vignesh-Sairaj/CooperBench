# Results Format

Every paper table and report should be reproducible from `results/` in Git alone. Each benchmark run gets one folder, `results/<run_name>/`, written by [`tools/export_results.py`](../tools/export_results.py). Never edit the generated files by hand; fix the script and re-export instead.

## Workflow

```bash
tools/run.sh coop flash_10 5 --git                                   # run, with launch.json + console.log
uv run --frozen python tools/export_results.py <run_name>            # write results/<run_name>/
uv run --frozen hf upload agent-coordination-lab/cooperbench-run-logs \
  logs/<run_name> <run_name> --repo-type dataset                     # archive raw logs
```

Then add a row for the run in [runs.md](runs.md) and write a few lines under **Observations** in its `summary.md`. The full sequence, including setup and pre-pulling images, is in [workflow.md](workflow.md).

## Run Names

- Baselines use the CLI's own name, for example `coop-msa_v2-git-gemini-3-8-flash-flash_10`.
- Intervention arms add a method suffix (`RUN_SUFFIX=verifier tools/run.sh ...` gives `...-flash_10-verifier`).
- Repeats of the same configuration add `-r2`, `-r3`, and so on.

## Files

| File | Contents |
| :--- | :--- |
| `run.json` | How the run was launched (command, commit, agent config, versions, concurrency, `key_slot` for runs started with `KEY_SLOT`), a link to the raw logs, `headline` metrics, and `load` stats (`peak_input_tokens_per_min`, `median_input_tokens_per_min`, `peak_calls_per_min`, `total_retries`, `rate_limit_retries`, `server_busy_retries`). |
| `pairs.csv` | One row per task pair. This is the data behind every table and statistical test. |
| `agents.csv` | One row per agent per pair, for step, cost, and failure analysis. |
| `summary.md` | Generated numbers and a pairs table, plus a hand-written **Observations** section that survives re-export. |

## `pairs.csv` Columns

| Column | Meaning |
| :--- | :--- |
| `repo`, `task_id`, `feature_a`, `feature_b` | The pair. Use these four columns to match pairs across runs. |
| `setting` | `solo`, `coop`, or `team`. |
| `both_passed` | The pair's score: both features' tests pass on the final code. |
| `feature_a_passed`, `feature_b_passed` | Each feature's tests on their own. |
| `merge_status`, `merge_strategy` | How the agents' patches merged (`clean`, `conflicts`, ...); `n/a` for `solo`. |
| `eval_error` | Grader error, or `not evaluated`. Rows with a value here are excluded from pass rates. |
| `n_agents`, `agents_at_step_limit`, `agents_errored` | Agent count and how many hit the 100-step limit or crashed. |
| `steps_total`, `cost_usd`, `duration_s`, `messages_sent`, `patch_lines_total` | Effort and communication for the pair. |

## `agents.csv` Columns

`repo`, `task_id`, `feature_a`, `feature_b`, `agent_id`, `feature_id`, `role` (`solo`, `peer`, `lead`, `member`), `status` (`Submitted`, `LimitsExceeded`, `Error`), `steps`, `cost_usd`, `patch_lines`, `model_calls`, `reasoning_tokens`, `compactions`, `error`.

## Comparing Runs

Only compare runs that share the model config and concurrency (both are in `run.json`). Compare arms on the same pairs by joining `pairs.csv` files on the four pair columns, so paired tests (for example McNemar) can be used instead of comparing pass rates alone.
