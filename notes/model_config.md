# Model Config

Every run uses the same setup, so differences in results come from the coordination method, not the model.

| Setting | Value | Why |
| :--- | :--- | :--- |
| Harness | `mini_swe_agent_v2` on local Docker | Upstream default. `openhands_sdk` only runs on Modal. |
| Model | `gemini-3.8-flash` | Fixed in our proposal. |
| Thinking | `HIGH` | Best quality for multi-step coding and merging. Thoughts are saved in trajectories for failure analysis. |
| Cost cap | `$10` per agent | Upstream's `$3` cap could stop `HIGH`-thinking agents early. |
| Step limit | 100 per agent | Upstream default. |

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

## Why the Config File Matters

Without it, runs silently use `LOW` thinking. LiteLLM (the library that calls the model) sends `LOW` for `gemini-3.8-flash` when no thinking level is set, instead of Google's default `MEDIUM`. The cause is a name check in `litellm==1.81.12` that looks for `gemini-3-flash` and does not match `gemini-3.8-flash`.

Our first end-to-end run (`dottxt_ai_outlines_task` task 1371, features 1 and 2, `coop --git`) used no config file. Its trajectories show 0 reasoning tokens per model call; the same pair with the config file shows about 800, so the config file does switch thinking on.

The `HIGH` run still failed that pair: the patches merged cleanly and feature 1 passed, but agent2 never produced a patch for feature 2 (`$1.28`). An earlier run of the same pair through OpenRouter passed. A single pair is too noisy to compare settings, so we compare them on full subsets.
