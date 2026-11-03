# Communication Interventions

Setup reference for the three opt-in communication mechanisms in `mini_swe_agent_v2` ([`communication.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/communication.py), wired in [`default.py`](../src/cooperbench/agents/mini_swe_agent_v2/agents/default.py) and [`messaging.py`](../src/cooperbench/agents/mini_swe_agent_v2/connectors/messaging.py)). All flags default to `false` so runs without them match the reference harness.

## Why Three Atomic Mechanisms

Baseline `coop --git` traces show three recurring communication failures:

1. **Mid-edit interruption:** non-blocking colleague messages are injected at the start of every turn, including right after a failed `sed` edit or red test run, derailing local debugging or getting ignored while the agent fixes syntax errors.
2. **Thread amnesia across turns and compactions:** flat `[Message from agent2]: ...` text has no message IDs or open/resolved state, so questions and file-boundary agreements scroll out of recent turns or get compressed away when the 28K-token compaction trigger fires.
3. **Ambiguous obligations and status noise:** status updates, proposals, and blocking questions look identical on the wire, so receivers fail to prioritize concrete requests or exit while a live colleague's proposal is still unanswered.

Following an ablation design, each intervention is two lines conceptually, toggles independently, and composes cleanly when combined.

## 1. Message Delivery Timing

- **Two-line summary:** Buffer non-blocking incoming messages while an agent is mid-edit or debugging a failing command, and deliver them at natural workflow boundaries (after a clean test/`git`/`gh pr` run, a messaging turn, or an explore-to-edit transition) or after a bounded hold ceiling (`4` steps). Blocking `--wait` messages (and urgent `Request`/`Proposal` intents when combined) bypass the buffer immediately.
- **Lineage:** Human-computer interaction research on *opportune moments for interruption* at task boundaries (Iqbal & Bailey, CHI 2007/2008) and turn-boundary message queuing in modern coding-agent harnesses (queued inbox flushing between tool/verification phases rather than mid-repair).
- **Flags (`agent:`):**
  - `delivery_timing: true` (default `false`)
  - `delivery_max_hold_steps: 4` — forced-flush ceiling in steps; any buffered messages also flush before exit in `_continue_after_exit()` so nothing is dropped when an agent submits.
  - `delivery_boundary_mode: natural | periodic` — `natural` flushes at clean workflow boundaries; `periodic` flushes strictly every `delivery_max_hold_steps` steps as a counterfactual control testing whether *when* messages arrive matters beyond simple batching.
- **Configs:** `configs/variants/delivery_timing_medium.yaml`, `configs/variants/delivery_timing_ref_low.yaml` (500-step / 128K reference setup); `configs/variants/delivery_timing_high.yaml`, `configs/variants/delivery_timing_low.yaml`, and `delivery_timing_periodic_{high,low}.yaml` (100-step / 28K ablation setup). No task-prompt change is needed.

## 2. Message Board / Threading

- **Two-line summary:** Assign monotonic run-scoped IDs (`m1`, `m2`, ...) in Redis and track `open` vs. `resolved` threads via validated `--reply-to <id>` and `--resolve` flags on `send_message`. Surface open threads in a compact footer at the end of each turn's observation, and pin both open threads and resolved agreements onto compaction summaries (`## ACTIVE THREAD BOARD (HARNESS-PINNED)`).
- **Lineage:** Persistent structured state in classic Blackboard architectures (Erman et al., Hearsay-II, 1980; Nii, 1986), issue-tracker / Slack thread resolution workflows, and harness-pinned state blocks that survive context compaction (extending the same principle as `step_counter`).
- **Contract & flags (`agent:`):**
  - `message_threading: true` (default `false`)
  - Every root message opens a thread (`m1`, `m2`, ...), except `--intent FYI` when intents are also enabled. Replying with `--reply-to m1` keeps `m1` `open`; adding `--resolve` transitions `m1` to `resolved`. Unknown `--reply-to` IDs or `--resolve` without `--reply-to` return exit code `1` with known IDs listed.
  - `thread_pin_mode: every_turn | compaction_only` (default `every_turn`) and `thread_max_pinned: 3`.
  - `thread_require_resolved_on_submit: false` — opt-in pre-submit reminder if an incoming thread from a still-running colleague remains open.
- **Configs:** `configs/variants/message_threading_medium.yaml` (500-step / 128K reference setup); `configs/variants/message_threading_high.yaml`, `configs/variants/message_threading_low.yaml` (100-step / 28K ablation setup).

## 3. Message Intent Tags

- **Two-line summary:** Require an explicit speech-act tag (`--intent <Proposal|Request|Response|ACK|FYI>`) on `send_message`, sort incoming `Request`/`Proposal` messages ahead of `FYI` updates on receipt, and remind an exiting agent once if a live colleague's `Request` or `Proposal` is still unanswered.
- **Lineage:** Speech-act agent communication languages — KQML (Finin et al., 1994), FIPA-ACL (2002), and Winograd & Flores's *Coordinator* conversation-for-action state machine (1986) — adapted to lightweight CLI flags for tool-calling LLM coding agents.
- **Flags (`agent:`):**
  - `message_intents: true` (default `false`) — validates `--intent` (in any flag position, with `[Intent]` / `Intent:` body-prefix fallback). When combined with threading, `--intent ACK --reply-to <id>` automatically resolves `<id>`, and `--intent FYI` does not open a thread.
  - `intent_filter_fyi: false` — optional receiver-side filter suppressing non-blocking `FYI` updates to test bandwidth vs. coordination tradeoffs.
  - `intent_presubmit_check: true` in intent configs (default `false` in `AgentConfig`) — one-shot pre-submit check in `_nudge_unsubmitted()` for unanswered live-peer `Request`/`Proposal` obligations.
- **Configs:** `configs/variants/message_intents_medium.yaml`, `configs/variants/message_intents_ref_low.yaml`, and `configs/variants/comm_combined_{medium,ref_low}.yaml` (500-step / 128K reference setup); `configs/variants/message_intents_{high,low}.yaml` and `configs/variants/comm_combined_{high,low}.yaml` (100-step / 28K ablation setup).

## Results

Full ablation and 50-pair `flash` confirmation results across `gemini-3-flash-preview` and `gemini-3.8-flash` are in [communication_ablations.md](communication_ablations.md).
