# Concurrency and Rate Limits

How many pairs to run at once per GCP project, and why. The frozen values are in the [reference setup](model_config.md#reference-setup).

## Reference Concurrency (Vertex AI)

`-c` counts pairs (`-c` agents for `solo`, `2 * -c` agents for `coop` and `team`).

| Setting | `-c` per project | Agents at once | Evidence (128K compaction, `medium` thinking, 50 pairs) |
| :--- | :---: | :---: | :--- |
| `solo` | `-c 8` | 8 | 14 rate-limit retries in 195 minutes; retries only add waiting time in `solo` |
| `coop`, `coop --git`, `team` | `-c 4` | 8 | 14 rate-limit retries in 317 minutes, and no false "colleague stopped" notices |

Use the same values at every hour, and don't raise them off-peak for runs that will be compared. To run faster, run more experiments in parallel on separate GCP projects instead.

**Why `coop` and `team` stay low.** During US business hours (Monday to Friday, 9:00 to 17:00 Pacific), `gemini-3.8-flash` on Vertex AI has little spare shared capacity, and a request can wait up to 10 minutes before it fails and is retried. An agent refreshes its "still running" signal only between turns, and the signal expires after 600 seconds, so when one turn stalls that long, its partner is told "[colleague] is no longer running" and may carry on alone. At `-c 5` with 64K compaction during business hours, 5 of 50 pairs got this false notice; at `-c 4` with 128K, none did. After each `coop` or `team` run, check the retry counts and count the pairs whose trajectories contain "is no longer running]". The lasting fix is a harness change that refreshes the signal during long model calls (see [tasks.md](tasks.md)).

Earlier measurements at 28K and 64K, for reference: `solo` handled 10 agents per project; `coop` at 28K handled 20 agents off-peak but had false notices on 8 of 40 pairs at peak; `gemini-3-flash-preview` handled 20 agents with no retries at any hour.

## Vertex AI Quota

On `VERTEXAI_LOCATION=global`, Vertex AI uses Dynamic Shared Quota rather than a fixed 1M input-TPM ceiling per project: `flash_10` runs at `-c 10` (20 concurrent agents in `coop`) measured over 3M input tokens per minute on a single project with zero `429` retries. Because Dynamic Shared Quota is shared capacity, peak hours can still see occasional `429` bursts, so keep checking retry counts after each run. To scale across multiple projects in parallel, set `VERTEXAI_PROJECT_1`, `VERTEXAI_PROJECT_2`, and so on in `.env` and pass `KEY_SLOT=<n>` ([workflow.md](workflow.md)). Vertex AI quota is separate from AI Studio quota, so a Vertex run and an AI Studio run on the same GCP project do not compete.

## AI Studio (`gemini/`)

Earlier runs used `MODEL=gemini/gemini-3.8-flash` (AI Studio keys). There the limit is AI Studio's hard cap of 1M input tokens per minute (TPM) per GCP project, not the machine (10 agent containers used a load under 8 on 128 cores and about 34 GB of RAM). The other limits, 1,000 requests per minute and unlimited requests per day, are never reached.

### Measured Load per Agent

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

### Recommended `-c` per API Key

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
