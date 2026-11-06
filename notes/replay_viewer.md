# 3-Pane Log Replay Viewer

An interactive visual studio to inspect and scrub multi-agent CooperBench trajectories side-by-side, inspect inter-agent messages and live delivery buffering, track active thread boards across context compactions, and view file diffs and command execution feeds.

## Quick Start

Launch the viewer web server from the repository root:

```bash
uv run --frozen python -m tools.replay_viewer.server --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in any modern browser.

### Command-Line Options

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--port <int>` | `8765` | Port to bind the local HTTP server. |
| `--host <ip>` | `127.0.0.1` | Network interface to bind. |
| `--repo-root <path>` | Auto-detected | Repository root directory holding `logs/`, `results/`, and `dataset/`. Works automatically in both standard checkouts and git worktrees. |
| `--export-html <file.html>` | _None_ | Compiles a standalone, self-contained HTML bundle with preloaded trajectories and exits without starting the server. |
| `--runs <patterns...>` | _All_ | Optional run-name filters for `--export-html` (for example, `--runs delivery-timing stepcounter`). |
| `--pairs <patterns...>` | _All_ | Optional task-pair filters for `--export-html` (for example, `--pairs outlines 1655`). |

## Standalone HTML Export

To generate a portable, self-contained report that runs in any browser without needing Python or network access:

```bash
# Export all runs for a specific showcase task pair:
uv run --frozen python -m tools.replay_viewer.server \
  --export-html replay_outlines_1655.html \
  --pairs outlines 1655

# Export a comparison across baseline and delivery-timing:
uv run --frozen python -m tools.replay_viewer.server \
  --export-html replay_delivery_vs_baseline.html \
  --runs delivery-timing stepcounter \
  --pairs jinja 1559
```

The exported HTML file contains all pre-compiled timeline events, chat bubbles, and diffs, so it can be emailed or opened locally by double-clicking.

### Pre-Built Midpoint Showcase (`demos/midpoint_showcase.html`)

[`demos/midpoint_showcase.html`](../demos/midpoint_showcase.html) bundles 12 pre-compiled replays (`3` task pairs × `4` runs spanning both the constrained `3-flash · 28K · 100 steps · low` regime and the frozen `3.8-flash · 128K · 500 steps · medium` reference regime) so teammates and course staff can open it directly in a browser without local `logs/`:

| Task Pair | Highlighted Comparison | Takeaway |
| :--- | :--- | :--- |
| `pallets_click_task` (`#2068 f6_f7`) | `Combined Arms` (`✓ PASS`) vs. `Intents` (`✗ FAIL`, `clean`) at `3.8-flash · 128K · 500 steps · medium` | `Combined Arms` (Frame 33) demonstrates live inbox buffering (`⏸ Held`), pinned threads across compaction, and speech-act tags; `Intents` (`m19` + `Final Patch` tab) shows why single-line shared-call-site conflict avoidance (`ed = Editor(...)`) still causes `0`-conflict test failures under symmetric branch isolation. |
| `openai_tiktoken_task` (`#0 f3_f6`) | `Baseline` (`✗ FAIL`) vs. `Delivery Timing` (`✓ PASS`) at `3-flash · 28K · 100 steps · low` | Unbuffered mid-edit arrivals in `Baseline` trigger `5` mid-repair compactions (`152` steps, merge conflict), whereas holding messages until `rc=0` verification passes cleanly in `70` steps (`16` msgs). |
| `dottxt_ai_outlines_task` (`#1655 f7_f10`) | `Baseline` (`✗ FAIL`) vs. `Delivery Timing` (`✓ PASS`) at `3-flash · 28K · 100 steps · low` | Buffering mid-edit arrivals cuts reactive chatter (`16` → `6` messages) and flips a merge conflict into a clean pass. |

To regenerate [`demos/midpoint_showcase.html`](../demos/midpoint_showcase.html) from local `logs/`:

```bash
uv run --frozen python -m tools.replay_viewer.server \
  --export-html demos/midpoint_showcase.html \
  --runs \
    coop-msa_v2-git-gemini-3-flash-flash-low-stepcounter \
    coop-msa_v2-git-gemini-3-flash-flash-low-delivery-timing \
    coop-msa_v2-git-gemini-3-8-flash-flash-ref-intents \
    coop-msa_v2-git-gemini-3-8-flash-flash-ref-comm-combined \
  --pairs \
    pallets_click_task:2068:f6_f7 \
    openai_tiktoken_task:0:f3_f6 \
    dottxt_ai_outlines_task:1655:f7_f10
```

## Local Run Logs (`logs/`)

Raw logs (`logs/<run_name>/`) are gitignored and kept on local disk (see [logs_archive.md](logs_archive.md)). When `logs/<run_name>/` is present locally, the replay viewer discovers the run automatically on startup or page refresh (`/api/runs`); to share a visual trace without copying raw `logs/`, use `--export-html` above.

## 3-Pane Layout Overview

The studio layout is designed for side-by-side behavioral analysis:

### Top Header & Cross-Run Regime Comparison
- **Active Run Badges**: Displays the setting (`coop --git`, `coop (no git)`, `team`), model, budget regime (`128K · 500 steps · medium` vs. `28K · 100 steps · low`), wall duration, and total cost.
- **`COMPARE RUNS:` Selector**: Lists every locally logged run for the selected task pair, grouped by model and budget regime, with each button showing pass/fail status, intervention arm, model/budget regime badge, merge outcome, and message count.

### 1. Left & Right Panes (Agent 1 & Agent 2)
- **Header**: Shows the assigned feature ID, title, and collapsible specification (`feature.md`).
- **Live Status Badges**: Step number, current action phase (`Explore`, `Edit`, `Test/Git`, `Message`), exit returncode (`rc=0` vs `rc!=0`), token usage, and context compactions completed.
- **Buffered Inbox Tray**: Highlights incoming messages currently held in the agent's buffer during active file editing or error fixing, displaying the hold reason (such as `recipient mid-edit`) and elapsed hold steps.
- **View Toggle**:
  - **Live Steps & Feed**: Displays the agent's thought process, executed bash command, and terminal output.
  - **Final Patch**: Shows the syntax-colored unified git diff (`agent.patch`) submitted by the agent.

### 2. Center Pane (Coordination & Thread Board)
- **Active Thread Board (Sticky Top)**: Tracks open versus resolved coordination threads (for example, `m1`, `m2`) and outstanding proposals/requests. When harness thread-pinning is active, shows agreements preserved across context compactions.
- **Chat Stream**: Chronological speech-act conversation feed with color-coded intent tags (`Proposal`, `Request`, `Response`, `ACK`, `FYI`), reply-to links (`↩ m1`), and delivery status indicators (`Sent @ Step X` -> `⏸ Held Y steps` -> `✓ Delivered @ Step Z`).
- **Inline Event Dividers**: Emits visual markers when an agent compacts its context or receives harness nudges (for example, submit nudges or pre-exit flush notices).

### 3. Bottom Scrubber & Transport Controls
- **Scrubber Track**: Clickable progress bar spanning all frames (0 to T-1) with color-coded markers for messages, delivery flushes, compactions, and harness nudges.
- **Transport Controls**: Play/Pause (`Space`), Step Previous (`Left Arrow`), Step Next (`Right Arrow`), and adjustable playback speeds (`0.5x` to `10x`).
- **Jump to Key Moments**: Instant jumps to the first message, first held message, delivery flush boundary, compaction, or final submission.
