"""Unit tests for opt-in communication interventions in Mini-SWE-Agent v2.

Covers:
1. Default-off upstream parity (zero behavior or payload drift when flags are False).
2. Message Delivery Timing (natural workflow boundaries, periodic counterfactual,
   step ceiling, urgent/blocking bypass, and pre-exit flush).
3. Message Board / Threading (monotonic Redis IDs, formal --reply-to / --resolve
   contract, wire validation, per-turn footers, and compaction board pinning).
4. Message Intent Tags & combined composition (--intent parsing, priority sorting,
   FYI filtering, ACK auto-resolution, and live-peer pre-submit obligation checks).
5. Variant config YAML schema and Jinja2 StrictUndefined template rendering.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from cooperbench.agents.mini_swe_agent_v2.agents.communication import COMPACTION_BOARD_HEADING
from cooperbench.agents.mini_swe_agent_v2.agents.default import DefaultAgent
from cooperbench.agents.mini_swe_agent_v2.config import get_config_path
from cooperbench.agents.mini_swe_agent_v2.connectors import MessagingConnector
from cooperbench.agents.mini_swe_agent_v2.utils.serialize import recursive_merge


class _StubModel:
    def __init__(self) -> None:
        self.queued_responses: list[dict[str, Any]] = []
        self.summarizer_inputs: list[list[dict[str, Any]]] = []

    def queue_turn(self, *commands: str, prompt_tokens: int = 100) -> None:
        self.queued_responses.append(
            {
                "role": "assistant",
                "content": "thinking",
                "extra": {
                    "actions": [{"command": cmd} for cmd in commands],
                    "cost": 0.01,
                    "response": {"usage": {"prompt_tokens": prompt_tokens}},
                },
            }
        )

    def query(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if self.queued_responses:
            return self.queued_responses.pop(0)
        return {
            "role": "assistant",
            "content": "noop",
            "extra": {"actions": [{"command": "true"}], "cost": 0.0},
        }

    def summarize_context(self, messages: list[dict[str, Any]], summary_prompt: str) -> dict[str, Any]:
        self.summarizer_inputs.append(list(messages))
        return {
            "role": "assistant",
            "content": "## FILE MAP\n(none)\n\n## CURRENT PLAN\nContinue.",
            "extra": {"summary": True},
        }

    def format_message(self, role: str, content: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"role": role, "content": content, "extra": extra or {}}

    def format_observation_messages(
        self,
        message: dict[str, Any],
        outputs: list[dict[str, Any]],
        template_vars: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [{"role": "tool", "content": out["output"], "extra": {}} for out in outputs]

    def get_template_vars(self) -> dict[str, Any]:
        return {}

    def serialize(self) -> dict[str, Any]:
        return {}


class _StubEnv:
    def __init__(self, *, pr_open: bool = False, dirty: bool = False) -> None:
        self.pr_open = pr_open
        self.dirty = dirty
        self.next_returncode = 0
        self.executed: list[str] = []

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        cmd = action["command"]
        self.executed.append(cmd)
        if cmd.startswith("git ls-remote --tags"):
            out = "abc123\trefs/tags/pr/agent1\n" if self.pr_open else ""
            return {"output": out, "returncode": 0}
        if cmd.startswith("git status --porcelain"):
            return {"output": " M app.py\n" if self.dirty else "", "returncode": 0}
        if cmd.startswith("git rev-list --count"):
            return {"output": "0\n", "returncode": 0}
        rc = self.next_returncode
        self.next_returncode = 0
        return {"output": f"ran: {cmd}", "returncode": rc}

    def get_template_vars(self) -> dict[str, Any]:
        return {
            "system": "Linux",
            "release": "6.6",
            "version": "#1",
            "machine": "x86_64",
        }

    def serialize(self) -> dict[str, Any]:
        return {}


def _make_agent(
    agent_id: str,
    comm: MessagingConnector | None,
    *,
    env: _StubEnv | None = None,
    model: _StubModel | None = None,
    **config: Any,
) -> DefaultAgent:
    stub_model = model or _StubModel()
    stub_env = env or _StubEnv()
    agent = DefaultAgent(
        stub_model,
        stub_env,
        comm=comm,
        agent_id=agent_id,
        system_template="sys",
        instance_template="inst",
        **config,
    )
    agent.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "inst"},
    ]
    return agent


def _turn(*commands: str) -> dict[str, Any]:
    return {"role": "assistant", "extra": {"actions": [{"command": c} for c in commands]}}


@pytest.fixture
def comm_pair(redis_url: str, request: pytest.FixtureRequest) -> tuple[MessagingConnector, MessagingConnector]:
    ns = f"{redis_url}#test:comm:{request.node.name}:{uuid.uuid4().hex[:8]}"
    alice = MessagingConnector(agent_id="agent1", agents=["agent1", "agent2"], url=ns)
    bob = MessagingConnector(agent_id="agent2", agents=["agent1", "agent2"], url=ns)
    return alice, bob


class TestUpstreamParity:
    def test_all_flags_off_by_default_preserves_exact_wire_and_output(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent("agent1", alice_comm, step_limit=100)
        bob = _make_agent("agent2", bob_comm, step_limit=100)

        assert alice._comm_coord.enabled is False
        obs = alice.execute_actions(_turn('send_message agent2 "hello there"'))
        assert obs[-1]["content"] == "Message sent to agent2"

        raw_inbox = bob_comm.receive()
        assert len(raw_inbox) == 1
        assert set(raw_inbox[0].keys()) == {"from", "to", "content", "timestamp"}

        alice_comm.send("agent2", "second message")
        bob.env.next_returncode = 1
        bob.execute_actions(_turn("sed -i 's/a/b/' broken.py"))
        bob.model.queue_turn("ls")
        bob.step()
        injected = [m["content"] for m in bob.messages if m["role"] == "user" and "[Message from" in m["content"]]
        assert injected == ["[Message from agent1]: second message"]


class TestDeliveryTiming:
    def test_holds_mid_edit_and_failed_test_then_flushes_on_clean_verify(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent("agent1", alice_comm, delivery_timing=True, delivery_max_hold_steps=4)

        # Step 1: Alice performs a file edit (no prior read_explore -> not a boundary).
        alice.model.queue_turn("sed -i 's/foo/bar/' src/app.py")
        alice.step()

        # Bob sends a non-blocking message while Alice is mid-implementation.
        bob_comm.send("agent1", "FYI: I am editing src/other.py")

        # Step 2: Alice runs failing pytest (returncode=1) -> message held at start of step 2,
        # and still held at start of step 3 because pytest failed.
        alice.env.next_returncode = 1
        alice.model.queue_turn("pytest -q")
        alice.step()
        assert not any("src/other.py" in m.get("content", "") for m in alice.messages)
        assert alice._comm_coord.has_held_messages is True

        # Step 3: Alice fixes code and runs passing pytest (returncode=0).
        alice.model.queue_turn("pytest -q")
        alice.step()
        assert not any("src/other.py" in m.get("content", "") for m in alice.messages)

        # Step 4: Start of turn after clean pytest -> buffered message is flushed!
        alice.model.queue_turn("git status")
        alice.step()
        delivered = [m["content"] for m in alice.messages if "src/other.py" in m.get("content", "")]
        assert delivered == ["[Message from agent2]: FYI: I am editing src/other.py"]
        assert alice._comm_coord.has_held_messages is False

    def test_flushes_on_read_to_edit_transition(self, comm_pair: tuple[MessagingConnector, MessagingConnector]) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent("agent1", alice_comm, delivery_timing=True, delivery_max_hold_steps=5)

        alice.model.queue_turn("nl -ba src/app.py | sed -n '1,30p'")
        alice.step()

        bob_comm.send("agent1", "Watch out for line 20 in src/app.py")
        alice.model.queue_turn("sed -i 's/old/new/' src/app.py")
        alice.step()
        # Held at start of step 2 (last action was READ_EXPLORE), then step 2 executes FILE_EDIT ->
        # prev=READ_EXPLORE, last=FILE_EDIT triggers flush at start of step 3!
        assert alice._comm_coord.has_held_messages is True

        alice.model.queue_turn("ls")
        alice.step()
        assert any("Watch out for line 20" in m.get("content", "") for m in alice.messages)

    def test_periodic_mode_ignores_natural_boundaries_until_ceiling(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent(
            "agent1",
            alice_comm,
            delivery_timing=True,
            delivery_max_hold_steps=3,
            delivery_boundary_mode="periodic",
        )

        alice.model.queue_turn("sed -i 's/a/b/' f.py")
        alice.step()  # n_calls = 1

        bob_comm.send("agent1", "periodic test message")
        alice.model.queue_turn("pytest -q")
        alice.step()  # arrived_step = 1, executes clean pytest, n_calls = 2

        # Even after clean pytest, periodic mode holds at step 2 (age = 2 - 1 = 1 < 3)
        alice.model.queue_turn("git status")
        alice.step()  # age = 1 < 3 -> still held, n_calls = 3
        assert alice._comm_coord.has_held_messages is True

        alice.model.queue_turn("ls")
        alice.step()  # age = 3 - 1 = 2 < 3 -> still held, n_calls = 4
        assert alice._comm_coord.has_held_messages is True

        alice.model.queue_turn("ls")
        alice.step()  # age = 4 - 1 = 3 >= 3 -> flushed!
        assert alice._comm_coord.has_held_messages is False
        assert any("periodic test message" in m.get("content", "") for m in alice.messages)

    def test_blocking_wait_bypasses_hold_immediately(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent("agent1", alice_comm, delivery_timing=True, delivery_max_hold_steps=5)

        alice.model.queue_turn("sed -i 's/a/b/' f.py")
        alice.step()

        # Simulate Bob blocked in send_and_wait on Alice
        bob_comm.send("agent1", "Need answer now!")
        bob_comm._client.setex(bob_comm._blocked_key("agent1"), 30, "agent2")
        try:
            alice.model.queue_turn("ls")
            alice.step()
        finally:
            bob_comm._client.delete(bob_comm._blocked_key("agent1"))

        assert alice._comm_coord.has_held_messages is False
        injected = [m["content"] for m in alice.messages if "Need answer now!" in m.get("content", "")]
        assert len(injected) == 1
        assert "BLOCKED waiting for your reply" in injected[0]

    def test_pre_exit_flushes_buffered_messages_even_when_pr_is_open(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        env = _StubEnv(pr_open=True, dirty=False)
        alice = _make_agent("agent1", alice_comm, env=env, delivery_timing=True, step_limit=100)

        alice.model.queue_turn("sed -i 's/a/b/' f.py")
        alice.step()
        bob_comm.send("agent1", "Wait — I changed signature of helper()!")
        alice.model.queue_turn("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT")
        alice.step()
        assert alice._comm_coord.has_held_messages is True

        # Simulate exit sentinel handling
        alice.messages.append({"role": "exit", "content": "", "extra": {"exit_status": "Submitted"}})
        assert alice._continue_after_exit() is True
        assert alice._comm_coord.has_held_messages is False
        assert any("changed signature of helper()" in m.get("content", "") for m in alice.messages)
        assert all(m["role"] != "exit" for m in alice.messages)


class TestMessageThreading:
    def test_monotonic_ids_open_vs_resolved_and_wire_validation(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        alice = _make_agent("agent1", alice_comm, message_threading=True, step_limit=100, step_counter=True)
        bob = _make_agent("agent2", bob_comm, message_threading=True, step_limit=100, step_counter=True)

        # 1. Validation failures: --resolve without --reply-to, and unknown --reply-to ID
        err1 = alice.execute_actions(_turn('send_message --resolve agent2 "settled"'))
        assert "--resolve requires --reply-to" in err1[-1]["content"]
        err2 = alice.execute_actions(_turn('send_message --reply-to m99 agent2 "unknown"'))
        assert "unknown --reply-to id 'm99'" in err2[-1]["content"]
        assert bob_comm.peek() == 0

        # 2. Alice opens thread m1 (with nested quotes inside single-quoted body)
        alice.n_calls = 1
        out1 = alice.execute_actions(_turn("""send_message agent2 'Taking "cli.py" — you take parser.py?'"""))
        assert "Message sent to agent2 (id: m1)" in out1[-1]["content"]
        assert "[Open threads (1):" in out1[-1]["content"]
        assert "[Step 1 of 100: 99 left." in out1[-1]["content"]

        # 3. Bob receives m1, replies with --reply-to m1 (NO --resolve) -> m2, thread m1 stays OPEN
        bob.model.queue_turn('send_message --reply-to m1 agent1 "What about shared types in models.py?"')
        bob.step()
        assert "Message sent to agent1 (id: m2, thread m1: open)" in bob.messages[-1]["content"]
        assert "[Open threads (1):" in bob.messages[-1]["content"]

        # 4. Alice receives m2 and replies with --reply-to m2 --resolve -> m3 resolves root thread m1!
        alice.model.queue_turn('send_message --reply-to m2 --resolve agent2 "Put shared types at bottom of models.py"')
        alice.step()
        assert "Message sent to agent2 (id: m3, thread m1: resolved)" in alice.messages[-1]["content"]
        assert "[Open threads" not in alice.messages[-1]["content"]

        # 5. Bob receives m3 -> Bob's thread m1 transitions to resolved and leaves the turn footer
        bob.model.queue_turn("ls")
        bob.step()
        assert "[Open threads" not in bob.messages[-1]["content"]
        assert bob._comm_coord._threads["m1"].status == "resolved"

        # 6. Undelivered send to exited peer does not advance msg_seq
        bob_comm.mark_exited(published=True)
        fail_send = alice.execute_actions(_turn('send_message agent2 "after exit"'))
        assert "completed their work and exited" in fail_send[-1]["content"]
        assert int(alice_comm._client.get(alice_comm._seq_key) or 0) == 3

    def test_compaction_pins_open_and_resolved_threads_and_strips_old_board(
        self, comm_pair: tuple[MessagingConnector, MessagingConnector]
    ) -> None:
        alice_comm, bob_comm = comm_pair
        model = _StubModel()
        alice = _make_agent(
            "agent1",
            alice_comm,
            model=model,
            message_threading=True,
            compaction_enabled=True,
            compaction_token_trigger=1000,
            compaction_keep_recent_turns=1,
        )

        # Open m1 and resolve it via m2; open m3 and leave it open
        alice.execute_actions(_turn('send_message agent2 "Split cli.py vs parser.py"'))
        bob_comm.send("agent1", "Agreed on split", assign_id=True, reply_to="m1", resolve=True)
        bob_comm.send("agent1", "Can you export parse_flag()?", assign_id=True)
        alice.model.queue_turn("ls", prompt_tokens=1500)
        alice.step()
        alice.model.queue_turn("pwd", prompt_tokens=500)
        alice.step()  # triggers compaction #1 before query!

        assert alice._compaction_count == 1
        summary_msg = alice.messages[2]
        assert COMPACTION_BOARD_HEADING in summary_msg["content"]
        assert "Open threads (require follow-up or --resolve):" in summary_msg["content"]
        assert "m3" in summary_msg["content"]
        assert "Resolved agreements (keep honoring these boundaries):" in summary_msg["content"]
        assert "m1" in summary_msg["content"]

        # Trigger compaction #2 and verify summarizer_input had prior board stripped
        alice._last_prompt_tokens = 1500
        alice.model.queue_turn("ls", prompt_tokens=500)
        alice.step()
        assert alice._compaction_count == 2
        second_summarizer_input = model.summarizer_inputs[-1]
        assert all(COMPACTION_BOARD_HEADING not in (m.get("content") or "") for m in second_summarizer_input)


