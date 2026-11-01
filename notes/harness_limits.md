# Harness Limits vs. Real Coding Agents

The upstream harness (`mini_swe_agent_v2`) runs agents on much tighter budgets than the coding agents people use day to day. This affects how realistic our baselines are, and it should go in the limitations section of the paper.

## Context Compaction at 28K Tokens

- **What happens:** after each model call, the harness checks the request size. At 28K tokens or more, it asks the model to summarize the older turns and keeps only the system prompt, the task, the summary, and the last 2 turns ([`default.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/default.py), `compaction_token_trigger` in `coop.yaml` and `solo.yaml`).
- **Why 28K:** the upstream config comment says it leaves headroom on 32K-context models. Gemini 3.8 Flash has a 1M-token context.
- **What real coding agents do:** they compact much later, roughly when the model's context is half full or nearly full. Gemini CLI's default is half of the model's input limit (about 500K tokens for a 1M model), and Claude Code compacts close to the model's full window (around 200K).
- **What we saw:** in the first `solo` baseline on `flash_10` with `HIGH` thinking, agents compacted 10 to 24 times in 100 steps (44 times in the one passing pair), and spent steps re-reading files after each compaction. 9 of 10 agents ran out of steps before pushing their work.
- **Why so often:** right after a compaction the context is already 10K to 15K tokens (system prompt, task, summary, and the last 2 turns), and it grows by 1K to 2K tokens per step. That leaves room for only about 10 steps before the next compaction. Thought summaries are about a quarter of each step's growth.

## Other Tight Budgets

- **100 steps per agent**, after which the agent stops. Work counts only if the agent pushed it or opened a PR, so an agent that runs out of steps scores zero even if it edited the right files locally.
- **Bash only:** agents edit files through shell commands, with no dedicated file-editing or search tools.

## Raising the Compaction Threshold: Trade-offs

- **More realistic** and likely fewer wasted steps.
- **Higher API load and cost:** every call resends the current context, so larger contexts mean more input tokens per call. At 28K, 10 agents already reach about 95% of our 1M input-tokens-per-minute limit; at 64K we might fit about 5 agents per key, and at 100K only 2 or 3.
- **Less comparable with upstream** results, which all use 28K.

**Status:** open. Turning off thought summaries (`includeThoughts: false`) did not help: on 3 failed `solo` pairs, compactions went from 14, 14, 24 to 14, 12, 22, and all 3 agents still used 100 steps without pushing (logs in `setup-checks/` of the [logs archive](logs_archive.md)). The threshold itself is the next thing to test. Any change needs team agreement and goes into [`configs/gemini_3_8_flash_high.yaml`](../configs/gemini_3_8_flash_high.yaml), applied to every run in a comparison.
