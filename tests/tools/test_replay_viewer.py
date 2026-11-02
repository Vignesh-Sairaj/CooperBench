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
    MAIN_REPO_ROOT,
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
            output='Message sent to agent2 (id: m1, intent: FYI)',
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


def test_compile_real_pair() -> None:
    """Tests compilation against real log data on disk."""
    if not (MAIN_REPO_ROOT / "logs").exists():
        pytest.skip("CooperBench logs directory not available.")

    runs = list_runs()
    assert len(runs) > 0
    # Ensure all runs have expected keys and config badges
    for r in runs[:5]:
        assert "run_name" in r
        assert "config_flags" in r
        assert "delivery_timing" in r["config_flags"]

    pairs = list_pairs_index()
    assert len(pairs) > 0

    # Compile the delivery-timing run on outlines 1655 f7_f10
    replay = compile_pair_replay(
        run_name="coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing",
        repo="dottxt_ai_outlines_task",
        task_id=1655,
        features=(7, 10),
    )

    assert replay["run_name"] == "coop-msa_v2-git-gemini-3-flash-flash_10-low-delivery-timing"
    assert replay["repo"] == "dottxt_ai_outlines_task"
    assert replay["task_id"] == 1655
    assert replay["features"] == [7, 10]
    assert len(replay["messages"]) == 9
    assert len(replay["steps"]["agent1"]) > 0
    assert len(replay["steps"]["agent2"]) > 0
    assert len(replay["timeline"]) > 0
    assert "agent1" in replay["timeline"][0]
    assert "agent2" in replay["timeline"][0]
    assert "center" in replay["timeline"][0]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def test_http_api_endpoints() -> None:
    """Verifies that the server handles /, /api/runs, /api/index, and /api/replay correctly."""
    port = _find_free_port()
    ReplayRequestHandler.repo_root = MAIN_REPO_ROOT
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
            assert len(runs) > 0

        # 3. Test /api/index
        with urlopen(f"{base_url}/api/index") as resp:
            assert resp.status == 200
            pairs = json.loads(resp.read().decode("utf-8"))
            assert isinstance(pairs, list)
            assert len(pairs) > 0

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


def test_export_static_html(tmp_path: Path) -> None:
    """Verifies that export_static_html creates a standalone HTML bundle."""
    from tools.replay_viewer.server import export_static_html

    out_file = tmp_path / "standalone_replay.html"
    res = export_static_html(
        output_path=out_file,
        repo_root=MAIN_REPO_ROOT,
        run_filter=["delivery-timing"],
        pair_filter=["1655"],
    )

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "window.__PRELOADED_REPLAY_BUNDLE__" in content
    assert "dottxt_ai_outlines_task" in content
    assert "CooperBench" in content
