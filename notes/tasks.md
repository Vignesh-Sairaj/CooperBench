# Tasks

Open work for the project. Put your GitHub handle in **Owner** when you pick something up, and move it to **Done** with a link to the note or result when finished.

## Open

| Task | Owner | Details |
| :--- | :--- | :--- |
| Pre-pull the `flash_10` task images | | Each teammate on their own machine: `tools/pull_images.sh flash_10`. |
| Repeat the key comparisons on more pairs | | In progress on the 50-pair `flash` subset: `solo` (`low` 36/50, `high` 34/50), `coop --git` (`low` 30/50, `high` 34/50), `team` (`low` 22/50), and `solo` `low` without the step counter (32/50) are done; `medium` thinking (`solo`, `coop --git`) and messaging-only `coop` (`low`) are running. See [saturation_flash.md](saturation_flash.md). |
| Review the `results/` format | | See [results_format.md](results_format.md), [`tools/run.sh`](../tools/run.sh), and [`tools/export_results.py`](../tools/export_results.py). Every run is listed in [runs.md](runs.md). |
| Join the Hugging Face logs archive | | Each teammate: accept the org invite, set `HF_TOKEN`, and test a download of a `setup-checks/` folder. See [logs_archive.md](logs_archive.md). |
| Team-size experiment with 3 and 4 agents (later) | | `coop` and `team` already start one agent per feature (`-f 1,2,3` runs 3 agents), and `team3_250` / `team3_all` list three-feature groups. Blocker: the grader only checks two features (the local path uses the first two; the batch path crashes on three). Extend it to merge all patches and require every feature's tests to pass. |
| Send the submit-reminder crash fix upstream | | Fixed in our fork (see [harness_limits.md](harness_limits.md)). Rebase the fix onto the latest upstream commit and open a pull request on `cooperbench/CooperBench`. |
| Confirm `HIGH` thinking with the team | | Our status report left the thinking setting open. Share [model_config.md](model_config.md). |
| Keep agents' "still running" signal alive during long model calls | | During peak hours a Vertex AI call can wait up to 10 minutes; the signal is refreshed only between turns and expires after 600 seconds, so partners get false "[colleague] is no longer running" notices. Refresh it while a model call is in flight. Plain bug fix; also worth sending upstream. See [model_config.md](concurrency.md#reference-concurrency-vertex-ai). |
| Fix `team` grading (after the midpoint) | | The lead's combined work is never graded. Pause `team` runs until fixed. See [details](#fix-team-grading). |
| Fix shared-line conflict-avoidance workarounds / designated integrator (after the midpoint) | | In `coop --git`, the prompt tells agents that their branches must merge with zero `git merge` conflicts while containing only their own work. When two features must add arguments to the same single-line call (`pallets_click_task/2068`), agents avoid editing the shared line by setting attributes after construction (`ed.<attr> = <attr>`), which fails constructor-mocking tests (causing 4 of 5 `solo`-only losses on `lite`). Test an opt-in designated-integrator or shared-call-site rule. See [details](#fix-shared-line-conflict-avoidance-workarounds). |

## Done

| Task | Owner | Result |
| :--- | :--- | :--- |
| Local setup: Docker, Redis, Python env, all tests passing | | 447 tests pass. |
| First end-to-end run (one `coop --git` pair, no config file) | | Setup works; the pair failed (merge conflict). |
| Check `HIGH` thinking on one pair | | Config works (about 800 reasoning tokens per call vs. 0 without it). Pair still failed: feature 1 passed, agent2 never wrote a patch for feature 2. |
| Pick default model and thinking level | | [model_config.md](model_config.md) |
| Set up the raw logs archive | | Private Hugging Face dataset with every run's logs. See [logs_archive.md](logs_archive.md). |
| Write the run and export tools | | [`tools/run.sh`](../tools/run.sh) starts a run and records how it was launched; [`tools/export_results.py`](../tools/export_results.py) writes `results/<run_name>/`. |
| Find how many agents fit per API key | | The 1M input-tokens-per-minute limit per GCP project sets the limit, not the machine: about 8 agents per key at 28K compaction, 4 at 64K. See [model_config.md](concurrency.md). |
| Step limit and compaction experiments on `flash_10` | | 9 runs across `solo`, `coop`, and `coop --git`. See [baseline_ablation_flash10.md](baseline_ablation_flash10.md). |
| Run experiments in parallel on several API keys | | `KEY_SLOT` in `tools/run.sh`. See [workflow.md](workflow.md). |
| Four baseline settings on `flash_10` | | `solo`, `coop`, `coop --git`, and `team` done. See [runs.md](runs.md). |
| Model, thinking level, and step counter experiments | | See [model_thinking_stepcounter_flash10.md](model_thinking_stepcounter_flash10.md). |
| Decide the standard setup for all experiments | | Frozen 2026-11-02: `gemini-3.8-flash` on Vertex AI, `medium` thinking, 500 steps, 128K compaction, step counter. See [model_config.md](model_config.md#reference-setup). |

## Task Details

### Fix `team` grading

**Problem in one sentence:** in `team` mode the lead is told to combine both features in a local file that the grader never reads, so the lead's integration work is thrown away and `team` scores far below two peers.

**How `team` mode works.** One agent is the lead and one is the member. Each implements one feature. They share a folder (`/workspace/shared/`), a task list, and messaging, but no shared git server unless `--git` is passed. The idea is that the lead integrates both features into one result.

**Why the lead gets contradicting instructions.** With the `mini_swe_agent_v2` harness, each agent's prompt is the normal `coop` task prompt with the `team` role prompt appended after it ([`adapter.py`](../src/cooperbench/agents/mini_swe_agent_v2/adapter.py)):

1. The `coop` prompt ([`coop.yaml`](../src/cooperbench/agents/mini_swe_agent_v2/config/coop.yaml)) says the pushed pull request is the submission and that it must contain only the agent's own work, without the colleague's changes.
2. The `team` lead prompt ([`team_harness/prompt.py`](../src/cooperbench/team_harness/prompt.py)) says the opposite: apply each member's patch from `/workspace/shared/<agent>.patch`, check that both features are in the working tree, and then write `git diff > patch.txt`. It warns that submitting only the lead's own feature fails the team.

**Why `patch.txt` is ignored.** The `team` prompt was written for the command-line agent harnesses, which grade a local `patch.txt`. `mini_swe_agent_v2` grades only what each agent pushed to its git remote (`git_connector.submitted_patch()` in `adapter.py`): the shared server with `--git`, otherwise a private repository inside the agent's own sandbox. Upstream made that change on purpose, so that agents cannot submit work their partner never saw.

**How grading then plays out** ([`eval/sandbox.py`](../src/cooperbench/eval/sandbox.py)). The grader merges the lead's and the member's pushed patches with a plain three-way git merge:

- **Clean merge:** both feature test suites run on the merged code, and that result is final.
- **Merge conflict, or a patch that does not apply:** the grader falls back to testing the lead's patch alone against both test suites.

So the lead loses either way:

- **Lead follows the `coop` prompt** (pushes only its own feature; the combined code sits unused in `patch.txt`): if the two branches conflict, the fallback tests a lead patch that has only one feature, and the pair fails.
- **Lead follows the `team` prompt and pushes the combined code:** its branch now overlaps the member's branch, so the merge almost always conflicts. The pair passes only through the lead-alone fallback, and only if the combined code is right.

**Evidence.** On the 50-pair `flash` subset at `low` thinking, 500 steps ([summary](../results/team-msa_v2-gemini-3-8-flash-flash-saturation-low/summary.md), [saturation_flash.md](saturation_flash.md)):

- `team` passed 22/50, vs. 30/50 for `coop --git` and 36/50 for `solo` with the same setup.
- 30 of 50 pairs had merge conflicts (0 of 50 in `coop --git`), and 9 of the 22 passes came through the lead-alone fallback.
- All 50 leads wrote `patch.txt`. On 7 pairs that `solo` solves, the lead pushed only its own feature while `patch.txt` held both: `dottxt_ai_outlines_task/1655` (7,10), `openai_tiktoken_task/0` (3,6) and (6,8), `pallets_click_task/2068` (1,6) and (5,7), `pallets_jinja_task/1465` (2,3), and `pallets_jinja_task/1621` (1,6). That is half of `team`'s 14 losses against `solo`.
- Earlier `flash_10` runs show the same pattern: `team` 4/10 and 5/10, vs. 8/10 for `coop --git`.

**A second, smaller bug (message counts).** `_spawn_team_agent` in [`runner/team.py`](../src/cooperbench/runner/team.py) does not pass the agent's sent messages back to the runner, so `messages_sent` in `result.json` reads 0 on 49 of 50 pairs. The trajectories show the agents actually sent 1 to 31 messages per pair (median 14.5). This affects only logging, not scores.

**Proposed fix** (behind a new flag that is off by default, so runs without it still match upstream):

1. Make the instructions agree. With the flag on, tell the lead to bring the member's work into its own branch and push the combined code as its pull request. The member keeps pushing only its own feature.
2. Make the grader match. With the flag on, grade the lead's pushed branch alone against both test suites, the same check the fallback already does, instead of merging it with the member's branch first. Grading the lead's `patch.txt` instead would also work, but it brings back the problem upstream removed (graded work the partner never saw), so pushing to git is preferred.
3. Pass sent messages through in `runner/team.py` so `messages_sent` is correct. This one is a plain bug fix and can go upstream without a flag.

**Done when:**

- Unit tests cover the new prompt and grading path, and a run with the flag off gives the same prompts and grading as today.
- `team` is rerun with the flag on, on `flash_10` and then on `flash` at the team's standard thinking level, and compared pair by pair with `coop --git` and `solo`.
- Each of the 7 pairs listed above either passes or fails for a reason other than the unpushed integration.
- An upstream issue or pull request is opened for the mismatch and the message-count bug.

### Fix shared-line conflict-avoidance workarounds

**Problem in one sentence:** when two features must add parameters to the same single-line function or constructor call, `coop.yaml`'s rules ("zero `git merge` conflicts" plus "do not commit your colleague's changes into your branch") trap agents into working around the constructor call, which breaks hidden unit tests that mock the constructor.

**Why the prompt contradicts the test on single-line calls.** Git's three-way merge works line by line. In `pallets_click_task/2068`, `ed = Editor(editor=editor, env=env, require_save=require_save, extension=extension)` in `src/click/termui.py` is on a single line in the base commit. If `agent1` adds its keyword argument to that line on its branch and `agent2` adds its own keyword argument to that same line on its branch, `git merge` always reports a conflict on that line—unless both branches replace that line with the exact same combined call (or one agent merges and integrates both). However, `coop.yaml` explicitly instructs agents: *"your PR must contain only your own work — do not commit your colleague's changes into your branch."* To satisfy both rules at once, the agents agree in chat that only one agent will edit the `Editor(...)` call line and the other will leave the call line untouched and set `ed.<attr> = <attr>` on the next line after construction. That keeps `git merge` conflict-free, but fails any hidden test that mocks `Editor` and asserts the new keyword argument was passed into `Editor(...)`.

**Evidence.** On the 100-pair `lite` reference run ([saturation_flash.md](saturation_flash.md#reference-settings-solo-vs-coop---git), full case study in [pallets_click_2068.md](pallets_click_2068.md)), 4 of the 5 pairs where `solo` beat `coop --git` are `pallets_click_task/2068` pairs (`(5,11)`, `(6,7)`, `(7,10)`, `(9,11)`), and 7 of the 11 `pallets_click_task/2068` pairs in `coop --git` failed for this exact reason. Outside `pallets_click_task`, `coop --git` slightly leads `solo` (`63/80` vs. `61/80`).

**Candidate interventions** (behind an opt-in config flag, off by default):

1. **Allow shared-line co-editing in `coop --git`:** permit peers to agree on the exact combined signature/call-site line (and put the identical combined line on both branches so three-way `git merge` resolves it cleanly) when two features modify the same function signature or constructor call, while keeping feature bodies separate.
2. **Designated integrator (one of the two peers, or after fixing `team` grading):** have both agents implement and test their own features first, then designate one agent (for example, `agent1` / the `team` lead, or a lightweight post-submission merger agent) to merge both branches, resolve shared call sites directly in the constructor call, run both test suites, and push the integrated result.
