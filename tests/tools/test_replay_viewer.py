"""Unit tests for the CooperBench 3-pane log replay viewer.

Tests trajectory segment stitching, deduplication across context compactions,
message lifecycle matching, delivery timing held-step calculations, thread board
tracking, real run compilation, and HTTP API endpoints.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from tools.replay_viewer.compiler import (
    CompactionEvent,
    MessageEvent,
    _apply_message_to_threads,
    _classify_action,
    _extract_agent_steps,
    _match_and_reconstruct_messages,
    _stitch_trajectory,
    compile_pair_replay,
    list_pairs_index,
    list_runs,
)
from tools.replay_viewer.server import ReplayRequestHandler


def test_classify_action() -> None:
    """Verifies that classify_action correctly identifies coarse workflow phases."""
    assert _classify_action("pytest tests/test_core.py") == "verify_or_git"
    assert _classify_action("git status") == "verify_or_git"
    assert _classify_action("git diff") == "verify_or_git"
    assert _classify_action("cat <<'EOF' > foo.py\ncode\nEOF") == "file_edit"
    assert _classify_action("sed -i 's/a/b/' bar.go") == "file_edit"
    assert _classify_action("ls -la && cat file.txt") == "read_explore"
    assert _classify_action("send_message agent2 'hello'") == "message"
    assert _classify_action("") == "none"
    assert _classify_action("echo 123") == "other"


def test_segment_stitching_and_deduplication() -> None:
    """Verifies that solver turns are deduplicated and compaction events are extracted."""
    # Synthetic trajectory with 2 solver segments and 1 summarizer segment.
    segment0_msgs = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "task prompt"},
        {
            "role": "assistant",
            "content": "thought 1",
            "extra": {
                "actions": [{"command": "ls -R"}],
                "response": {"id": "rid_1", "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
                "timestamp": 100.0,
                "cost": 0.01,
            },
        },
        {"role": "tool", "content": "files list", "extra": {"returncode": 0, "raw_output": "files list"}},
        {
            "role": "assistant",
            "content": "thought 2",
            "extra": {
                "actions": [{"command": "cat mux.go"}],
                "response": {"id": "rid_2", "usage": {"prompt_tokens": 200, "completion_tokens": 20}},
                "timestamp": 105.0,
                "cost": 0.02,
            },
        },
        {"role": "tool", "content": "mux code", "extra": {"returncode": 0, "raw_output": "mux code"}},
    ]

    summarizer_msgs = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "summarize please"},
        {
            "role": "assistant",
            "content": "## FILE MAP\n- `mux.go`: Modified\n\n## ACTIVE THREAD BOARD (HARNESS-PINNED)\nOpen threads:\n- m1: open",
            "extra": {"timestamp": 110.0},
        },
    ]

    # Segment 2 solver repeats turn 2 (rid_2) due to compaction_keep_recent_turns=1, then adds turn 3 (rid_3)
    segment2_msgs = [
        {"role": "system", "content": "system"},
        {
            "role": "assistant",
            "content": "summary content",
            "extra": {"summary": True, "timestamp": 111.0},
        },
        {
            "role": "assistant",
            "content": "thought 2 duplicate",
            "extra": {
                "actions": [{"command": "cat mux.go"}],
                "response": {"id": "rid_2", "usage": {"prompt_tokens": 200, "completion_tokens": 20}},
                "timestamp": 105.0,
                "cost": 0.02,
            },
        },
        {"role": "tool", "content": "mux code", "extra": {"returncode": 0, "raw_output": "mux code"}},
        {
            "role": "assistant",
            "content": "thought 3",
            "extra": {
                "actions": [{"command": "pytest"}],
                "response": {"id": "rid_3", "usage": {"prompt_tokens": 300, "completion_tokens": 30}},
                "timestamp": 120.0,
                "cost": 0.03,
            },
        },
        {"role": "tool", "content": "all tests passed", "extra": {"returncode": 0, "raw_output": "all tests passed"}},
    ]

    raw_traj = {
        "segments": [
            {"kind": "solver", "messages": segment0_msgs},
            {"kind": "summarizer", "messages": summarizer_msgs},
            {"kind": "solver", "messages": segment2_msgs},
        ]
    }

    stitched_turns, compactions = _stitch_trajectory(raw_traj, "agent1")

    # Should extract exactly 1 CompactionEvent with pinned board preserved.
    assert len(compactions) == 1
    comp = compactions[0]
    assert isinstance(comp, CompactionEvent)
    assert comp.agent_id == "agent1"
    assert "FILE MAP" in comp.summary
    assert comp.pinned_board is not None
    assert "ACTIVE THREAD BOARD (HARNESS-PINNED)" in comp.pinned_board

    # Assistant turns extracted in agent steps should be exactly 3: rid_1, rid_2, rid_3.
    steps, _ = _extract_agent_steps(stitched_turns, "agent1")
    assert len(steps) == 3
    assert [s.command for s in steps] == ["ls -R", "cat mux.go", "pytest"]
    assert steps[0].action_phase == "read_explore"
    assert steps[1].action_phase == "read_explore"
    assert steps[2].action_phase == "verify_or_git"


def test_delivery_timing_held_steps_calculation() -> None:
    """Verifies that held steps and hold/flush reasons are computed accurately."""
    # Synthetic Agent 1 and Agent 2 steps.
    # Agent 1 sends a message at ts=110.0 (step 2).
    # Agent 2 at ts=110.0 was at step 1 (editing file, ts=105.0).
    # Agent 2 verifies at step 3 (ts=125.0) which satisfies the natural boundary and delivers.
    from tools.replay_viewer.compiler import AgentStep

    a1_steps = [
        AgentStep(
            agent_id="agent1",
            step_number=1,
            timestamp=100.0,
            thought=None,
            command="git status",
            action_phase="verify_or_git",
            touched_files=(),
            returncode=0,
            output="",
            diff_snippet=None,
            prompt_tokens=100,
            completion_tokens=10,
            cumulative_cost=0.01,
            footers=(),
        ),
        AgentStep(
            agent_id="agent1",
            step_number=2,
            timestamp=110.0,
            thought=None,
            command="send_message agent2 'here is my plan'",
            action_phase="message",
            touched_files=(),
            returncode=0,
            output="Message sent to agent2 (id: m1, intent: FYI)",
            diff_snippet=None,
            prompt_tokens=150,
            completion_tokens=15,
            cumulative_cost=0.02,
            footers=(),
        ),
    ]

    a2_steps = [
        AgentStep(
            agent_id="agent2",
            step_number=1,
            timestamp=105.0,
            thought=None,
            command="cat <<'EOF' > mod.py\ncode\nEOF",
            action_phase="file_edit",
            touched_files=("mod.py",),
            returncode=0,
            output="",
            diff_snippet=None,
            prompt_tokens=100,
            completion_tokens=10,
            cumulative_cost=0.01,
            footers=(),
        ),
        AgentStep(
            agent_id="agent2",
            step_number=2,
            timestamp=115.0,
            thought=None,
            command="python mod.py",
            action_phase="other",
            touched_files=(),
            returncode=1,
            output="SyntaxError",
            diff_snippet=None,
            prompt_tokens=150,
            completion_tokens=15,
            cumulative_cost=0.02,
            footers=(),
        ),
        AgentStep(
            agent_id="agent2",
            step_number=3,
            timestamp=125.0,
            thought=None,
            command="pytest tests/",
            action_phase="verify_or_git",
            touched_files=(),
            returncode=0,
            output="PASS",
            diff_snippet=None,
            prompt_tokens=200,
            completion_tokens=20,
            cumulative_cost=0.03,
            footers=(),
        ),
    ]

    config_flags = {
        "delivery_timing": True,
        "delivery_max_hold_steps": 4,
        "delivery_boundary_mode": "natural",
        "message_threading": True,
        "message_intents": True,
    }

    matched = _match_and_reconstruct_messages(a1_steps, a2_steps, config_flags)
    assert len(matched) == 1
    m = matched[0]
    assert m.id == "m1"
    assert m.sender == "agent1"
    assert m.recipient == "agent2"
    assert m.receiver_step_at_send == 1
    assert m.delivered_step == 3
    assert m.held_steps == 2
    assert m.delivery_status == "held"
    assert "mid-edit" in m.hold_reason
    assert "verification boundary" in m.flush_reason


def test_thread_board_and_intent_tracking() -> None:
    """Verifies that threads track open vs resolved status and reply chains."""
    threads = {}
    m1 = MessageEvent(
        id="m1",
        sender="agent1",
        recipient="agent2",
        content="Shall we modify routes.go?",
        intent="Proposal",
        reply_to=None,
        resolve=False,
        wait=False,
        sent_step=2,
        sent_at=10.0,
        receiver_step_at_send=1,
        receiver_action_at_send="explore",
        receiver_rc_at_send=0,
        delivered_step=3,
        delivered_at=15.0,
        held_steps=2,
        hold_reason="",
        flush_reason="",
        delivery_status="held",
    )
    _apply_message_to_threads(threads, m1)
    assert "m1" in threads
    assert threads["m1"].status == "open"
    assert threads["m1"].last_intent == "Proposal"

    # Agent 2 replies resolving the thread
    m2 = MessageEvent(
        id="m2",
        sender="agent2",
        recipient="agent1",
        content="Yes, I agree. Done.",
        intent="ACK",
        reply_to="m1",
        resolve=True,
        wait=False,
        sent_step=4,
        sent_at=20.0,
        receiver_step_at_send=3,
        receiver_action_at_send="verify",
        receiver_rc_at_send=0,
        delivered_step=4,
        delivered_at=22.0,
        held_steps=1,
        hold_reason="",
        flush_reason="",
        delivery_status="held",
    )
    _apply_message_to_threads(threads, m2)
    assert threads["m1"].status == "resolved"
    assert threads["m1"].last_sender == "agent2"
    assert len(threads["m1"].history) == 2


@pytest.fixture()
def synthetic_repo_root(tmp_path: Path) -> Path:
    """Creates a hermetic repo root with synthetic logs, results, and dataset for replay compilation."""
    root = tmp_path / "repo"
    run_name = "coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"
    repo = "dottxt_ai_outlines_task"
    task_id = "1655"

    pair_dir = root / "logs" / run_name / "coop" / repo / task_id / "f7_f10"
    pair_dir.mkdir(parents=True, exist_ok=True)
    res_dir = root / "results" / run_name
    res_dir.mkdir(parents=True, exist_ok=True)

    (root / "logs" / run_name / "launch.json").write_text(
        json.dumps(
            {
                "run_name": run_name,
                "setting": "coop",
                "subset": "flash_10",
                "git_enabled": True,
                "agent_config": "delivery_timing: true\ndelivery_max_hold_steps: 4\ndelivery_boundary_mode: natural\nstep_counter: true\n",
            }
        ),
        encoding="utf-8",
    )
    (res_dir / "run.json").write_text(
        json.dumps(
            {
                "run_name": run_name,
                "setting": "coop",
                "subset": "flash_10",
                "git_enabled": True,
                "passed": 1,
                "total": 1,
                "cost_usd": 0.42,
            }
        ),
        encoding="utf-8",
    )
    (res_dir / "pairs.csv").write_text(
        "repo,task_id,feature_a,feature_b,both_passed,merge_status,messages_sent,steps_total,cost_usd\n"
        f"{repo},{task_id},7,10,true,clean,2,4,0.42\n",
        encoding="utf-8",
    )
    (pair_dir / "result.json").write_text(
        json.dumps(
            {
                "repo": repo,
                "task_id": 1655,
                "features": [7, 10],
                "messages_sent": 2,
                "total_steps": 4,
                "total_cost": 0.42,
            }
        ),
        encoding="utf-8",
    )
    (pair_dir / "eval.json").write_text(
        json.dumps({"both_passed": True, "merge": {"status": "clean"}}),
        encoding="utf-8",
    )

    traj1 = {
        "segments": [
            {
                "kind": "solver",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "task"},
                    {
                        "role": "assistant",
                        "content": "send plan",
                        "extra": {
                            "actions": [{"command": "send_message agent2 'plan for f7'"}],
                            "response": {"id": "a1_1", "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
                            "timestamp": 100.0,
                            "cost": 0.1,
                        },
                    },
                    {
                        "role": "tool",
                        "content": "Message sent to agent2 (id: m1, intent: Proposal)",
                        "extra": {"returncode": 0, "raw_output": "Message sent to agent2 (id: m1, intent: Proposal)"},
                    },
                    {
                        "role": "assistant",
                        "content": "verify",
                        "extra": {
                            "actions": [{"command": "pytest"}],
                            "response": {"id": "a1_2", "usage": {"prompt_tokens": 120, "completion_tokens": 10}},
                            "timestamp": 120.0,
                            "cost": 0.11,
                        },
                    },
                    {
                        "role": "tool",
                        "content": "PASS",
                        "extra": {"returncode": 0, "raw_output": "PASS"},
                    },
                ],
            }
        ]
    }
    traj2 = {
        "segments": [
            {
                "kind": "solver",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "task"},
                    {
                        "role": "assistant",
                        "content": "edit file",
                        "extra": {
                            "actions": [{"command": "cat <<'EOF' > outlines.py\nx = 1\nEOF"}],
                            "response": {"id": "a2_1", "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
                            "timestamp": 95.0,
                            "cost": 0.1,
                        },
                    },
                    {
                        "role": "tool",
                        "content": "",
                        "extra": {"returncode": 0, "raw_output": ""},
                    },
                    {
                        "role": "assistant",
                        "content": "verify and reply",
                        "extra": {
                            "actions": [{"command": "pytest && send_message agent1 'looks good'"}],
                            "response": {"id": "a2_2", "usage": {"prompt_tokens": 150, "completion_tokens": 15}},
                            "timestamp": 110.0,
                            "cost": 0.11,
                        },
                    },
                    {
                        "role": "tool",
                        "content": "PASS\nMessage sent to agent1 (id: m2, intent: ACK, reply_to: m1, resolved)",
                        "extra": {
                            "returncode": 0,
                            "raw_output": "PASS\nMessage sent to agent1 (id: m2, intent: ACK, reply_to: m1, resolved)",
                        },
                    },
                ],
            }
        ]
    }
    (pair_dir / "agent1_full_traj.json").write_text(json.dumps(traj1), encoding="utf-8")
    (pair_dir / "agent2_full_traj.json").write_text(json.dumps(traj2), encoding="utf-8")
    (pair_dir / "agent1.patch").write_text("diff --git a/a.py b/a.py\n+a\n", encoding="utf-8")
    (pair_dir / "agent2.patch").write_text("diff --git a/b.py b/b.py\n+b\n", encoding="utf-8")
    return root


def test_compile_real_pair(synthetic_repo_root: Path) -> None:
    """Tests compilation against a structured run directory on disk."""
    logs_dir = synthetic_repo_root / "logs"
    results_dir = synthetic_repo_root / "results"
    dataset_dir = synthetic_repo_root / "dataset"

    runs = list_runs(logs_dir=logs_dir, results_dir=results_dir)
    assert len(runs) == 1
    for r in runs:
        assert "run_name" in r
        assert "config_flags" in r
        assert r["config_flags"]["delivery_timing"] is True

    pairs = list_pairs_index(logs_dir=logs_dir, results_dir=results_dir)
    assert len(pairs) == 1

    replay = compile_pair_replay(
        run_name="coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing",
        repo="dottxt_ai_outlines_task",
        task_id=1655,
        features=(7, 10),
        logs_dir=logs_dir,
        results_dir=results_dir,
        dataset_dir=dataset_dir,
    )

    assert replay["run_name"] == "coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"
    assert replay["repo"] == "dottxt_ai_outlines_task"
    assert replay["task_id"] == 1655
    assert replay["features"] == [7, 10]
    assert len(replay["messages"]) == 2
    assert len(replay["steps"]["agent1"]) == 2
    assert len(replay["steps"]["agent2"]) == 2
    assert len(replay["timeline"]) > 0
    assert "agent1" in replay["timeline"][0]
    assert "agent2" in replay["timeline"][0]
    assert "center" in replay["timeline"][0]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def test_http_api_endpoints(synthetic_repo_root: Path) -> None:
    """Verifies that the server handles /, /api/runs, /api/index, and /api/replay correctly."""
    port = _find_free_port()
    ReplayRequestHandler.repo_root = synthetic_repo_root
    server = ThreadingHTTPServer(("127.0.0.1", port), ReplayRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Test /
        with urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "CooperBench" in content
            assert "Replay Studio" in content

        # 2. Test /api/runs
        with urlopen(f"{base_url}/api/runs") as resp:
            assert resp.status == 200
            runs = json.loads(resp.read().decode("utf-8"))
            assert isinstance(runs, list)
            assert len(runs) == 1

        # 3. Test /api/index
        with urlopen(f"{base_url}/api/index") as resp:
            assert resp.status == 200
            pairs = json.loads(resp.read().decode("utf-8"))
            assert isinstance(pairs, list)
            assert len(pairs) == 1

        # 4. Test /api/replay
        replay_url = (
            f"{base_url}/api/replay?run=coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"
            "&repo=dottxt_ai_outlines_task&task=1655&f1=7&f2=10"
        )
        with urlopen(replay_url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["task_id"] == 1655
            assert len(data["timeline"]) > 0

        # 5. Test 400 Bad Request on missing parameters
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base_url}/api/replay?run=invalid")
        assert exc_info.value.code == 400

        # 6. Test 404 on missing pair
        with pytest.raises(HTTPError) as exc_info_404:
            urlopen(f"{base_url}/api/replay?run=invalid&repo=none&task=0&f1=1&f2=2")
        assert exc_info_404.value.code == 404

    finally:
        server.shutdown()
        server.server_close()


def test_export_static_html(tmp_path: Path, synthetic_repo_root: Path) -> None:
    """Verifies that export_static_html creates a standalone HTML bundle."""
    from tools.replay_viewer.server import export_static_html

    out_file = tmp_path / "standalone_replay.html"
    res = export_static_html(
        output_path=out_file,
        repo_root=synthetic_repo_root,
        run_filter=["delivery-timing"],
        pair_filter=["1655"],
    )

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "window.__PRELOADED_REPLAY_BUNDLE__" in content
    assert "dottxt_ai_outlines_task" in content
    assert "CooperBench" in content


def test_regime_metadata_and_local_logs_filtering(synthetic_repo_root: Path) -> None:
    """Verifies regime metadata extraction across regimes and exclusion of unlogged results."""
    logs_dir = synthetic_repo_root / "logs"
    results_dir = synthetic_repo_root / "results"
    dataset_dir = synthetic_repo_root / "dataset"

    # Add a second 128K / 500-step reference run with local logs on the same pair.
    ref_run = "coop-msa_v2-git-gemini-3-8-flash-flash-ref-intents"
    ref_pair_dir = logs_dir / ref_run / "coop" / "dottxt_ai_outlines_task" / "1655" / "f7_f10"
    ref_pair_dir.mkdir(parents=True, exist_ok=True)
    orig_pair_dir = (
        logs_dir
        / "coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"
        / "coop"
        / "dottxt_ai_outlines_task"
        / "1655"
        / "f7_f10"
    )
    for fname in ("result.json", "eval.json", "agent1_full_traj.json", "agent2_full_traj.json"):
        (ref_pair_dir / fname).write_text((orig_pair_dir / fname).read_text(encoding="utf-8"), encoding="utf-8")

    ref_res_dir = results_dir / ref_run
    ref_res_dir.mkdir(parents=True, exist_ok=True)
    (ref_res_dir / "run.json").write_text(
        json.dumps(
            {
                "run_name": ref_run,
                "setting": "coop",
                "git_enabled": True,
                "model": "vertex_ai/gemini-3.8-flash",
                "subset": "flash",
                "budgets": {
                    "step_limit": 500,
                    "compaction_token_trigger": 128000,
                    "thinking_level": "medium",
                },
            }
        ),
        encoding="utf-8",
    )
    (ref_res_dir / "pairs.csv").write_text(
        "repo,task_id,feature_a,feature_b,both_passed,merge_status,messages_sent,steps_total,cost_usd\n"
        "dottxt_ai_outlines_task,1655,7,10,true,clean,2,4,0.42\n",
        encoding="utf-8",
    )

    # Add a results-only run without local logs/; it should not appear as a replayable pair run.
    unlogged_run = "coop-msa_v2-git-gemini-3-8-flash-lite-ref"
    unlogged_res_dir = results_dir / unlogged_run
    unlogged_res_dir.mkdir(parents=True, exist_ok=True)
    (unlogged_res_dir / "run.json").write_text(
        json.dumps(
            {
                "run_name": unlogged_run,
                "setting": "coop",
                "git_enabled": True,
                "model": "vertex_ai/gemini-3.8-flash",
                "subset": "lite",
                "budgets": {
                    "step_limit": 500,
                    "compaction_token_trigger": 128000,
                    "thinking_level": "medium",
                },
            }
        ),
        encoding="utf-8",
    )
    (unlogged_res_dir / "pairs.csv").write_text(
        "repo,task_id,feature_a,feature_b,both_passed,merge_status,messages_sent,steps_total,cost_usd\n"
        "dottxt_ai_outlines_task,1655,7,10,true,clean,5,20,1.10\n",
        encoding="utf-8",
    )

    pairs = list_pairs_index(logs_dir=logs_dir, results_dir=results_dir)
    assert len(pairs) == 1
    pair_runs = pairs[0]["runs"]
    assert set(pair_runs.keys()) == {
        "coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing",
        ref_run,
    }
    assert unlogged_run not in pair_runs

    low_entry = pair_runs["coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"]
    assert low_entry["model"] == "gemini-3-flash-preview"
    assert low_entry["budgets"]["step_limit"] == 100
    assert low_entry["budgets"]["compaction_token_trigger"] == 28000

    ref_entry = pair_runs[ref_run]
    assert ref_entry["model"] == "vertex_ai/gemini-3.8-flash"
    assert ref_entry["budgets"] == {
        "step_limit": 500,
        "compaction_token_trigger": 128000,
        "thinking_level": "medium",
    }

    replay = compile_pair_replay(
        run_name=ref_run,
        repo="dottxt_ai_outlines_task",
        task_id=1655,
        features=(7, 10),
        logs_dir=logs_dir,
        results_dir=results_dir,
        dataset_dir=dataset_dir,
    )
    assert replay["model"] == "vertex_ai/gemini-3.8-flash"
    assert replay["git_enabled"] is True
    assert replay["budgets"]["compaction_token_trigger"] == 128000
    assert replay["budgets"]["step_limit"] == 500
    assert replay["budgets"]["thinking_level"] == "medium"
