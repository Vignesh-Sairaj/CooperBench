# Results Format

Every paper table and report should be reproducible from `results/` in Git alone. Each benchmark run gets one folder, `results/<run_name>/`, written by [`tools/export_results.py`](../tools/export_results.py). Never edit the generated files by hand; fix the script and re-export instead.

## Workflow

```bash
set -a; source .env; set +a
tools/run.sh coop flash_10 10 --git                                  # run, with launch.json + console.log
uv run --frozen python tools/export_results.py <run_name>            # write results/<run_name>/
uv run --frozen hf upload agent-coordination-lab/cooperbench-run-logs \
  logs/<run_name> <run_name> --repo-type dataset                     # archive raw logs
```

Then add a row for the run in [runs.md](runs.md) and write the **Experiment** and **Observations** sections in its `summary.md`. The full sequence, including setup and pre-pulling images, is in [workflow.md](workflow.md).

## Run Names

- Baselines use the CLI's own name, for example `coop-msa_v2-git-gemini-3-8-flash-flash_10`.
- Runs with the reference settings end in `-ref` (`tools/run.sh coop flash 4 --git` gives `coop-msa_v2-git-gemini-3-8-flash-flash-ref`).
- Intervention arms add a method suffix instead (`RUN_SUFFIX=verifier tools/run.sh ...` gives `...-flash-verifier`).
- Repeats of the same configuration add `-r2`, `-r3`, and so on.

## Files

| File | Contents |
| :--- | :--- |
| `run.json` | How the run was launched (command, commit, agent config, versions, concurrency, `key_slot` for runs started with `KEY_SLOT`), a link to the raw logs, `headline` metrics, and `load` stats (`peak_input_tokens_per_min`, `median_input_tokens_per_min`, `peak_calls_per_min`, `total_retries`, `rate_limit_retries`, `server_busy_retries`). |
| `pairs.csv` | One row per task pair: whether it passed and how the patches merged. Use it for pass rates and for comparing runs. |
| `agents.csv` | One row per agent in each pair (1 per pair in `solo`, 2 in `coop`): what each agent did. Use it to explain why a pair failed, since the agents in a pair often end differently. |
| `summary.md` | The page to read. In order: **Experiment** (hand-written: what the run tests and why), **Results** (setting, step limit, compaction, pass rate, cost), **Pairs**, **Observations** (hand-written: what we saw in the traces), and **Run Details** (model, config file, concurrency, key slot, commit, API load, raw logs). Re-exporting regenerates everything except the two hand-written sections. |

For example, in `coop`, `pairs.csv` can show a failed pair while `agents.csv` shows that one agent submitted its feature and the other hit the step limit with nothing pushed. Both files share the four pair columns, so you can join them.

## `pairs.csv` Columns

| Column | Meaning |
| :--- | :--- |
| `repo`, `task_id`, `feature_a`, `feature_b` | The pair. Use these four columns to match pairs across runs. |
| `setting` | `solo`, `coop`, or `team`. |
| `both_passed` | The pair's score: both features' tests pass on the final code. |
| `feature_a_passed`, `feature_b_passed` | Each feature's tests on their own. |
| `merge_status`, `merge_strategy` | How the agents' patches merged (`clean`, `identical`, `conflicts`, or `missing_input` when a patch did not apply); `n/a` for `solo`. |
| `eval_error` | Grader error, or `not evaluated`. Rows with a value here are excluded from pass rates. |
| `n_agents`, `agents_at_step_limit`, `agents_errored` | Agent count and how many hit the run's step limit or crashed. |
| `steps_total`, `cost_usd`, `duration_s`, `messages_sent`, `patch_lines_total` | Effort and communication for the pair, summed over its agents. |

## `agents.csv` Columns

| Column | Meaning |
| :--- | :--- |
| `repo`, `task_id`, `feature_a`, `feature_b` | The pair this agent worked on (same as in `pairs.csv`). |
| `agent_id`, `feature_id`, `role` | Which agent, which feature it owned (empty for `solo`), and its role (`solo`, `peer`, `lead`, `member`). |
| `status` | How the agent ended: `Submitted`, `LimitsExceeded` (hit the step or cost limit), or `Error`. |
| `steps`, `model_calls` | Model responses counted against the step limit, and model calls made. |
| `cost_usd`, `reasoning_tokens` | What the agent cost and how many thinking tokens it used. |
| `patch_lines` | Size of the patch the agent pushed. `0` means nothing was submitted for grading. |
| `compactions` | How many times its context was summarized. |
| `error` | Error message if the agent crashed. |

## Comparing Runs

Only compare runs that use the same model setup (in `run.json`), and check the retry counts in **Run Details**: heavy rate limiting can slow `coop` agents enough to change results. Compare runs on the same pairs by joining their `pairs.csv` files on the four pair columns. That allows a paired test, which looks only at the pairs where the two runs disagree, instead of comparing pass rates alone. With 10 pairs, a difference of 1 to 2 pairs is within run-to-run variation.
