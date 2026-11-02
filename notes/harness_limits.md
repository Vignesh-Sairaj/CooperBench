# Harness Limits vs. Real Coding Agents

The upstream harness (`mini_swe_agent_v2`) gives agents much tighter budgets than the coding agents people use day to day. This affects how realistic our baselines are, and it belongs in the limitations section of the paper. For how these limits played out in our runs, see [baseline_ablation_flash10.md](baseline_ablation_flash10.md).

## Context Compaction at 28K Tokens

- **What happens:** after each model call, the harness checks how big the request was. At 28,000 tokens or more, it asks the model to summarize the older turns, then keeps only the system prompt, the task, the summary, and the last 2 turns (`compaction_token_trigger` in the harness configs `solo.yaml` and `coop.yaml`).
- **Why 28K:** the upstream config comment says it leaves headroom for models with a 32K context. Gemini 3.8 Flash accepts up to 1M tokens.
- **What real coding agents do:** they compact much later, roughly when the model's context is half full or nearly full. Gemini CLI's default is half of the model's input limit (about 500K tokens for a 1M model), and Claude Code compacts close to the model's full window (around 200K).
- **What we saw:** in the first `solo` run on `flash_10`, agents compacted 5 to 12 times in 100 steps (22 times in the one passing pair) and spent steps re-reading files after each compaction. 9 of 10 agents ran out of steps before pushing their work.
- **Why so often:** right after a compaction the context is already 10K to 15K tokens (system prompt, task, summary, and the last 2 turns), and it grows by 1K to 2K tokens per step.
- **It is a soft budget, not a hard window:** the size check runs after each call, so the request that crosses the threshold is still sent in full. One command that prints a lot can push a single request far past the threshold. With compaction at 64K, `solo` agents on `dspy_task/8394` and `pallets_jinja_task/1559` sent requests of up to about 185K tokens after printing very large command outputs.

## Early Checks: Thought Summaries and 64K Compaction

Before the full experiments, we re-ran 3 failed `solo` pairs with 100 steps under two changes (raw logs in `setup-checks/` of the [logs archive](logs_archive.md)):

| Pair | Compactions at 28K | With thought summaries turned off | At 64K | Steps used | Submitted | Cost at 64K |
| :--- | :---: | :---: | :---: | :---: | :---: | ---: |
| `pallets_click_task/2800` | 7 | 7 | 5 | 100 | no | `$1.23` |
| `typst_task/6554` | 7 | 6 | 2 | 100 | no | `$0.76` |
| `pallets_jinja_task/1559` | 12 | 11 | 4 | 100 | no | `$1.05` |

- Turning off thought summaries (the model's reasoning text saved in the logs) barely changed how often agents compacted, and we lost readable reasoning, so we keep them on.
- Raising the threshold to 64K cut compactions 1.4x to 3.5x, but roughly doubled each agent's token use per minute, which halves how many agents fit per API key ([model_config.md](model_config.md#concurrency)).
- **Neither change fixed the problem at 100 steps:** all 3 agents still used every step without pushing. Raising both the step limit and the threshold did fix it later (`solo` went to 7/10 with 250 steps and 64K).

## The Step Limit and How Work Is Graded

- **What counts as a step:** every model response counts, including responses that run no command. Compaction summaries do not count. At the limit (100 by default) the agent is stopped.
- **Agents are not told the limit:** neither the `solo` nor the `coop` prompt mentions it.
- **Only pushed work is graded:** the grader takes the agent's pushed branch or opened pull request. Edits that were never committed and pushed count as an empty patch, so an agent stopped one step before pushing scores the same as one that did nothing.
- **Telling the agent the limit is not enough:** we added the limit to the task prompt and scored 0/10. The agent sees the limit on every call, but nothing tells it which step it is on, and compaction removes the history it could count from. No agent mentioned the limit in its reasoning. An opt-in step counter that shows "Step n of N: k left" on every turn (`agent.step_counter`, used by `configs/variants/stepcounter.yaml`) fixed this for `solo`: 7/10 at 100 steps, with 9 of 10 agents pushing before the limit.
- **Bash only:** agents edit files through shell commands, with no dedicated file-editing or search tools.

## Harness Bugs We Hit

- **A single command can hang for hours.** The harness lets one shell command run for up to 3 hours (hardcoded in [`adapter.py`](../src/cooperbench/agents/mini_swe_agent_v2/adapter.py)), but the agent's container only lives for 2 hours. When a command never finishes, the agent stalls until the container dies. We saw this twice: a `grep` over the whole filesystem (83 minutes) and a Python test script stuck in a loop (70 minutes). Both times we stopped the command by hand and the agent carried on. It costs wall time, and if the container expires first the agent loses its environment. The 2-hour lifetime also ended any run longer than 2 hours: the adapter ignored `environment.container_timeout` from configs. Our fork now passes it through when a config sets it (default unchanged), which the 500-step `saturation_*` configs use (10 hours).
- **A reminder to submit can crash the agent.** In `coop` and `team`, when an agent says it is done but has not pushed, the harness adds a reminder and lets it continue ([`default.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/default.py), the submit nudge in `run()`). The end-of-run marker stays in the conversation, so the next model call fails with `Invalid Message passed in - {'role': 'exit', ...}` and the agent ends with an error. We saw this once, for the lead in `team` on `pallets_jinja_task/1621`. **Fixed in our fork:** the exit message is now removed before the reminder is added (`_continue_after_exit()` in `default.py`, with tests). Runs exported before this fix can still contain the crash. The fix also needs to go upstream (see [tasks.md](tasks.md)).
- **Per-pair durations can be off by an hour.** [`coop.py`](../src/cooperbench/runner/coop.py) times each pair with the local wall clock, so pairs that run across a daylight saving time change show a duration one hour off in `pairs.csv`. The run's total time is measured differently and is correct.
- **`team` mode gives contradicting submission instructions and drops message counts.** In `mini_swe_agent_v2`, [`adapter.py`](../src/cooperbench/agents/mini_swe_agent_v2/adapter.py) appends the `team` role prompt ([`team_harness/prompt.py`](../src/cooperbench/team_harness/prompt.py)) onto the `coop.yaml` task prompt. The `coop.yaml` block tells each agent to push a pull request containing only its own work, while `team_harness/prompt.py` (written for CLI adapters that grade local `patch.txt`) tells the lead to apply the member's diff from `/workspace/shared/` and write `git diff > patch.txt`. Because `adapter.py` only grades the pushed git branch (`git_connector.submitted_patch`) and ignores `patch.txt`, any lead that integrates in `patch.txt` without committing and pushing the combined tree to git has its integration step discarded; conversely, any lead that does push the combined tree triggers a three-way merge conflict against the member's standalone branch and relies on the grader's lead-alone fallback (`solo-agent1` in [`eval/sandbox.py`](../src/cooperbench/eval/sandbox.py)). In addition, `_spawn_team_agent` in [`runner/team.py`](../src/cooperbench/runner/team.py) omits `result.sent_messages`, so `conversation.json` and `messages_sent` record `0` for tool-calling runs even when agents exchange dozens of `send_message` turns. The proposed fix is tracked in [tasks.md](tasks.md#fix-team-grading).
