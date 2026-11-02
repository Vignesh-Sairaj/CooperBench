# Model Config

Every run uses the same model setup, so differences in results come from the coordination method, not the model. This note covers that setup, how to launch it, and how many agents to run per GCP project or API key.

## Reference Setup

All new runs, baselines and intervention arms alike, use this setup. It is the upstream harness code at `63b9d44`, unmodified, plus our agent config. It is **not** the upstream default setup: our config raises the cost cap from `$3` to `$10` and turns on `HIGH` thinking instead of the `LOW` thinking LiteLLM silently sends.

| Flag or setting | Value |
| :--- | :--- |
| Code | `main` of our fork, with every intervention flag off |
| Harness | `-a mini_swe_agent_v2 --backend docker` |
| Model and provider | `-m vertex_ai/gemini-3.8-flash` (`VERTEXAI_PROJECT` in `.env`, `VERTEXAI_LOCATION=global`, `gcloud` ADC) |
| Agent config | `--agent-config configs/gemini_3_8_flash_high.yaml` |
| Step limit and compaction | Upstream defaults: 100 steps, compaction at 28K tokens |
| Concurrency | `-c 10` per Vertex AI project (for AI Studio `gemini/*` keys, see [Recommended `-c` per API key](#recommended--c-per-api-key)) |
| Run name | Leave out `-n`; intervention arms add a suffix (see [results_format.md](results_format.md)) |
| Subsets | `flash_10` for the baseline screen, `flash` for intervention arms |

[`tools/run.sh`](../tools/run.sh) fills in all of these (with `AGENT_CONFIG` available for controlled variant configs under `configs/variants/`, and `MODEL=gemini/gemini-3.8-flash` still supported for AI Studio keys), so prefer it over calling `cooperbench run` directly. The four baselines on `flash_10`:

| Setting | Command | Run name |
| :--- | :--- | :--- |
| `solo` | `tools/run.sh solo flash_10 10` | `solo-msa_v2-gemini-3-8-flash-flash_10` |
| `coop` | `tools/run.sh coop flash_10 10` | `coop-msa_v2-gemini-3-8-flash-flash_10` |
| `coop --git` | `tools/run.sh coop flash_10 10 --git` | `coop-msa_v2-git-gemini-3-8-flash-flash_10` |
| `team` | `tools/run.sh team flash_10 10` | `team-msa_v2-gemini-3-8-flash-flash_10` |

**Likely to change:** the upstream 100 steps and 28K compaction stop most agents before they submit. The per-turn step counter fixes most of that at the same cost ([model_thinking_stepcounter_flash10.md](model_thinking_stepcounter_flash10.md)), and we have proposed making it standard. The thinking level and budget will be chosen from the 500-step `solo` saturation runs. Whatever the team adopts goes into the reference agent config, and every baseline is rerun on `vertex_ai/gemini-3.8-flash`.

## Settings and Reasons

| Setting | Value | Why |
| :--- | :--- | :--- |
| Harness | `mini_swe_agent_v2` on local Docker | Upstream default. `openhands_sdk` only runs on Modal. |
| Model and provider | `vertex_ai/gemini-3.8-flash` (`global`) | Fixed in our proposal. Vertex AI `global` uses Dynamic Shared Quota (`>3M` input TPM measured per project vs. AI Studio's hard 1M cap) with identical LiteLLM request payload and `$0.75`/`$3.75` per-1M pricing. |
| Thinking | `HIGH` | Best quality for multi-step coding and merging. Thoughts are saved in trajectories for failure analysis. |
| Cost cap | `$10` per agent | Upstream's `$3` cap could stop `HIGH`-thinking agents early. |
| Step limit | 100 per agent | Upstream default. 250 or 500 steps with 64K compaction is under test; see [baseline_ablation_flash10.md](baseline_ablation_flash10.md). |
| Concurrency | `-c 10` on Vertex AI `global` (or per-key limits on AI Studio `gemini/`) | Runs up to 20 agents on one Vertex AI project without hitting AI Studio's 1M input-TPM wall; see [Concurrency](#concurrency). |

Thinking and the cost cap are set in [`configs/gemini_3_8_flash_high.yaml`](../configs/gemini_3_8_flash_high.yaml).

## Running a Single Pair by Hand

For whole subsets, use `tools/run.sh` ([workflow.md](workflow.md)). To try one pair directly, pre-pull its task image and always pass the config file. Leave out `-n` so the CLI names the run after its setting, model, and task:

```bash
docker pull akhatua/cooperbench-dottxt-ai-outlines:task1371

VERTEXAI_PROJECT=<your-gcp-project> VERTEXAI_LOCATION=global \
uv run --frozen cooperbench run \
  -r dottxt_ai_outlines_task -t 1371 -f 1,2 \
  -a mini_swe_agent_v2 \
  -m vertex_ai/gemini-3.8-flash \
  --agent-config configs/gemini_3_8_flash_high.yaml \
  --setting coop --git --backend docker
```

Use the same provider (`vertex_ai/`, `gemini/`, or `openrouter/`) for every run in a comparison: rate-limit pauses and endpoint latency shift relative turn pacing and message arrival order in `coop`. Always keep `VERTEXAI_LOCATION=global` for Vertex AI (regional endpoints add a `1.1x` cost multiplier in LiteLLM or return `404`). Note that `_generate_run_name` strips the provider prefix, so `vertex_ai/gemini-3.8-flash` and `gemini/gemini-3.8-flash` produce the same run folder name (`run.json` records the full `model` string).

## Concurrency

### Vertex AI (`vertex_ai/`, recommended)

On `VERTEXAI_LOCATION=global`, Vertex AI uses Dynamic Shared Quota rather than a fixed 1M input-TPM ceiling per project: `flash_10` runs at `-c 10` (20 concurrent agents in `coop`) measured over 3M input tokens per minute on a single project with zero `429` retries. Because Dynamic Shared Quota is shared capacity, peak hours can still see occasional `429` bursts, so keep checking retry counts after each run. To scale across multiple projects in parallel, set `VERTEXAI_PROJECT_1`, `VERTEXAI_PROJECT_2`, and so on in `.env` and pass `KEY_SLOT=<n>` ([workflow.md](workflow.md)). Vertex AI quota is separate from AI Studio quota, so a Vertex run and an AI Studio run on the same GCP project do not compete.

#### Recommended `-c` per Vertex AI project

`-c` counts pairs (`-c` agents for `solo`, `2 * -c` agents for `coop` and `team`). Keep the concurrent agent count equal across compared runs.

| Model, thinking | Compaction | Agents per project | `solo` | `coop`, `coop --git`, `team` | Measured |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `gemini-3.8-flash`, high (reference) | 28K | 20 | `-c 10` | `-c 10` | `flash_10`, 20 agents: over 3M input tok/min, 0 retries |
| `gemini-3.8-flash`, any thinking level | 64K | 10 (provisional) | `-c 10` | `-c 5` | Being measured on `flash` (500 steps, `low`); update after the first runs |

At 64K each agent sends about twice the tokens per minute it sends at 28K (see the table below), so the 64K row starts at half the agents. Raise it only if a full run logs few `429` retries.

**Run names do not include the provider.** `vertex_ai/gemini-3.8-flash` and `gemini/gemini-3.8-flash` produce the same run name, and the runner skips every pair that already has a result in that folder. When repeating an AI Studio run on Vertex AI, add a suffix (for example `RUN_SUFFIX=saturation-low-vertex`) so it does not reuse the old folder.

### AI Studio (`gemini/`)

Earlier runs used `MODEL=gemini/gemini-3.8-flash` (AI Studio keys). There the limit is AI Studio's hard cap of 1M input tokens per minute (TPM) per GCP project, not the machine (10 agent containers used a load under 8 on 128 cores and about 34 GB of RAM). The other limits, 1,000 requests per minute and unlimited requests per day, are never reached.

### Measured load per agent

Summing `prompt_tokens` per timestamp minute across trajectories reproduces AI Studio's input-TPM chart (`947,572` computed vs. `945.9K` in AI Studio on the first `solo` `flash_10` run, with 0 rate-limit retries):

| Run | Agents | Avg input tok/min per agent | Calls/min per agent | Peak input tok/min (whole run) |
| :--- | ---: | ---: | ---: | ---: |
| `solo` `flash_10`, 28K | 10 | 76K | 4.2 | 947.6K |
| `coop --git` setup check, 28K, `HIGH` | 2 | 82K | 4.2 | 359.5K |
| `solo` 3 pairs, 28K, thought summaries off | 3 | 90K | 5.3 | 444.3K |
| `solo` 3 pairs, 64K | 3 | 163K | 5.1 | 699.4K (2 overlapping agents) |
| `coop --git` `flash_10` (100 and 250 steps), 28K (`-c 5`) | 10 | ~80K | ~4.2 | 986.3K / 1,046.2K |
| `solo` `flash_10` (250 steps), 64K (`-c 4`) | 4 | ~160K | ~5.0 | 1,083.1K |

- **`coop` agents are not lighter than `solo` agents** (82K vs. 76K tok/min/agent).
- **Load peaks right after launch**, when all agents read files at once, and the peak varies a lot between runs with the same agent count. Four `solo` runs at `-c 10` (10 agents, 28K) peaked at 947.6K, 1,043.2K, 1,183.1K, and 1,271.9K tok/min, with 0, 9, 41, and 64 `429` retries. Two `coop --git` runs at `-c 5` (also 10 agents) logged 7 and 6 `429` retries, and `coop` (no `--git`) at `-c 5` logged 48. The worst peak was about 1.6x the average load, so plan for that:

$$\text{max agents} \approx \frac{\text{1M tok/min}}{\text{avg tok/min per agent} \times 1.6}$$

At 28K this gives 1M / (80K x 1.6) ≈ 8 agents; at 64K it gives 1M / (160K x 1.6) ≈ 4 agents.

### Recommended `-c` per API key

`-c` counts pairs (`-c` agents for `solo`, `2 * -c` agents for `coop` and `team`). How many agents fit depends on the **model and thinking level**, not just the compaction threshold: at low thinking, each model call returns faster, so each agent sends more tokens per minute. Keep the **concurrent agent count** equal across compared runs.

| Model, thinking | Compaction | Agents per key | `solo` | `coop`, `coop --git`, `team` | Measured |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `gemini-3.8-flash`, high (reference) | 28K | 8 | `-c 8` | `-c 4` | 8 agents: 0 retries; 10 agents: 0 to 64 retries per run |
| `gemini-3.8-flash`, high | 64K | 4 | `-c 4` | `-c 2` | 4 agents: 1 and 6 retries |
| `gemini-3.8-flash`, low | 28K | 4 | `-c 4` | `-c 2` | 3 agents: 0 retries; 6 agents: 105 retries |
| `gemini-3.8-flash`, low | 64K | 2 | `-c 2` | `-c 1` | 3 agents: about 300 retries per 25-pair run (500 steps) |
| `gemini-3-flash-preview`, minimal or low | 28K | 3 | `-c 3` | `-c 1` | 3 agents: 2 and 26 retries; 6 agents: 69 and 73 retries |
| `gemini-3-flash-preview`, high | 28K | 5 | `-c 5` | `-c 2` | 3 agents: 0 retries; 6 agents: 61 retries |

Rows with only one or two measurements are estimates. Peak load per agent in these runs was about 105K to 125K tokens/min for 3.8 Flash at `high` and 28K, 270K to 300K at 64K, and 180K to 400K for either model at `minimal` or `low`.

The rate-limit errors name the model as well as the project, so the limit is probably separate for each model. If so, a `gemini-3-flash-preview` run and a `gemini-3.8-flash` run could share one key without competing; we have not tested this.

Throttled calls retry with 4 to 60 second backoff (up to 10 attempts). In `solo` this only adds wall time: a retry happens inside one model call and does not use a step. In `coop` and `team`, a slowed agent can make its partner give up waiting for a reply, so retries can change outcomes there. Check the `429` rate-limit and `5xx` server-busy retry counts printed by `tools/run.sh` (and saved in `run.json` under `load`) after each run. Runs before this change used `-c 10` (`solo`) and `-c 5` (`coop`) at 28K; see each run's `run.json` for its concurrency and retry counts. To run more agents at once, run separate experiments in parallel, each with a key from a different GCP project (`KEY_SLOT`, see [workflow.md](workflow.md)). Rate limits apply per project, not per key.

## Why the Config File Matters

Without it, runs silently use `LOW` thinking. LiteLLM (the library that calls the model) sends `LOW` for `gemini-3.8-flash` when no thinking level is set, instead of Google's default `MEDIUM`. The cause is a name check in `litellm==1.81.12` that looks for `gemini-3-flash` and does not match `gemini-3.8-flash`.

Our first end-to-end run (`dottxt_ai_outlines_task` task 1371, features 1 and 2, `coop --git`) used no config file. Its trajectories show 0 reasoning tokens per model call; the same pair with the config file shows about 800, so the config file does switch thinking on.

The `HIGH` run still failed that pair: the patches merged cleanly and feature 1 passed, but agent2 never produced a patch for feature 2 (`$1.28`). An earlier run of the same pair through OpenRouter passed. A single pair is too noisy to compare settings, so we compare them on full subsets.
