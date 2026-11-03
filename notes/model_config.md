# Model Config

The frozen settings that every comparable run uses, and how to run them. Keep this note short: evidence lives in the experiment notes ([saturation_flash.md](saturation_flash.md)), rate limits in [concurrency.md](concurrency.md), and harness quirks in [harness_limits.md](harness_limits.md).

## Reference Setup

**Frozen on 2026-11-02.** Don't change these settings. New behavior goes behind a flag in a separate config (see [Changing the Setup](#changing-the-setup)).

| Setting | Value | Why |
| :--- | :--- | :--- |
| Model | `gemini-3.8-flash` (sweeps also use `gemini-3-flash-preview` or `gemini-3.1-flash-lite-preview`) | Default reference. Far fewer merge conflicts than `gemini-3-flash-preview`, while Flash-family sweeps test how interventions behave across model capability. |
| Provider | Vertex AI, location `global` | Higher rate limits than AI Studio at the same price. |
| Thinking | `medium` (sweeps also run `low`) | `low` costs `solo` 7 pairs; `high` never beat `medium` and costs more ([evidence](saturation_flash.md#choosing-the-thinking-level)). |
| Step limit | 500 per agent | A ceiling, not a target. A lower limit cuts off `solo`, which needs about twice the steps of one `coop` agent. |
| Compaction | at 128K tokens (a soft trigger) | No consistent accuracy difference from 64K, and far fewer summaries ([evidence](saturation_flash.md#64k-vs-128k-compaction), [how it works](harness_limits.md)). |
| Step counter | On | Shows "Step n of 500: k left" every turn; the largest single improvement we measured, at no cost. |
| Cost cap | `$40` per agent | A safety net; never reached so far. |
| Container lifetime | 10 hours | Upstream's 2 hours is too short for long runs. |
| Concurrency | Per Vertex AI project: `solo` `-c 8`; `coop`, `coop --git`, `team` `-c 4`; any hour | Prevents the slowdowns that make one agent stall while its partner waits ([concurrency.md](concurrency.md)). |
| Harness and code | `-a mini_swe_agent_v2 --backend docker`; `main` of our fork with every intervention flag off | Upstream harness at `63b9d44` plus opt-in flags only. |

The settings live in [`configs/reference/medium.yaml`](../configs/reference/medium.yaml). [`low.yaml`](../configs/reference/low.yaml) and [`high.yaml`](../configs/reference/high.yaml) differ only in the thinking level and are used for thinking sweeps.

## How to Run

[`tools/run.sh`](../tools/run.sh) uses the reference config by default and adds `-ref` to the run name, so a new run never reuses the folder of an older run made with other settings. Load `.env` first (`set -a; source .env; set +a`).

| Run | Command | Run name |
| :--- | :--- | :--- |
| `solo` | `tools/run.sh solo flash 8` | `solo-msa_v2-gemini-3-8-flash-flash-ref` |
| `coop` (messaging only) | `tools/run.sh coop flash 4` | `coop-msa_v2-gemini-3-8-flash-flash-ref` |
| `coop --git` | `tools/run.sh coop flash 4 --git` | `coop-msa_v2-git-gemini-3-8-flash-flash-ref` |
| `team` | `tools/run.sh team flash 4` | `team-msa_v2-gemini-3-8-flash-flash-ref` |
| `coop --git` at `low` thinking | `AGENT_CONFIG=configs/reference/low.yaml RUN_SUFFIX=ref-low tools/run.sh coop flash 4 --git` | `coop-msa_v2-git-gemini-3-8-flash-flash-ref-low` |

Use `flash_10` (10 pairs) to check that a new feature works at all, and `flash` (50 pairs) or `core` (10 harder pairs) for results. Results move between runs: when the same config was rerun on a different provider, 4 to 6 of the 50 pairs changed outcome, so compare arms pair by pair and repeat runs before calling a difference real.

## Changing the Setup

- **Interventions:** copy `configs/reference/medium.yaml` (or `low.yaml` / `high.yaml` when sweeping thinking level) to `configs/variants/<name>_<level>.yaml`, add only the new flag (off by default in the code), and run with `AGENT_CONFIG=configs/variants/<name>_<level>.yaml RUN_SUFFIX=<name>` (plus `MODEL=vertex_ai/<model>` when sweeping across Flash models). Compare it with a reference run on the same model, thinking level, subset, provider, and concurrency.
- **Old configs:** `configs/gemini_3_8_flash_high.yaml` (100 steps, 28K compaction, `high` thinking) and most of `configs/variants/` produced earlier results and are kept only to reproduce them.
