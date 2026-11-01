"""The opt-in step counter: what the agent sees at the end of each turn.

Without it the agent knows neither how many steps it has used nor how many remain, because
compaction drops the history it could count from.
"""

from __future__ import annotations

from cooperbench.agents.mini_swe_agent_v2.agents.default import DefaultAgent
from cooperbench.agents.mini_swe_agent_v2.exceptions import FormatError


class _StubModel:
    def format_message(self, role, content, extra=None):
        return {"role": role, "content": content, "extra": extra or {}}

    def format_observation_messages(self, message, outputs, template_vars):
        return [{"role": "tool", "content": o["output"], "extra": {}} for o in outputs]

    def get_template_vars(self):
        return {}

    def serialize(self):
        return {}


class _StubEnv:
    def execute(self, action):
        return {"output": f"ran {action['command']}", "returncode": 0}

    def get_template_vars(self):
        return {}

    def serialize(self):
        return {}


def _agent(**config):
    agent = DefaultAgent(_StubModel(), _StubEnv(), system_template="s", instance_template="i", **config)
    agent.messages = []
    return agent


def _turn(*commands):
    return {"role": "assistant", "extra": {"actions": [{"command": c} for c in commands]}}


def test_off_by_default_leaves_observations_unchanged():
    agent = _agent(step_limit=100)
    agent.n_calls = 3
    out = agent.execute_actions(_turn("ls"))
    assert out[-1]["content"] == "ran ls"


def test_counter_appended_to_last_observation_of_the_turn():
    agent = _agent(step_limit=100, step_counter=True)
    agent.n_calls = 3
    out = agent.execute_actions(_turn("ls", "pwd"))
    assert out[0]["content"] == "ran ls"
    assert out[1]["content"].startswith("ran pwd\n\n[Step 3 of 100: 97 left.")
    assert "only work you have pushed and submitted is graded" in out[1]["content"]
    assert agent.messages[-1] is out[1]


def test_counter_never_goes_negative():
    agent = _agent(step_limit=5, step_counter=True)
    agent.n_calls = 5
    assert "[Step 5 of 5: 0 left." in agent.execute_actions(_turn("ls"))[-1]["content"]


def test_no_counter_without_a_step_limit():
    agent = _agent(step_limit=0, step_counter=True)
    agent.n_calls = 3
    assert agent.execute_actions(_turn("ls"))[-1]["content"] == "ran ls"


def test_format_error_turns_also_show_the_counter():
    agent = _agent(step_limit=100, step_counter=True)
    agent.n_calls = 7
    err = FormatError({"role": "user", "content": "Please call the bash tool.", "extra": {}})
    out = agent._with_step_counter(list(err.messages))
    assert out[-1]["content"].endswith(
        "[Step 7 of 100: 93 left. When no steps are left you are stopped, "
        "and only work you have pushed and submitted is graded.]"
    )


def test_exit_messages_are_left_alone():
    agent = _agent(step_limit=100, step_counter=True)
    agent.n_calls = 100
    exit_msg = {"role": "exit", "content": "LimitsExceeded", "extra": {}}
    assert agent._with_step_counter([exit_msg]) == [exit_msg]
