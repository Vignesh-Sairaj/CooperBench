# Benchmark Runs

One row per run exported to `results/`. Each run's `summary.md` has the per-pair results and what we saw in the traces; `run.json` has the exact command and config.

How to read the table:

- **Setting:** `solo` is one agent implementing both features. `coop` is two agents, one feature each, who can message each other. `coop --git` adds a shared git remote where they can push and pull each other's branches. `team` is a lead plus a member with a shared task list.
- **Subset:** `flash_10` is 10 hand-picked feature pairs (one per task, 9 repos), used for cheap screening.
- **Step limit:** the maximum number of model responses per agent. The agent is then stopped, and only work it pushed counts. Upstream default: 100.
- **Compaction:** once a request reaches this many tokens, the harness replaces older turns with a model-written summary and keeps only the last 2 turns verbatim. Upstream default: 28K (28,000 tokens). In effect this is a soft context budget set by the harness, far below the model's own 1M-token limit. It is soft because the check runs after each call, so one large command output can push a single request well past it (we saw up to 185K at a 64K threshold). Right after a compaction the context is back to roughly 10K to 15K.
- **Passed:** both features' hidden tests pass (in `coop`, after merging the two agents' patches).
- Every run uses `gemini-3.8-flash` with `HIGH` thinking and a `$10` per-agent cost cap ([model_config.md](model_config.md)). With 10 pairs, a difference of 1 to 2 pairs is within run-to-run variation ([baseline_ablation_flash10.md](baseline_ablation_flash10.md)).

| Run (summary) | Setting | Subset | Step limit | Compaction | Other change | Question it answers | Passed | Cost |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- | :---: | ---: |
| [`solo-...-flash_10`](../results/solo-msa_v2-gemini-3-8-flash-flash_10/summary.md) | `solo` | `flash_10` | 100 | 28K | None | Baseline with upstream budgets | 1/10 | `$8.92` |
| [`solo-...-flash_10-r2`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-r2/summary.md) | `solo` | `flash_10` | 100 | 28K | None (repeat) | How much does the same setup vary? | 0/10 | `$8.99` |
| [`solo-...-flash_10-budgetprompt`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-budgetprompt/summary.md) | `solo` | `flash_10` | 100 | 28K | Task prompt states the step limit | Does telling the agent the limit help? | 0/10 | `$8.41` |
| [`solo-...-flash_10-steps250`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `solo` | `flash_10` | 250 | 28K | None | Do agents finish with more steps? | 2/10 | `$18.75` |
| [`solo-...-flash_10-steps250-compact64k`](../results/solo-msa_v2-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `solo` | `flash_10` | 250 | 64K | None | Does one agent need more context for two features? | 7/10 | `$19.63` |
| [`coop-...-git-...-flash_10`](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10/summary.md) | `coop --git` | `flash_10` | 100 | 28K | None | Baseline with upstream budgets | 3/10 | `$11.93` |
| [`coop-...-git-...-flash_10-steps250`](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop --git` | `flash_10` | 250 | 28K | None | Do agents finish with more steps? | 8/10 | `$19.87` |
| [`coop-...-flash_10-steps250`](../results/coop-msa_v2-gemini-3-8-flash-flash_10-steps250/summary.md) | `coop` | `flash_10` | 250 | 28K | No shared git | Does the shared git remote matter? | 8/10 | `$23.05` |
| [`coop-...-git-...-flash_10-steps250-compact64k`](../results/coop-msa_v2-git-gemini-3-8-flash-flash_10-steps250-compact64k/summary.md) | `coop --git` | `flash_10` | 250 | 64K | None | `coop` vs. `solo` at the same per-agent budget | 8/10 | `$21.68` |

Full run names follow `<setting>-msa_v2-[git-]gemini-3-8-flash-<subset>[-<variant>]` ([results_format.md](results_format.md)).
