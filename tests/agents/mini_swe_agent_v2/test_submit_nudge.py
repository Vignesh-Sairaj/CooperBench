"""An agent that tries to end with unpublished work gets a reminder, and must not crash.

The reminder used to be appended after the agent's exit message, so the next model call
sent a ``role: exit`` message and LiteLLM rejected it.
"""

from __future__ import annotations

from cooperbench.agents.mini_swe_agent_v2.agents.default import DefaultAgent


class _StubModel:
    def format_message(self, role, content, extra=None):
        return {"role": role, "content": content, "extra": extra or {}}

    def get_template_vars(self):
        return {}

    def serialize(self):
        return {}


class _StubEnv:
    def __init__(self, dirty: bool):
        self.dirty = dirty

    def execute(self, action):
        cmd = action["command"]
        if cmd.startswith("git status"):
            return {"output": " M src/app.py\n" if self.dirty else "", "returncode": 0}
        return {"output": "", "returncode": 0}  # no PR tag, nothing ahead of the remote

    def get_template_vars(self):
        return {}

    def serialize(self):
        return {}


class _StubComm:
    agent_id = "agent1"


def _exiting_agent(dirty: bool) -> DefaultAgent:
    agent = DefaultAgent(_StubModel(), _StubEnv(dirty), comm=_StubComm(), system_template="s", instance_template="i")
    exit_msg = {"role": "exit", "content": "", "extra": {"exit_status": "Submitted", "submission": ""}}
    agent.messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "i"}, exit_msg]
    return agent


def test_reminder_replaces_the_exit_message():
    agent = _exiting_agent(dirty=True)
    assert agent._continue_after_exit() is True
    assert all(m["role"] != "exit" for m in agent.messages)
    assert agent.messages[-1]["role"] == "user"
    assert "You have not submitted anything" in agent.messages[-1]["content"]


def test_nothing_to_submit_keeps_the_exit_message():
    agent = _exiting_agent(dirty=False)
    assert agent._continue_after_exit() is False
    assert agent.messages[-1]["role"] == "exit"
    assert agent.messages[-1]["extra"]["exit_status"] == "Submitted"


def test_reminders_stop_after_the_limit():
    agent = _exiting_agent(dirty=True)
    agent._submit_nudges = DefaultAgent.MAX_SUBMIT_NUDGES
    assert agent._continue_after_exit() is False
    assert agent.messages[-1]["role"] == "exit"
