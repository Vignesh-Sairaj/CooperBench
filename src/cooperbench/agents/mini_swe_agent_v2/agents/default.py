"""Basic agent class. See https://mini-swe-agent.com/latest/advanced/control_flow/ for visual explanation
or https://minimal-agent.com for a tutorial on the basic building principles.
"""

import json
import logging
import re
import time
import traceback
from pathlib import Path
from typing import Any, Literal

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel

from cooperbench.agents.mini_swe_agent_v2 import Environment, Model, __version__
from cooperbench.agents.mini_swe_agent_v2.agents.communication import (
    CommunicationCoordinator,
    CommunicationSettings,
    NoSendCommand,
    ParsedSendBatch,
    SendCall,
    SendParseError,
    strip_compaction_board,
)
from cooperbench.agents.mini_swe_agent_v2.connectors.messaging import MessagingConnector
from cooperbench.agents.mini_swe_agent_v2.exceptions import InterruptAgentFlow, LimitsExceeded
from cooperbench.agents.mini_swe_agent_v2.utils.serialize import recursive_merge

# Name of the shared git remote created by GitConnector.  Referenced in the messages the
# agent sees, so it must match GitConnector.REMOTE_NAME.
GIT_REMOTE = "origin"


class AgentConfig(BaseModel):
    """Check the config files in config/ for example settings."""

    system_template: str
    """Template for the system message (the first message)."""
    instance_template: str
    """Template for the first user message specifying the task (the second message overall)."""
    step_limit: int = 0
    """Maximum number of steps the agent can take."""
    step_counter: bool = False
    """Append the current step number and the step limit to every observation, so the agent
    can see how many steps it has left. Off by default (upstream behavior)."""
    cost_limit: float = 3.0
    """Stop agent after exceeding (!) this cost."""
    output_path: Path | None = None
    """Save the trajectory to this path."""
    compaction_enabled: bool = True
    """Enable context compaction (summarization of old messages)."""
    compaction_token_trigger: int = 28000
    """Compact when prompt token count exceeds this threshold."""
    compaction_keep_recent_turns: int = 2
    """Number of recent assistant turns to keep verbatim after compaction."""
    compaction_summary_prompt: str = (
        "You are summarizing the transcript below so the agent can continue in a "
        "fresh context without re-running commands. You are an outside observer "
        "of the conversation, not its next participant — output the summary as a "
        "single text response.\n"
        "\n"
        "The system prompt and the original task are preserved separately — DO NOT "
        "restate them. Focus on what would otherwise be LOST when the prior turns "
        "are discarded.\n"
        "\n"
        "Cite only what actually appears in the transcript. Do NOT invent line "
        "counts, file sizes, line numbers, or file contents you did not see. "
        "If you don't know a value, omit the field rather than guessing.\n"
        "\n"
        "Output ONLY the summary, using these exact section headings. Quote "
        "verbatim where stated; paraphrasing forces the agent to re-run commands.\n"
        "\n"
        "## FILE MAP\n"
        "One line per file the agent has touched (read, edited, or referenced):\n"
        "    `<path>`: <one-phrase description of what it contains>. Read so far: "
        '<line ranges or "all" or "first N lines" — only if known from `wc`, '
        "`head`, `tail`, or `sed -n` output above>. Modified: <yes/no>.\n"
        "Include `<line_count> lines` ONLY if a `wc -l` was actually run on it.\n"
        "\n"
        "## RELEVANT CODE READ\n"
        "For each file the agent read, quote the lines that matter for the task, "
        "verbatim, with citations:\n"
        "\n"
        "    `<path>` lines `<a>-<b>`: <one-line note on why this region matters>\n"
        "    ```\n"
        "    <verbatim snippet — exact indentation>\n"
        "    ```\n"
        "\n"
        "Include the parts likely needed again (definitions, key call sites, "
        "similar patterns nearby, struct shapes). Skip true boilerplate (license "
        "headers, unused imports). If a file was read and nothing in it matters, "
        "write one line: `<path>: read, nothing relevant`.\n"
        "\n"
        "## KEY SYMBOLS / IDENTIFIERS\n"
        "Flat list of important names the agent has discovered, with locations:\n"
        "`<name>` -> `<path>:<line>` — <one-phrase role>.\n"
        "Only include locations actually seen in the transcript.\n"
        "\n"
        "## SEARCH RESULTS WORTH KEEPING\n"
        "For each grep/find/ls/git-log: command + only the matches that matter:\n"
        "    `<cmd>` -> `<file>:<line>: <verbatim match>`.\n"
        "Also note negative results: `<cmd>` -> no matches.\n"
        "\n"
        "## EDITS ALREADY APPLIED\n"
        "For each edit (sed/echo>/cat-heredoc/python-write):\n"
        "    `<path>` <one-line description>:\n"
        "    ```diff\n"
        "    - <before>\n"
        "    + <after>\n"
        "    ```\n"
        "\n"
        "## BUILD / TEST OUTPUT\n"
        "For each test/build run: command, exit code, verbatim error lines "
        "(with `<file>:<line>:` refs). Skip pass noise.\n"
        "\n"
        "## COLLEAGUE MESSAGES\n"
        "Every send_message sent and `[Message from …]` received, verbatim, "
        "chronological.\n"
        "\n"
        "## OPEN QUESTIONS / UNREAD REGIONS\n"
        "What still needs investigation. Be specific — list file paths + line "
        "ranges + what to look for, so the next read is targeted not exploratory.\n"
        "\n"
        "## CURRENT PLAN\n"
        "The most recent stated plan and the immediate next intended step.\n"
        "\n"
        "Sections with no content: write `(none)`. Begin with `## FILE MAP` — "
        "no preamble."
    )
    """Prompt appended to conversation history when requesting a summary."""
    delivery_timing: bool = False
    """Hold non-blocking incoming messages until natural turn boundaries or step ceiling."""
    delivery_max_hold_steps: int = 4
    """Maximum steps a buffered message may be held before forced delivery."""
    delivery_boundary_mode: Literal["natural", "periodic"] = "natural"
    """Flush buffered messages at natural workflow boundaries or every N steps."""
    message_threading: bool = False
    """Assign monotonic message IDs (m1, m2, ...) and track open/resolved threads."""
    thread_pin_mode: Literal["every_turn", "compaction_only"] = "every_turn"
    """Render active threads in every turn's observation footer or only on compaction."""
    thread_max_pinned: int = 3
    """Maximum open threads shown in the per-turn observation footer."""
    thread_require_resolved_on_submit: bool = False
    """Remind an exiting agent once if incoming threads from a live peer remain open."""
    message_intents: bool = False
    """Require explicit speech-act intents (Proposal, Request, Response, ACK, FYI)."""
    intent_filter_fyi: bool = False
    """Suppress non-blocking incoming FYI updates on the receiver side."""
    intent_presubmit_check: bool = False
    """Remind an exiting agent once if incoming Request/Proposal items remain unanswered."""


class DefaultAgent:
    def __init__(
        self,
        model: Model,
        env: Environment,
        *,
        comm: MessagingConnector | None = None,
        agent_id: str = "agent",
        config_class: type = AgentConfig,
        **kwargs,
    ):
        """See the `AgentConfig` class for permitted keyword arguments."""
        self.config = config_class(**kwargs)
        self.messages: list[dict] = []
        self.model = model
        self.env = env
        self.comm = comm
        self.agent_id = agent_id
        self.extra_template_vars = {}
        self.logger = logging.getLogger("agent")
        self.cost = 0.0
        self.n_calls = 0
        self.sent_messages: list[dict] = []
        # Compaction state
        self._last_prompt_tokens: int = 0
        self._compaction_count: int = 0
        self._segments: list[dict] = []
        self._current_segment_messages: list[dict] = []
        self._comm_coord = CommunicationCoordinator(
            agent_id=agent_id,
            settings=CommunicationSettings(
                delivery_timing=self.config.delivery_timing,
                delivery_max_hold_steps=self.config.delivery_max_hold_steps,
                delivery_boundary_mode=self.config.delivery_boundary_mode,
                message_threading=self.config.message_threading,
                thread_pin_mode=self.config.thread_pin_mode,
                thread_max_pinned=self.config.thread_max_pinned,
                thread_require_resolved_on_submit=self.config.thread_require_resolved_on_submit,
                message_intents=self.config.message_intents,
                intent_filter_fyi=self.config.intent_filter_fyi,
                intent_presubmit_check=self.config.intent_presubmit_check,
            ),
        )

    def log(self, msg: str):
        """Log message with agent prefix."""
        self.logger.debug(f"[{self.agent_id}] {msg}")

    def get_template_vars(self, **kwargs) -> dict:
        return recursive_merge(
            self.config.model_dump(),
            self.env.get_template_vars(),
            self.model.get_template_vars(),
            {"n_model_calls": self.n_calls, "model_cost": self.cost},
            self.extra_template_vars,
            kwargs,
        )

    def _render_template(self, template: str) -> str:
        return Template(template, undefined=StrictUndefined).render(**self.get_template_vars())

    def add_messages(self, *messages: dict) -> list[dict]:
        self.logger.debug(messages)  # set log level to debug to see
        self.messages.extend(messages)
        return list(messages)

    def handle_uncaught_exception(self, e: Exception) -> list[dict]:
        return self.add_messages(
            self.model.format_message(
                role="exit",
                content=str(e),
                extra={
                    "exit_status": type(e).__name__,
                    "submission": "",
                    "exception_str": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        )

    def run(self, task: str = "", **kwargs) -> dict:
        """Run step() until agent is finished. Returns dictionary with exit_status, submission keys."""
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template)),
            self.model.format_message(role="user", content=self._render_template(self.config.instance_template)),
        )
        try:
            while True:
                try:
                    self.step()
                except InterruptAgentFlow as e:
                    self.add_messages(*self._with_step_counter(list(e.messages)))
                except Exception as e:
                    self.handle_uncaught_exception(e)
                    raise
                finally:
                    self.save(self.config.output_path)
                if self.messages[-1].get("role") == "exit":
                    if self._continue_after_exit():
                        continue
                    break
        finally:
            # Announce departure on EVERY exit path, not just a clean submit. A crash or a
            # step-limit exit used to leave this unset, so the peer's has_exited() stayed False
            # and it waited on someone who was never coming back -- one agent burned 91 minutes
            # of sleep that way and outlived its own sandbox.
            if self.comm:
                # `published` means "the peer can see my work on the remote", i.e. a PR is open.
                try:
                    published = self._opened_pr()
                except Exception:
                    published = False
                self.comm.mark_exited(published=published)
        return self.messages[-1].get("extra", {})

    MAX_SUBMIT_NUDGES = 2

    def _continue_after_exit(self) -> bool:
        """Decide whether an exiting agent gets a submit reminder instead of ending.

        The exit message is taken off the history before the reminder is added. Left in
        place, the next model call sends a ``role: exit`` message, which LiteLLM rejects
        (``Invalid Message passed in``), so the reminded agent crashed instead of submitting.
        It is put back when the agent really ends, because ``run()`` returns its ``extra``.
        """
        exit_message = self.messages.pop()
        if self._nudge_unsubmitted():
            return True
        self.messages.append(exit_message)
        return False

    def _nudge_unsubmitted(self) -> bool:
        """Tell an agent that is ending with unshared work, instead of letting it end.

        `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` and actually submitting are separate
        acts, so an agent can finish the task, verify its tests, announce "all changes are
        complete", fire the sentinel -- and have published nothing. Grading sees an empty
        patch, indistinguishable from an agent that never wrote any code. Measured: one agent
        did this after 943 steps of real work.

        Returns True if the episode should continue rather than exit.
        """
        if not self.comm:  # solo has no peer branch to compare against; left as-is
            return False

        limits_exhausted = 0 < self.config.step_limit <= self.n_calls or 0 < self.config.cost_limit <= self.cost
        if self._comm_coord.enabled and not limits_exhausted and self._comm_coord.has_held_messages:
            if getattr(self, "_held_flush_nudges", 0) < 2:
                self._held_flush_nudges = getattr(self, "_held_flush_nudges", 0) + 1
                flushed = self._comm_coord.flush_all_held(
                    current_step=self.n_calls,
                    is_awaited_fn=getattr(self.comm, "is_awaited_by", None),
                )
                for line in flushed:
                    self.add_messages(self.model.format_message(role="user", content=line))
                self.add_messages(
                    self.model.format_message(
                        role="user",
                        content=(
                            "Buffered message(s) from your colleague arrived while you were working and "
                            "have been delivered above. Review them and reconcile if needed, then run "
                            "`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` again."
                        ),
                    )
                )
                return True

        if getattr(self, "_submit_nudges", 0) < self.MAX_SUBMIT_NUDGES and not self._opened_pr():
            agent = self.comm.agent_id
            dirty = (self.env.execute({"command": "git status --porcelain"}).get("output") or "").strip()
            ahead = (
                self.env.execute({"command": f"git rev-list --count {GIT_REMOTE}/{agent}..HEAD 2>/dev/null"})
                .get("output", "")
                .strip()
            )
            unpushed = ahead not in ("", "0")
            if dirty or unpushed:
                self._submit_nudges = getattr(self, "_submit_nudges", 0) + 1
                held = "uncommitted changes" if dirty else "commits that are not pushed"
                self.log(f"SUBMIT NUDGE {self._submit_nudges} for {agent}: {held}, no PR")
                self.add_messages(
                    self.model.format_message(
                        role="user",
                        content=(
                            f"You have not submitted anything. Your work is still local ({held}) and "
                            f"no pull request exists, so it would be graded as an empty submission.\n\n"
                            f"    git add <the files you want to submit>\n"
                            f'    git commit -m "..."\n'
                            f"    git push {GIT_REMOTE} HEAD:{agent}\n"
                            f'    gh pr create --title "..." --body "..."\n\n'
                            f"Then echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT again."
                        ),
                    )
                )
                return True

        if self._comm_coord.enabled and not limits_exhausted and getattr(self, "_obligation_nudges", 0) < 1:
            pending = self._comm_coord.pending_presubmit_obligations(
                is_peer_exited_fn=getattr(self.comm, "has_exited", None)
            )
            if pending:
                self._obligation_nudges = getattr(self, "_obligation_nudges", 0) + 1
                bullet_list = "\n".join(pending)
                self.log(f"OBLIGATION NUDGE for {self.comm.agent_id}: {len(pending)} pending item(s)")
                self.add_messages(
                    self.model.format_message(
                        role="user",
                        content=(
                            "Before finishing, you have unanswered coordination items from a colleague "
                            "who is still working:\n"
                            f"{bullet_list}\n\n"
                            "Reply with `send_message` (and push any needed updates to your PR), then run "
                            "`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` again."
                        ),
                    )
                )
                return True

        return False

    def _opened_pr(self) -> bool:
        """Whether this agent's PR exists on the shared remote.

        Replaces `_publish_final_work`, which pushed `patch.txt` to the agent's branch at
        exit. Submission is now a PR the agent opens itself, so there is nothing left to
        publish -- that method only logged `no patch.txt to publish` on every run.
        """
        if not self.comm:
            return False
        r = self.env.execute({"command": f"git ls-remote --tags {GIT_REMOTE} refs/tags/pr/{self.comm.agent_id}"})
        return bool((r.get("output") or "").strip())

    def step(self) -> list[dict]:
        """Query the LM, execute actions. Polls for inter-agent messages
        and (in team mode) the shared task list before querying."""
        # Check for inter-agent messages before querying LLM
        if self.comm:
            if hasattr(self.comm, "heartbeat"):
                self.comm.heartbeat()
            messages = self.comm.receive()
            if self._comm_coord.enabled:
                for msg in messages:
                    ts = msg.get("timestamp", "")[:19].replace("T", " ")
                    self.log(f"INBOX: [{msg['from']} @ {ts}] {msg['content']}")
                rendered = self._comm_coord.receive_for_step(
                    messages,
                    current_step=self.n_calls,
                    is_awaited_fn=getattr(self.comm, "is_awaited_by", None),
                )
                for line in rendered:
                    self.add_messages(self.model.format_message(role="user", content=line))
            else:
                for msg in messages:
                    ts = msg.get("timestamp", "")[:19].replace("T", " ")
                    self.log(f"INBOX: [{msg['from']} @ {ts}] {msg['content']}")
                    # Say so when the sender is stalled on us. Without it the message reads as
                    # ordinary context and gets deprioritised behind the agent's own edit loop.
                    blocked = ""
                    if getattr(self.comm, "is_awaited_by", None) and self.comm.is_awaited_by(msg["from"]):
                        blocked = (
                            f" — {msg['from']} is BLOCKED waiting for your reply and cannot continue"
                            f" until you answer. Reply with send_message before your next command."
                        )
                    self.add_messages(
                        self.model.format_message(
                            role="user",
                            content=f"[Message from {msg['from']}{blocked}]: {msg['content']}",
                        )
                    )
            self._announce_departed_peers()
        # In team mode, also refresh the shared task list so the LLM
        # sees the live state of who's working on what before its next
        # response.  ``team_poller`` is set by the adapter when team
        # kwargs are present; absent for solo/coop.
        poller = getattr(self, "team_poller", None)
        if poller is not None:
            summary = poller.poll()
            if summary:
                self.add_messages(self.model.format_message(role="user", content=summary))
        return self.execute_actions(self.query())

    def _get_prompt_tokens(self, message: dict) -> int:
        return message.get("extra", {}).get("response", {}).get("usage", {}).get("prompt_tokens", 0)

    def _should_compact(self) -> bool:
        return self.config.compaction_enabled and self._last_prompt_tokens >= self.config.compaction_token_trigger

    @staticmethod
    def _find_turn_boundary(messages: list[dict], n_turns: int) -> int:
        """Return the index where the last n_turns complete assistant turns start."""
        assistant_indices = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
        if not assistant_indices or n_turns <= 0:
            return len(messages)
        start = max(0, len(assistant_indices) - n_turns)
        return assistant_indices[start]

    def _close_current_segment(self, kind: str = "solver") -> None:
        """Append accumulated messages as a named segment and reset the buffer."""
        msgs = self._current_segment_messages or self.messages
        if msgs:
            self._segments.append({"kind": kind, "messages": list(msgs)})
            self._current_segment_messages = []

    def _compact_messages(self) -> None:
        """Summarize old messages and replace history, keeping recent turns verbatim."""
        summarize_fn = getattr(self.model, "summarize_context", None)
        if not callable(summarize_fn):
            self.log("Model does not support summarize_context, skipping compaction")
            return

        prefix = self.messages[:2]  # system + task
        conversation = self.messages[2:]
        boundary = self._find_turn_boundary(conversation, self.config.compaction_keep_recent_turns)
        old_turns = conversation[:boundary]
        recent_turns = conversation[boundary:]

        if not old_turns:
            return

        self._close_current_segment("solver")

        summarizer_turns = (
            [
                {**m, "content": strip_compaction_board(m["content"])} if isinstance(m.get("content"), str) else m
                for m in old_turns
            ]
            if self._comm_coord.enabled
            else old_turns
        )
        summarizer_input = prefix + summarizer_turns
        summary_msg = summarize_fn(
            summarizer_input,
            summary_prompt=self.config.compaction_summary_prompt,
        )
        self._segments.append(
            {
                "kind": "summarizer",
                "messages": [
                    *[{k: v for k, v in m.items() if k != "extra"} for m in summarizer_input],
                    {"role": "user", "content": self.config.compaction_summary_prompt},
                    summary_msg,
                ],
            }
        )

        solver_summary_msg = summary_msg
        if self._comm_coord.enabled:
            board = self._comm_coord.render_compaction_board()
            if board:
                solver_summary_msg = {
                    **summary_msg,
                    "content": f"{summary_msg.get('content', '')}\n\n{board}",
                }

        self.messages = prefix + [solver_summary_msg] + recent_turns
        self._compaction_count += 1
        self.log(
            f"Compaction #{self._compaction_count}: {self._last_prompt_tokens} prompt tokens -> compacted "
            f"({len(old_turns)} messages summarized, {len(recent_turns)} kept)"
        )

    def query(self) -> dict:
        """Query the model and return model messages. Override to add hooks."""
        if 0 < self.config.step_limit <= self.n_calls or 0 < self.config.cost_limit <= self.cost:
            raise LimitsExceeded(
                {
                    "role": "exit",
                    "content": "LimitsExceeded",
                    "extra": {"exit_status": "LimitsExceeded", "submission": ""},
                }
            )
        if self._should_compact():
            self._compact_messages()
        self.n_calls += 1
        message = self.model.query(self.messages)
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self._last_prompt_tokens = self._get_prompt_tokens(message)
        self.add_messages(message)
        self._current_segment_messages = list(self.messages)
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        """Execute actions in message, add observation messages, return them.

        Only the ``bash`` tool is registered with the model (see adapter.py) —
        ``send_message`` is invoked by the agent embedding a shell command
        like ``send_message <recipient> <<'MSG' ... MSG`` inside the bash
        command string.  We parse any such calls out of the command, run
        them through the messaging connector, and execute the remainder (if
        any) against the docker env.  Single-tool registration is much
        more reliable for smaller models than exposing two tools.
        """
        actions = message.get("extra", {}).get("actions", [])
        outputs = []
        for action in actions:
            tool_name = action.get("tool_name", "bash")
            if tool_name == "send_message" and self.comm:
                # Defensive: supported for legacy callers that still
                # register send_message as a tool.
                outputs.append(self._handle_send_message(action))
                continue

            cmd = action.get("command", "")
            if self.comm and self._comm_coord.enabled:
                match self._comm_coord.parse_send_command(cmd):
                    case NoSendCommand():
                        env_out = self.env.execute(action)
                        self._comm_coord.record_action(
                            command=cmd,
                            returncode=int(env_out.get("returncode", 0)),
                            sent_message=False,
                        )
                        outputs.append(env_out)
                        continue
                    case SendParseError(message=err_msg):
                        self._comm_coord.record_action(command=cmd, returncode=1, sent_message=False)
                        outputs.append({"output": err_msg, "returncode": 1, "exception_info": ""})
                        continue
                    case ParsedSendBatch(calls=calls, remaining_command=remaining):
                        sm_results = [self._execute_comm_call(call) for call in calls]
                        combined = "\n".join(r["output"] for r in sm_results)
                        sm_rc = max((int(r.get("returncode", 0)) for r in sm_results), default=0)
                        if not remaining.strip():
                            self._comm_coord.record_action(
                                command="",
                                returncode=sm_rc,
                                sent_message=(sm_rc == 0),
                            )
                            outputs.append({"output": combined, "returncode": sm_rc, "exception_info": ""})
                            continue
                        env_out = self.env.execute({**action, "command": remaining})
                        final_rc = int(env_out.get("returncode", 0)) or sm_rc
                        self._comm_coord.record_action(
                            command=remaining,
                            returncode=final_rc,
                            sent_message=(sm_rc == 0),
                        )
                        env_out["output"] = combined + "\n" + env_out.get("output", "")
                        env_out["returncode"] = final_rc
                        outputs.append(env_out)
                        continue

            if self.comm:
                sm_matches = _parse_send_messages(cmd)
                if not sm_matches and re.search(r"\bsend_message\b", cmd):
                    # send_message is parsed out of the command string, not a real binary, so an
                    # unparsed one reaches bash and dies as `command not found` -- and the agent
                    # reads that as "messaging is broken" rather than "my quoting was wrong".
                    # Measured: 7 lost sends across two runs (bare --wait with no body,
                    # unterminated heredoc, `< file` redirect, `-t 60`, `timeout N bash -c ...`).
                    outputs.append(
                        {
                            "output": (
                                "send_message: could not parse that call, so nothing was sent.\n"
                                "Use one of:\n"
                                "  send_message [--wait] <agent> <<'MSG'\n  your text\n  MSG\n"
                                '  send_message [--wait] <agent> "your text"\n'
                                "The message body is required, and --wait takes no argument."
                            ),
                            "returncode": 1,
                            "exception_info": "",
                        }
                    )
                    continue
                if sm_matches:
                    sm_outputs = []
                    for recipient, content, wait in sm_matches:
                        r = self._handle_send_message({"recipient": recipient, "content": content, "wait": wait})
                        sm_outputs.append(r["output"])
                    remaining = _strip_send_message(cmd)
                    combined = "\n".join(sm_outputs)
                    if not remaining.strip():
                        outputs.append({"output": combined, "returncode": 0, "exception_info": ""})
                        continue
                    env_out = self.env.execute({**action, "command": remaining})
                    env_out["output"] = combined + "\n" + env_out.get("output", "")
                    outputs.append(env_out)
                    continue

            outputs.append(self.env.execute(action))
        observations = self.model.format_observation_messages(message, outputs, self.get_template_vars())
        return self.add_messages(*self._with_step_counter(list(observations)))

    def _with_step_counter(self, messages: list[dict]) -> list[dict]:
        """Append turn footers (active threads/obligations and "Step n of N") to the last observation.

        The step limit alone is not actionable: compaction drops the history the agent could
        count turns from, so it cannot tell step 12 from step 95. Showing the count on every
        turn keeps it visible in the last turns that compaction always keeps.
        """
        if not messages:
            return messages
        last = messages[-1]
        if last.get("role") == "exit" or not isinstance(last.get("content"), str):
            return messages

        footers: list[str] = []
        if self._comm_coord.enabled:
            comm_note = self._comm_coord.render_turn_footer(current_step=self.n_calls)
            if comm_note:
                footers.append(comm_note)
        if self.config.step_counter and self.config.step_limit > 0:
            left = max(self.config.step_limit - self.n_calls, 0)
            footers.append(
                f"[Step {self.n_calls} of {self.config.step_limit}: {left} left. When no steps are left you "
                "are stopped, and only work you have pushed and submitted is graded.]"
            )
        if not footers:
            return messages
        suffix = "".join(f"\n\n{note}" for note in footers)
        messages[-1] = {**last, "content": f"{last['content']}{suffix}"}
        return messages

    def _announce_departed_peers(self) -> None:
        """Tell the agent, once, when a peer has finished and left.

        Otherwise an agent can spend the rest of its run waiting for an answer from a
        colleague who is no longer running, with nothing in its context to indicate that.
        Announced once per peer; the recovery path is named because the peer's work is
        still reachable through git even though the conversation is over.
        """
        if not self.comm:
            return
        announced = getattr(self, "_departed_announced", None)
        if announced is None:
            announced = self._departed_announced = set()
        for peer in getattr(self.comm, "agents", []) or []:
            if peer == self.comm.agent_id or peer in announced:
                continue
            if not self.comm.has_exited(peer):
                continue
            announced.add(peer)
            self._comm_coord.clear_peer_obligations(peer)
            gone = getattr(self.comm, "is_unreachable", None) and self.comm.is_unreachable(peer)
            self.log(f"PEER {'UNREACHABLE' if gone else 'EXITED'}: {peer}")
            headline = (
                f"[{peer} is no longer running] They stopped without submitting, so nothing "
                f"further will arrive from them."
                if gone
                else f"[{peer} has completed their work and exited] They will not read or answer further messages."
            )
            self.add_messages(
                self.model.format_message(
                    role="user",
                    content=f"{headline}\n\n{self._peer_work_pointer(peer)}",
                )
            )

    def _peer_work_pointer(self, peer: str) -> str:
        """Where to find a departed peer's work — only claimed when it is really there.

        Publication to the shared remote is best-effort, so asserting the branch holds
        their submission when it does not would repeat exactly the failure this whole
        change exists to remove: telling the agent something untrue and letting it act
        on it.
        """
        if self.comm and self.comm.has_published(peer):
            return (
                f"Their submitted patch is on branch {GIT_REMOTE}/{peer}. If your changes "
                f"overlap theirs, inspect and reconcile before you submit:\n"
                f"    git fetch {GIT_REMOTE} && git diff HEAD...{GIT_REMOTE}/{peer}"
            )
        return (
            f"Their work could NOT be published to {GIT_REMOTE}/{peer}, so that branch does "
            f"not reflect what they submitted — do not rely on it. Proceed on your own "
            f"judgement and keep your changes as self-contained as you can."
        )

    def _handle_send_message(self, action: dict) -> dict:
        """Handle a send_message call via the messaging connector.

        ``wait=True`` (when the agent wrote ``send_message --wait ...`` in bash) blocks
        until the peer replies, the peer exits, or the timeout elapses.

        A send to a peer that has already finished is reported as a failure, not a
        success.  Reporting success there is actively misleading: the agent believes it
        has coordinated, keeps waiting for an answer that cannot arrive, and ships work
        that was never reconciled.
        """
        recipient = action.get("recipient", "")
        content = action.get("content", "")
        wait = action.get("wait", False)

        if wait and hasattr(self.comm, "send_and_wait"):
            delivered, replies = self.comm.send_and_wait(recipient, content, timeout=60)
            if not delivered:
                return self._peer_gone_result(recipient)
            self.log(f"SENT (blocking) to {recipient}: {content[:80]}...")
            self.sent_messages.append({"to": recipient, "content": content})
            output = f"Message sent to {recipient}"
            if replies:
                for r in replies:
                    output += f"\n\n[Reply from {r['from']}]: {r['content']}"
            elif self.comm.has_exited(recipient):
                output += (
                    f"\n\nNo reply: {recipient} has since completed their work and exited.\n"
                    f"{self._peer_work_pointer(recipient)}"
                )
            return {"output": output, "returncode": 0, "exception_info": ""}

        if not self.comm.send(recipient, content):
            return self._peer_gone_result(recipient)
        self.log(f"SENT to {recipient}: {content[:80]}...")
        self.sent_messages.append({"to": recipient, "content": content})
        return {"output": f"Message sent to {recipient}", "returncode": 0, "exception_info": ""}

    def _execute_comm_call(self, call: SendCall) -> dict:
        """Dispatch a validated SendCall when opt-in communication features are active."""
        assert self.comm is not None
        if call.wait and hasattr(self.comm, "send_and_wait"):
            delivered, replies = self.comm.send_and_wait(
                call.recipient,
                call.content,
                timeout=60,
                assign_id=self.config.message_threading,
                reply_to=call.reply_to,
                resolve=call.resolve,
                intent=call.intent,
            )
            if not delivered:
                self._comm_coord.clear_peer_obligations(call.recipient)
                return self._peer_gone_result(call.recipient)
            sent_meta = dict(getattr(self.comm, "last_sent_message", None) or {})
            self.log(f"SENT (blocking) to {call.recipient}: {call.content[:80]}...")
            self.sent_messages.append(self._build_sent_record(call, sent_meta))
            output = self._comm_coord.record_outgoing(call, sent_meta, current_step=self.n_calls)
            if replies:
                for line in self._comm_coord.record_wait_replies(replies, current_step=self.n_calls):
                    output += f"\n\n{line}"
            elif self.comm.has_exited(call.recipient):
                self._comm_coord.clear_peer_obligations(call.recipient)
                output += (
                    f"\n\nNo reply: {call.recipient} has since completed their work and exited.\n"
                    f"{self._peer_work_pointer(call.recipient)}"
                )
            return {"output": output, "returncode": 0, "exception_info": ""}

        if not self.comm.send(
            call.recipient,
            call.content,
            assign_id=self.config.message_threading,
            reply_to=call.reply_to,
            resolve=call.resolve,
            intent=call.intent,
        ):
            self._comm_coord.clear_peer_obligations(call.recipient)
            return self._peer_gone_result(call.recipient)
        sent_meta = dict(getattr(self.comm, "last_sent_message", None) or {})
        self.log(f"SENT to {call.recipient}: {call.content[:80]}...")
        self.sent_messages.append(self._build_sent_record(call, sent_meta))
        output = self._comm_coord.record_outgoing(call, sent_meta, current_step=self.n_calls)
        return {"output": output, "returncode": 0, "exception_info": ""}

    @staticmethod
    def _build_sent_record(call: SendCall, sent_meta: dict[str, Any]) -> dict[str, Any]:
        record: dict[str, Any] = {
            "to": call.recipient,
            "content": call.content,
            "timestamp": time.time(),
        }
        if sent_meta.get("id"):
            record["id"] = sent_meta["id"]
        if call.reply_to:
            record["reply_to"] = call.reply_to
        if call.resolve:
            record["resolve"] = True
        if call.intent:
            record["intent"] = call.intent
        return record

    def _peer_gone_result(self, recipient: str) -> dict:
        """Tell the agent its peer is gone, and what to do about it.

        Phrased as a terminal state rather than a delivery error so the agent does not
        retry, and names the recovery path so the peer's work is still reachable.
        """
        self.log(f"NOT DELIVERED to {recipient}: peer already exited")
        return {
            "output": (
                f"{recipient} has already completed their work and exited. Your message was "
                f"NOT delivered and no reply will come — do not send further messages to "
                f"them.\n\n{self._peer_work_pointer(recipient)}"
            ),
            "returncode": 1,
            "exception_info": "",
        }

    def serialize(self, *extra_dicts) -> dict:
        """Serialize agent state to a json-compatible nested dictionary for saving."""
        last_message = self.messages[-1] if self.messages else {}
        last_extra = last_message.get("extra", {})
        agent_data = {
            "info": {
                "model_stats": {
                    "instance_cost": self.cost,
                    "api_calls": self.n_calls,
                },
                "config": {
                    "agent": self.config.model_dump(mode="json"),
                    "agent_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                },
                "mini_version": __version__,
                "exit_status": last_extra.get("exit_status", ""),
                "submission": last_extra.get("submission", ""),
            },
            "messages": self.messages,
            "trajectory_format": "mini-swe-agent-1.1",
        }
        if self._compaction_count > 0:
            segments = list(self._segments)
            current = self._current_segment_messages or self.messages
            if current:
                segments.append({"kind": "solver", "messages": list(current)})
            agent_data["segments"] = segments
        return recursive_merge(agent_data, self.model.serialize(), self.env.serialize(), *extra_dicts)

    def save(self, path: Path | None, *extra_dicts) -> dict:
        """Save the trajectory of the agent to a file if path is given. Returns full serialized data.
        You can pass additional dictionaries with extra data to be (recursively) merged into the output data.
        """
        data = self.serialize(*extra_dicts)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2))
        return data


def _parse_send_messages(cmd: str) -> list[tuple[str, str, bool]]:
    """Extract (recipient, content, wait) tuples from send_message calls.

    ``--wait`` may appear before or after the recipient.  Supports three
    formats: heredoc (``<<'MSG'``), double-quoted, single-quoted.
    """
    matches: list[tuple[str, str, bool]] = []
    for m in re.finditer(
        r"send_message\s+(--wait\s+)?(\w+)(\s+--wait)?\s+<<'?(\w+)'?\s*\n(.*?)\n\4",
        cmd,
        re.DOTALL,
    ):
        wait = bool(m.group(1) or m.group(3))
        matches.append((m.group(2), m.group(5), wait))
    if not matches:
        for m in re.finditer(r'send_message\s+(--wait\s+)?(\w+)(\s+--wait)?\s+"([^"]*)"', cmd):
            wait = bool(m.group(1) or m.group(3))
            matches.append((m.group(2), m.group(4), wait))
        for m in re.finditer(r"send_message\s+(--wait\s+)?(\w+)(\s+--wait)?\s+'([^']*)'", cmd):
            wait = bool(m.group(1) or m.group(3))
            matches.append((m.group(2), m.group(4), wait))
    return matches


def _strip_send_message(cmd: str) -> str:
    """Remove send_message calls from a compound bash command."""
    cmd = re.sub(
        r"send_message\s+(--wait\s+)?\w+(\s+--wait)?\s+<<'?(\w+)'?\s*\n.*?\n\3",
        "",
        cmd,
        flags=re.DOTALL,
    )
    cmd = re.sub(r'send_message\s+(--wait\s+)?\w+(\s+--wait)?\s+"[^"]*"', "", cmd)
    cmd = re.sub(r"send_message\s+(--wait\s+)?\w+(\s+--wait)?\s+'[^']*'", "", cmd)
    cmd = re.sub(r"^\s*&&\s*", "", cmd)
    cmd = re.sub(r"\s*&&\s*$", "", cmd)
    cmd = re.sub(r"&&\s*&&", "&&", cmd)
    cmd = re.sub(r"\|\|\s*\|\|", "||", cmd)
    return cmd.strip()
