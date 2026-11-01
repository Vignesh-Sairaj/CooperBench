# Harness Limits vs. Real Coding Agents

The upstream harness (`mini_swe_agent_v2`) runs agents on much tighter budgets than the coding agents people use day to day. This affects how realistic our baselines are, and it should go in the limitations section of the paper.

## Context Compaction at 28K Tokens

- **What happens:** after each model call, the harness checks the request size. At 28K tokens or more, it asks the model to summarize the older turns and keeps only the system prompt, the task, the summary, and the last 2 turns ([`default.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/default.py), `compaction_token_trigger` in `coop.yaml` and `solo.yaml`).
- **Why 28K:** the upstream config comment says it leaves headroom on 32K-context models. Gemini 3.8 Flash has a 1M-token context.
- **What real coding agents do:** they compact much later, roughly when the model's context is half full or nearly full. Gemini CLI's default is half of the model's input limit (about 500K tokens for a 1M model), and Claude Code compacts close to the model's full window (around 200K).
- **What we saw:** in the first `solo` baseline on `flash_10` with `HIGH` thinking, agents compacted 5 to 12 times in 100 steps (22 times in the one passing pair; note an earlier export doubled these counts by counting both solver and summarizer trajectory segments), and spent steps re-reading files after each compaction. 9 of 10 agents ran out of steps before pushing their work.
- **Why so often:** right after a compaction the context is already 10K to 15K tokens (system prompt, task, summary, and the last 2 turns), and it grows by 1K to 2K tokens per step.
- **It is a soft budget, not a hard window:** the size check runs after each call, so the request that crosses the threshold is still sent in full. One command that prints a lot can push a single request far past the threshold. With compaction at 64K, `solo` agents on `dspy_task/8394` and `pallets_jinja_task/1559` sent requests of up to about 185K tokens after printing very large command outputs.

## Diagnostic Checks: Thought Summaries and 64K Compaction

We re-ran 3 failed `solo` pairs (`pallets_click_task/2800`, `typst_task/6554`, `pallets_jinja_task/1559`) under two changes (raw logs in `setup-checks/` of the [logs archive](logs_archive.md)):

| Pair | Compactions (28K ref) | Compactions (`includeThoughts: false`) | Compactions (64K) | Steps (all 3 arms) | Submitted | Cost at 64K |
| :--- | :---: | :---: | :---: | :---: | :---: | ---: |
| `pallets_click_task/2800` | 7 | 7 | 5 | 100 | no | `$1.23` |
| `typst_task/6554` | 7 | 6 | 2 | 100 | no | `$0.76` |
| `pallets_jinja_task/1559` | 12 | 11 | 4 | 100 | no | `$1.05` |

- Turning off thought summaries barely changed compaction counts and lost readable reasoning traces, so we keep `includeThoughts: true`.
- Raising `compaction_token_trigger` to `64000` cut compactions 1.4x to 3.5x while roughly doubling input token rate per agent (~163K vs. ~76K tok/min/agent, reducing safe concurrency from about 8 agents to 4 per key; 1 transient `503` congestion retry, 0 `429` rate limits).
- **Neither change fixed the 0 submissions:** all 3 agents still ran all 100 steps without pushing.

## Unannounced 100-Step Limit and Publish-Only Grading

- **100 model responses per agent (`step_limit: 100`):** `DefaultAgent.query()` increments `n_calls` on every model response (including responses without a bash command; compaction summary calls do not count) and raises `LimitsExceeded` at 100.
- **Agents are never told the step budget:** neither `solo.yaml` nor `coop.yaml` mentions the 100-step cap, and `GitConnector.submitted_patch()` grades only pushed branches or PRs (`refs/tags/pr/<agent>` or `refs/heads/<agent>`). Local uncommitted or unpushed edits inside `/workspace/repo` produce an empty patch (`0` lines).
- **Bash only:** agents edit files through shell commands, with no dedicated file-editing or search tools.
- **Why static prompt budget notices fail:** in `solo` `budgetprompt` (`0/10`), zero assistant messages mentioned the step cap because compaction keeps only `2` recent turns and tool observations carry no step counter. In `solo`, combining `250 steps + 64K compaction` raised pass rate to `7/10` (`70%`), matching `coop --git` at `250 steps + 28K` (`8/10`); see [baseline_ablation_flash10.md](baseline_ablation_flash10.md).

## Upstream Runner Bugs Observed in Overnight Runs

- **3-hour per-command timeout exceeds container lifetime:** [`adapter.py`](../src/cooperbench/agents/mini_swe_agent_v2/adapter.py) hardcodes `"timeout": 10800` (3 hours per bash command, ignoring `environment.timeout`) while [`docker.py`](../src/cooperbench/agents/mini_swe_agent_v2/environments/docker.py) starts containers with `sleep 2h` (`container_timeout: "2h"`). When an agent runs `grep -rn ... / 2>/dev/null`, `grep` scans `/proc` until the 2-hour container exits instead of timing out the single command.
- **Wall-clock `datetime.now()` per-pair duration in `coop.py`:** [`coop.py`](../src/cooperbench/runner/coop.py) computes per-pair `duration_seconds` with naive local `datetime.now()` rather than `time.monotonic()`, producing a `-3600s` offset on pairs crossing a Daylight Saving Time fallback (run-level `total_time_seconds` in `summary.json` uses `time.time()` and is unaffected).
