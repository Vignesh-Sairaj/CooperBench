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
| Concurrency | About 8 agents per key at 28K: `-c 8` for `solo`, `-c 4` for `coop` and `team` |
| Run name | Leave out `-n`; intervention arms add a suffix (see [results_format.md](results_format.md)) |
| Subsets | `flash_10` for the baseline screen, `flash` for intervention arms |

[`tools/run.sh`](../tools/run.sh) fills in all of these (with `AGENT_CONFIG` available for controlled variant configs under `configs/variants/`), so prefer it over calling `cooperbench run` directly. The four baselines on `flash_10`:

| Setting | Command | Run name |
| :--- | :--- | :--- |
| `solo` | `tools/run.sh solo flash_10 8` | `solo-msa_v2-gemini-3-8-flash-flash_10` |
| `coop` | `tools/run.sh coop flash_10 4` | `coop-msa_v2-gemini-3-8-flash-flash_10` |
| `coop --git` | `tools/run.sh coop flash_10 4 --git` | `coop-msa_v2-git-gemini-3-8-flash-flash_10` |
| `team` | `tools/run.sh team flash_10 4` | `team-msa_v2-gemini-3-8-flash-flash_10` |

**May still change:** the compaction threshold and the step budget are under test on `flash_10` via `configs/variants/` (see [harness_limits.md](harness_limits.md) and [tasks.md](tasks.md)). If either changes, it goes into the reference agent config and every baseline is rerun.

## Settings and Reasons

| Setting | Value | Why |
| :--- | :--- | :--- |
| Harness | `mini_swe_agent_v2` on local Docker | Upstream default. `openhands_sdk` only runs on Modal. |
| Model | `gemini-3.8-flash` | Fixed in our proposal. |
| Thinking | `HIGH` | Best quality for multi-step coding and merging. Thoughts are saved in trajectories for failure analysis. |
| Cost cap | `$10` per agent | Upstream's `$3` cap could stop `HIGH`-thinking agents early. |
| Step limit | 100 per agent | Upstream default (250-step and budget-prompt variants under test). |
| Concurrency | `-c 8` (`solo`) or `-c 4` (`coop`, `team`) at 28K, one run per key | Keeps ~8 concurrent agents per 1M input-TPM key, leaving headroom for launch peaks; see [Concurrency](#concurrency). |

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

What limits us is the Gemini API's 1M input-tokens-per-minute (TPM) cap per key, not the machine (10 containers used load < 8 on 128 cores and ~34 GB RAM; RPM limit is 1K and RPD is unlimited).

### Measured load per agent

Summing `prompt_tokens` per timestamp minute across trajectories reproduces AI Studio's input-TPM chart (`947,572` computed vs. `945.9K` in AI Studio on the first `solo` `flash_10` run, with 0 rate-limit retries):

| Run | Agents | Avg input tok/min per agent | Calls/min per agent | Peak input tok/min (whole run) |
| :--- | ---: | ---: | ---: | ---: |
| `solo` `flash_10`, 28K | 10 | 76K | 4.2 | 947.6K |
| `coop --git` setup check, 28K, `HIGH` | 2 | 82K | 4.2 | 359.5K |
| `solo` 3 pairs, 28K, no thought summaries | 3 | 90K | 5.3 | 444.3K |
| `solo` 3 pairs, 64K | 3 | 163K | 5.1 | 699.4K (2 overlapping agents) |
| `coop --git` `flash_10` (100 and 250 steps), 28K (`-c 5`) | 10 | ~80K | ~4.2 | 986.3K / 1,046.2K |
| `solo` `flash_10` (250 steps), 64K (`-c 4`) | 4 | ~160K | ~5.0 | 1,083.1K |

- **`coop` agents are not lighter than `solo` agents** (82K vs. 76K tok/min/agent).
- **Load peaks right after launch**, when all agents read files at once, and the peak varies a lot between runs with the same agent count. Four `solo` runs at `-c 10` (10 agents, 28K) peaked at 947.6K, 1,043.2K, 1,183.1K, and 1,271.9K tok/min, with 0, 9, 41, and 64 `429` retries. Two `coop --git` runs at `-c 5` (also 10 agents) logged 7 and 6 `429` retries, and `coop` (no `--git`) at `-c 5` logged 48. The worst peak was about 1.6x the average load, so plan for that:

$$\text{max agents} \approx \frac{\text{1M tok/min}}{\text{avg tok/min per agent} \times 1.6}$$

At 28K this gives 1M / (80K x 1.6) ≈ 8 agents; at 64K it gives 1M / (160K x 1.6) ≈ 4 agents.

### Recommended `-c` per API key

`-c` counts pairs (`-c` agents for `solo`, `2 * -c` agents for `coop` and `team`). Keep the **concurrent agent count** equal across compared runs:

| Compaction threshold | `solo` | `coop`, `coop --git`, `team` | Concurrent agents | Measured |
| :--- | :---: | :---: | :---: | :--- |
| 28K (reference) | `-c 8` | `-c 4` | 8 | 10 agents (`-c 10` / `-c 5`) logged 0 to 64 `429` retries per run |
| 64K | `-c 4` | `-c 2` | 4 | 4 agents peaked at 1,083.1K tok/min with 1 `429` retry |

Throttled calls retry with 4 to 60 second backoff (up to 10 attempts). In `solo` this only adds wall time: a retry happens inside one model call and does not use a step. In `coop` and `team`, a slowed agent can make its partner's `send_message --wait` time out, so retries can change outcomes there. Check the `429` rate-limit and `5xx` server-busy retry counts printed by `tools/run.sh` (and saved in `run.json` under `load`) after each run. Runs before this change used `-c 10` (`solo`) and `-c 5` (`coop`) at 28K; see each run's `run.json` for its concurrency and retry counts. To run more agents at once, split experiments across separate teammates' API keys.

## Why the Config File Matters

Without it, runs silently use `LOW` thinking. LiteLLM (the library that calls the model) sends `LOW` for `gemini-3.8-flash` when no thinking level is set, instead of Google's default `MEDIUM`. The cause is a name check in `litellm==1.81.12` that looks for `gemini-3-flash` and does not match `gemini-3.8-flash`.

Our first end-to-end run (`dottxt_ai_outlines_task` task 1371, features 1 and 2, `coop --git`) used no config file. Its trajectories show 0 reasoning tokens per model call; the same pair with the config file shows about 800, so the config file does switch thinking on.

The `HIGH` run still failed that pair: the patches merged cleanly and feature 1 passed, but agent2 never produced a patch for feature 2 (`$1.28`). An earlier run of the same pair through OpenRouter passed. A single pair is too noisy to compare settings, so we compare them on full subsets.
