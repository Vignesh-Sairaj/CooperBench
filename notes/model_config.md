# Model Config

Every run uses the same setup, so differences in results come from the coordination method, not the model.

## Reference Setup

All our runs, baselines and intervention arms alike, use this setup. It is the upstream harness code at `63b9d44`, unmodified, plus our agent config. It is **not** the upstream default setup: our config raises the cost cap from `$3` to `$10` and turns on `HIGH` thinking instead of the `LOW` thinking LiteLLM silently sends.

| Flag or setting | Value |
| :--- | :--- |
| Code | `main` of our fork, with every intervention flag off |
| Harness | `-a mini_swe_agent_v2 --backend docker` |
| Model and provider | `-m gemini/gemini-3.8-flash` (AI Studio key in `GEMINI_API_KEY`) |
| Agent config | `--agent-config configs/gemini_3_8_flash_high.yaml` |
| Step limit and compaction | Upstream defaults: 100 steps, compaction at 28K tokens |
| Concurrency | `-c 10`, one run at a time per API key |
| Run name | Leave out `-n`; intervention arms add a suffix (see [results_format.md](results_format.md)) |
| Subsets | `flash_10` for the baseline screen, `flash` for intervention arms |

[`tools/run.sh`](../tools/run.sh) fills in all of these, so prefer it over calling `cooperbench run` directly. The four baselines on `flash_10`:

| Setting | Command | Run name |
| :--- | :--- | :--- |
| `solo` | `tools/run.sh solo flash_10 10` | `solo-msa_v2-gemini-3-8-flash-flash_10` |
| `coop` | `tools/run.sh coop flash_10 10` | `coop-msa_v2-gemini-3-8-flash-flash_10` |
| `coop --git` | `tools/run.sh coop flash_10 10 --git` | `coop-msa_v2-git-gemini-3-8-flash-flash_10` |
| `team` | `tools/run.sh team flash_10 10` | `team-msa_v2-gemini-3-8-flash-flash_10` |

**May still change:** the compaction threshold and the step budget are under test (see [harness_limits.md](harness_limits.md) and [tasks.md](tasks.md)). If either changes, it goes into the agent config and every baseline is rerun.

## Settings and Reasons

| Setting | Value | Why |
| :--- | :--- | :--- |
| Harness | `mini_swe_agent_v2` on local Docker | Upstream default. `openhands_sdk` only runs on Modal. |
| Model | `gemini-3.8-flash` | Fixed in our proposal. |
| Thinking | `HIGH` | Best quality for multi-step coding and merging. Thoughts are saved in trajectories for failure analysis. |
| Cost cap | `$10` per agent | Upstream's `$3` cap could stop `HIGH`-thinking agents early. |
| Step limit | 100 per agent | Upstream default. |
| Concurrency | `-c 10`, one run at a time per API key | See [Concurrency](#concurrency). |

Thinking and the cost cap are set in [`configs/gemini_3_8_flash_high.yaml`](../configs/gemini_3_8_flash_high.yaml).

## How to Run

Pre-pull the task image, then always pass the config file. Leave out `-n` so the CLI names the run after its setting, model and task:

```bash
docker pull akhatua/cooperbench-dottxt-ai-outlines:task1371

uv run --frozen cooperbench run \
  -r dottxt_ai_outlines_task -t 1371 -f 1,2 \
  -a mini_swe_agent_v2 \
  -m gemini/gemini-3.8-flash \
  --agent-config configs/gemini_3_8_flash_high.yaml \
  --setting coop --git --backend docker
```

Use the same provider (`gemini/`, `vertex_ai/`, or `openrouter/`) for every run in a comparison. With OpenRouter, check on one test call that the reasoning token count looks like `HIGH` before bulk runs; we have not verified that OpenRouter passes the setting through.

## Concurrency

Use `-c 10` for now, with one run at a time per API key. Keep `-c` the same across runs you compare.

What limits us is the Gemini API, not the machine. Measured on 2026-10-31 with `solo` on `flash_10` at `-c 10` (10 agents at once, `HIGH` thinking):

- **Machine:** all 10 containers started at once with pre-pulled images, with no startup timeouts. Load average stayed under 8 on 128 cores, and memory use was about 34 GB.
- **API:** AI Studio showed a peak of 946K input tokens per minute against a 1M limit, at 75 requests per minute (limit 1K; requests per day are unlimited). Each call resends the agent's conversation, about 12.6K input tokens per call.
- **Retries:** none logged in the first 25 minutes.

`-c` counts pairs, not agents. `coop` and `team` at `-c 10` run 20 agents, which will likely go over the input token limit. Throttled calls are retried (waits of 4 to 60 seconds, up to 10 attempts), so throttling shows up as slower agents rather than errors. In `coop`, a slowed agent can make its partner's `send_message --wait` time out, which changes the coordination we are measuring.

After every run, check the retry count that `tools/run.sh` prints at the end (it counts `Retrying` lines in `console.log`). If it is not zero, rerun at `-c 5` or split runs across teammates' API keys, which have separate limits.

## Why the Config File Matters

Without it, runs silently use `LOW` thinking. LiteLLM (the library that calls the model) sends `LOW` for `gemini-3.8-flash` when no thinking level is set, instead of Google's default `MEDIUM`. The cause is a name check in `litellm==1.81.12` that looks for `gemini-3-flash` and does not match `gemini-3.8-flash`.

Our first end-to-end run (`dottxt_ai_outlines_task` task 1371, features 1 and 2, `coop --git`) used no config file. Its trajectories show 0 reasoning tokens per model call; the same pair with the config file shows about 800, so the config file does switch thinking on.

The `HIGH` run still failed that pair: the patches merged cleanly and feature 1 passed, but agent2 never produced a patch for feature 2 (`$1.28`). An earlier run of the same pair through OpenRouter passed. A single pair is too noisy to compare settings, so we compare them on full subsets.
