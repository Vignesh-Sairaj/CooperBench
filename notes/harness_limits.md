# Harness Limits vs. Real Coding Agents

The upstream harness (`mini_swe_agent_v2`) runs agents on much tighter budgets than the coding agents people use day to day. This affects how realistic our baselines are, and it should go in the limitations section of the paper.

## Context Compaction at 28K Tokens

- **What happens:** after each model call, the harness checks the request size. At 28K tokens or more, it asks the model to summarize the older turns and keeps only the system prompt, the task, the summary, and the last 2 turns ([`default.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/default.py), `compaction_token_trigger` in `coop.yaml` and `solo.yaml`).
- **Why 28K:** the upstream config comment says it leaves headroom on 32K-context models. Gemini 3.8 Flash has a 1M-token context.
- **What real coding agents do:** they compact much later, roughly when the model's context is half full or nearly full. Gemini CLI's default is half of the model's input limit (about 500K tokens for a 1M model), and Claude Code compacts close to the model's full window (around 200K).
- **What we saw:** in the first `solo` baseline on `flash_10` with `HIGH` thinking, agents compacted 5 to 12 times in 100 steps (22 times in the one passing pair; note an earlier export doubled these counts by counting both solver and summarizer trajectory segments), and spent steps re-reading files after each compaction. 9 of 10 agents ran out of steps before pushing their work.
- **Why so often:** right after a compaction the context is already 10K to 15K tokens (system prompt, task, summary, and the last 2 turns), and it grows by 1K to 2K tokens per step.

## Diagnostic Checks: Thought Summaries and 64K Compaction

We re-ran 3 failed `solo` pairs (`pallets_click_task/2800`, `typst_task/6554`, `pallets_jinja_task/1559`) under two changes (raw logs in `setup-checks/` of the [logs archive](logs_archive.md)):

| Pair | Compactions (28K ref) | Compactions (`includeThoughts: false`) | Compactions (64K) | Steps (all 3 arms) | Submitted | Cost at 64K |
| :--- | :---: | :---: | :---: | :---: | :---: | ---: |
| `pallets_click_task/2800` | 7 | 7 | 5 | 100 | no | `$1.23` |
| `typst_task/6554` | 7 | 6 | 2 | 100 | no | `$0.76` |
| `pallets_jinja_task/1559` | 12 | 11 | 4 | 100 | no | `$1.05` |

- Turning off thought summaries barely changed compaction counts and lost readable reasoning traces, so we keep `includeThoughts: true`.
- Raising `compaction_token_trigger` to `64000` cut compactions 1.4x to 3.5x while roughly doubling input token rate per agent (~163K vs. ~76K tok/min/agent, reducing safe concurrency from 10 agents to 4 per key; 1 transient `503` congestion retry, 0 `429` rate limits).
- **Neither change fixed the 0 submissions:** all 3 agents still ran all 100 steps without pushing.

## Unannounced 100-Step Limit and Publish-Only Grading

- **100 model responses per agent (`step_limit: 100`):** `DefaultAgent.query()` increments `n_calls` on every model response (including responses without a bash command; compaction summary calls do not count) and raises `LimitsExceeded` at 100.
- **Agents are never told the step budget:** neither `solo.yaml` nor `coop.yaml` mentions the 100-step cap, and `GitConnector.submitted_patch()` grades only pushed branches or PRs (`refs/tags/pr/<agent>` or `refs/heads/<agent>`). Local uncommitted or unpushed edits inside `/workspace/repo` produce an empty patch (`0` lines).
- **Bash only:** agents edit files through shell commands, with no dedicated file-editing or search tools.

**Status:** testing step-budget variants (`configs/variants/steps250.yaml`, `configs/variants/budgetprompt.yaml`, and `configs/variants/steps250_compact64k.yaml`) on `flash_10` alongside `coop --git` before freezing the team reference setup.
