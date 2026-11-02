"""Opt-in communication interventions for Mini-SWE-Agent v2.

Implements three composable coordination mechanisms behind AgentConfig flags:
1. Message Delivery Timing: holds non-blocking incoming messages until natural turn
   boundaries (clean test/git/PR commands, messaging turns, or explore-to-edit shifts)
   or a configurable step ceiling.
2. Message Board / Threading: assigns monotonic run-scoped message IDs (m1, m2, ...)
   and tracks open vs. resolved threads via explicit --reply-to / --resolve flags,
   pinning active threads across turns and across context compactions.
3. Message Intent Tags: enforces explicit speech-act intents (Proposal, Request,
   Response, ACK, FYI), prioritizes incoming Request/Proposal obligations above FYI
   chatter, optionally filters FYI updates, and optionally checks open obligations on exit.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

CANONICAL_INTENTS: dict[str, str] = {
    "proposal": "Proposal",
    "request": "Request",
    "response": "Response",
    "ack": "ACK",
    "fyi": "FYI",
}
INTENT_DISPLAY_ORDER = ("Proposal", "Request", "Response", "ACK", "FYI")
OBLIGATION_INTENTS = frozenset({"Proposal", "Request"})
RESOLUTION_INTENTS = frozenset({"Response", "ACK"})

_INTENT_PRIORITY: dict[str, int] = {
    "Request": 0,
    "Proposal": 0,
    "Response": 1,
    "ACK": 1,
    "FYI": 2,
}

_SEND_WORD_RE = re.compile(r"(?<![\w-])send_message\b")

_SEND_HEREDOC_RE = re.compile(
    r"""
    (?<![\w-])send_message
    (?P<header>[ \t]+[^\n]*?)
    [ \t]*<<-?[ \t]*['"]?(?P<tag>\w+)['"]?[ \t]*\n
    (?P<body>.*?)
    \n[ \t]*(?P=tag)(?=\s|$|[;&|])
    """,
    re.DOTALL | re.VERBOSE,
)

_SEND_QUOTED_RE = re.compile(
    r"""
    (?<![\w-])send_message
    (?P<header>(?:[ \t]+(?:[^\s;&|'"]+|"(?:\\.|[^"\\])*"|'[^']*'))+)
    [ \t]+(?:
        "(?P<dq>(?:\\.|[^"\\])*)"
        |
        '(?P<sq>[^']*)'
    )
    (?=\s|$|[;&|])
    """,
    re.VERBOSE,
)

_BODY_INTENT_PREFIX_RE = re.compile(
    r"""
    ^\s*(?:
        \[(?P<bracket>proposal|request|response|ack|fyi)\]
        |
        (?P<colon>proposal|request|response|ack|fyi)\s*:
    )\s*(?P<rest>.*)$
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE,
)

_VERIFY_OR_GIT_RE = re.compile(
    r"""
    \b(?:
        pytest | py\.test | unittest | tox | nox
        | go\s+test | cargo\s+(?:test|check)
        | (?:npm|yarn|pnpm)\s+test | jest | vitest | typst\s+compile
        | git\s+(?:status|diff|commit|push|fetch|pull|merge)
        | gh\s+pr\b
    )\b
    """,
    re.VERBOSE,
)

_FILE_EDIT_RE = re.compile(
    r"""
    (?:
        \b(?:sed|perl)\s+-[^\n]*i\b
        | \bgit\s+apply\b
        | \bpatch\b
        | \btee\s+
        | <<-?\s*['"]?\w+['"]?[^\n]*>
        | (?<![2>&=-])>(?!>|&|/dev/null)
        | \.write_text\s*\(
        | \bopen\s*\([^)]*,\s*['"][wa]
    )
    """,
    re.VERBOSE,
)

_READ_EXPLORE_RE = re.compile(
    r"""
    \b(?:
        ls | find | grep | rg | ag | nl | head | tail | wc
        | sed\s+-n | cat\b | git\s+(?:log|show|blame)
    )\b
    """,
    re.VERBOSE,
)

COMPACTION_BOARD_HEADING = "## ACTIVE THREAD BOARD (HARNESS-PINNED)"


class ActionKind(Enum):
    """Coarse classification of a solver turn's bash command for boundary detection."""

    NONE = "none"
    MESSAGE = "message"
    READ_EXPLORE = "read_explore"
    FILE_EDIT = "file_edit"
    VERIFY_OR_GIT = "verify_or_git"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SendCall:
    """Validated outgoing send_message invocation."""

    recipient: str
    content: str
    wait: bool = False
    reply_to: str | None = None
    resolve: bool = False
    intent: str | None = None


@dataclass(frozen=True, slots=True)
class NoSendCommand:
    """Bash command contains no send_message invocation."""


@dataclass(frozen=True, slots=True)
class SendParseError:
    """Bash command attempted send_message with invalid flags or missing required metadata."""

    message: str


@dataclass(frozen=True, slots=True)
class ParsedSendBatch:
    """One or more valid send_message calls extracted from a bash command."""

    calls: tuple[SendCall, ...]
    remaining_command: str


SendParseResult = NoSendCommand | SendParseError | ParsedSendBatch


@dataclass(frozen=True, slots=True)
class HeldMessage:
    """Incoming non-blocking message buffered until an opportune turn boundary."""

    raw: dict[str, Any]
    arrived_step: int


@dataclass(slots=True)
class ThreadEntry:
    """Tracked conversation thread keyed by its root message ID."""

    thread_id: str
    opened_by: str
    opened_step: int
    last_sender: str
    last_message_id: str
    last_step: int
    last_intent: str | None
    root_summary: str
    last_summary: str
    status: Literal["open", "resolved"] = "open"


@dataclass(frozen=True, slots=True)
class IntentObligation:
    """Unanswered incoming Request or Proposal when standalone intent tagging is active."""

    sender: str
    intent: str
    arrived_step: int
    summary: str


@dataclass(frozen=True, slots=True)
class CommunicationSettings:
    """Configuration slice controlling opt-in communication features."""

    delivery_timing: bool = False
    delivery_max_hold_steps: int = 4
    delivery_boundary_mode: Literal["natural", "periodic"] = "natural"
    message_threading: bool = False
    thread_pin_mode: Literal["every_turn", "compaction_only"] = "every_turn"
    thread_max_pinned: int = 3
    thread_require_resolved_on_submit: bool = False
    message_intents: bool = False
    intent_filter_fyi: bool = False
    intent_presubmit_check: bool = False

    @property
    def enabled(self) -> bool:
        return self.delivery_timing or self.message_threading or self.message_intents


@dataclass
class CommunicationCoordinator:
    """Per-agent state machine managing delivery timing, thread state, and intent obligations."""

    agent_id: str
    settings: CommunicationSettings
    _held_inbox: list[HeldMessage] = field(default_factory=list)
    _threads: dict[str, ThreadEntry] = field(default_factory=dict)
    _message_to_thread: dict[str, str] = field(default_factory=dict)
    _fyi_roots: dict[str, dict[str, Any]] = field(default_factory=dict)
    _intent_obligations: list[IntentObligation] = field(default_factory=list)
    _prev_action_kind: ActionKind = ActionKind.NONE
    _last_action_kind: ActionKind = ActionKind.NONE
    _last_returncode: int = 0

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    @property
    def has_held_messages(self) -> bool:
        return bool(self._held_inbox)

    def parse_send_command(self, cmd: str) -> SendParseResult:
        """Parse and validate send_message calls embedded in a bash command string."""
        if not _SEND_WORD_RE.search(cmd):
            return NoSendCommand()

        spans, raw_calls = _extract_raw_send_spans(cmd)
        if not raw_calls:
            return SendParseError(self._format_usage_error("could not parse that call"))

        validated: list[SendCall] = []
        for header, body in raw_calls:
            parsed = self._validate_single_call(header, body)
            if isinstance(parsed, SendParseError):
                return parsed
            validated.append(parsed)

        remaining = _strip_spans(cmd, spans)
        return ParsedSendBatch(calls=tuple(validated), remaining_command=remaining)

    def record_outgoing(self, call: SendCall, sent_msg: dict[str, Any], current_step: int) -> str:
        """Update thread and obligation state for a delivered outgoing message and format confirmation."""
        if self.settings.message_threading:
            msg_id = str(sent_msg.get("id") or "")
            self._apply_thread_event(
                msg_id=msg_id,
                sender=self.agent_id,
                content=call.content,
                reply_to=call.reply_to,
                resolve=call.resolve,
                intent=call.intent,
                step=current_step,
            )
        if self.settings.message_intents and call.intent in (RESOLUTION_INTENTS | {"Proposal"}):
            self._intent_obligations = [ob for ob in self._intent_obligations if ob.sender != call.recipient]

        return self._format_send_confirmation(call, sent_msg)

    def receive_for_step(
        self,
        incoming: list[dict[str, Any]],
        *,
        current_step: int,
        is_awaited_fn: Any,
    ) -> list[str]:
        """Process newly polled inbox messages and return formatted strings ready for injection."""
        deliver_now: list[dict[str, Any]] = []

        for msg in incoming:
            sender = msg.get("from", "")
            awaited = bool(callable(is_awaited_fn) and is_awaited_fn(sender))
            intent = _normalize_wire_intent(msg.get("intent"), msg.get("content", ""))
            if intent and "intent" not in msg:
                msg = {**msg, "intent": intent}

            if self.settings.message_intents and self.settings.intent_filter_fyi and intent == "FYI" and not awaited:
                # Register ID if present so peer --reply-to references remain valid, then drop.
                if msg.get("id"):
                    self._fyi_roots[str(msg["id"])] = msg
                    self._message_to_thread.setdefault(str(msg["id"]), str(msg["id"]))
                continue

            urgent = awaited or (self.settings.message_intents and intent in OBLIGATION_INTENTS)
            if not self.settings.delivery_timing or urgent:
                deliver_now.append(msg)
            else:
                self._held_inbox.append(HeldMessage(raw=msg, arrived_step=current_step))

        if self._held_inbox and self._should_flush_held(current_step):
            deliver_now.extend(item.raw for item in self._held_inbox)
            self._held_inbox.clear()

        return self._finalize_delivery(deliver_now, current_step=current_step, is_awaited_fn=is_awaited_fn)

    def flush_all_held(self, *, current_step: int, is_awaited_fn: Any = None) -> list[str]:
        """Force-flush all buffered messages (used before agent exit)."""
        if not self._held_inbox:
            return []
        batch = [item.raw for item in self._held_inbox]
        self._held_inbox.clear()
        return self._finalize_delivery(batch, current_step=current_step, is_awaited_fn=is_awaited_fn)

    def record_wait_replies(self, replies: list[dict[str, Any]], *, current_step: int) -> list[str]:
        """Record replies received synchronously via send_message --wait and format them."""
        formatted: list[str] = []
        for reply in replies:
            intent = _normalize_wire_intent(reply.get("intent"), reply.get("content", ""))
            if intent and "intent" not in reply:
                reply = {**reply, "intent": intent}
            self._ingest_delivered_message(reply, current_step=current_step)
            formatted.append(self._format_incoming_line(reply, blocked_suffix="", prefix_label="Reply"))
        return formatted

    def record_action(self, *, command: str, returncode: int, sent_message: bool) -> None:
        """Record the completed bash turn's outcome to inform next-step natural boundary checks."""
        self._prev_action_kind = self._last_action_kind
        self._last_action_kind = (
            ActionKind.MESSAGE if sent_message and not command.strip() else classify_command(command)
        )
        self._last_returncode = returncode

    def clear_peer_obligations(self, peer: str) -> None:
        """Clear pending pre-submit obligations from a peer that has exited."""
        self._intent_obligations = [ob for ob in self._intent_obligations if ob.sender != peer]

    def render_turn_footer(self, *, current_step: int) -> str:
        """Render a concise active-obligation footer for the end of a turn's tool observation."""
        if self.settings.message_threading and self.settings.thread_pin_mode == "every_turn":
            open_threads = self._sorted_open_threads()
            if not open_threads:
                return ""
            limit = self.settings.thread_max_pinned
            shown = open_threads[:limit] if limit > 0 else open_threads
            lines = [f"[Open threads ({len(open_threads)}):"]
            for entry in shown:
                age = max(current_step - entry.last_step, 0)
                age_str = f"{age} step{'s' if age != 1 else ''} ago"
                intent_tag = f" [{entry.last_intent}]" if (self.settings.message_intents and entry.last_intent) else ""
                if entry.last_sender != self.agent_id:
                    status_hint = f"from {entry.last_sender}, {age_str} — reply needed"
                    action_hint = f" — reply with --reply-to {entry.thread_id} (add --resolve when settled)"
                else:
                    status_hint = f"awaiting colleague, {age_str}"
                    action_hint = ""
                lines.append(f'- {entry.thread_id}{intent_tag} ({status_hint}): "{entry.last_summary}"{action_hint}')
            if len(open_threads) > len(shown):
                lines.append(f"- ... and {len(open_threads) - len(shown)} more open thread(s)")
            lines[-1] += "]"
            return "\n".join(lines)

        if self.settings.message_intents and not self.settings.message_threading and self._intent_obligations:
            lines = [f"[Pending colleague requests/proposals ({len(self._intent_obligations)}):"]
            for ob in self._intent_obligations[:3]:
                age = max(current_step - ob.arrived_step, 0)
                age_str = f"{age} step{'s' if age != 1 else ''} ago"
                lines.append(
                    f'- [{ob.intent}] from {ob.sender} ({age_str}): "{ob.summary}" '
                    f"— reply with --intent ACK or --intent Response"
                )
            lines[-1] += "]"
            return "\n".join(lines)

        return ""

    def render_compaction_board(self) -> str:
        """Render authoritative thread and obligation state to append to compaction summaries."""
        sections: list[str] = []

        if self.settings.message_threading and self._threads:
            open_threads = self._sorted_open_threads()
            resolved_threads = [t for t in self._threads.values() if t.status == "resolved"]
            if open_threads:
                lines = ["Open threads (require follow-up or --resolve):"]
                for entry in open_threads:
                    intent_tag = f" [{entry.last_intent}]" if entry.last_intent else ""
                    lines.append(
                        f"- {entry.thread_id}{intent_tag} (last from {entry.last_sender}): "
                        f'root="{entry.root_summary}" | latest="{entry.last_summary}"'
                    )
                sections.append("\n".join(lines))
            if resolved_threads:
                lines = ["Resolved agreements (keep honoring these boundaries):"]
                for entry in resolved_threads[-5:]:
                    lines.append(f'- {entry.thread_id}: "{entry.last_summary}"')
                sections.append("\n".join(lines))
        elif self.settings.message_intents and self._intent_obligations:
            lines = ["Unanswered colleague requests/proposals:"]
            for ob in self._intent_obligations:
                lines.append(f'- [{ob.intent}] from {ob.sender}: "{ob.summary}"')
            sections.append("\n".join(lines))

        if not sections:
            return ""
        return COMPACTION_BOARD_HEADING + "\n" + "\n\n".join(sections)

    def pending_presubmit_obligations(self, *, is_peer_exited_fn: Any) -> list[str]:
        """Return human-readable descriptions of unanswered incoming obligations from live peers."""
        items: list[str] = []

        if self.settings.message_threading and (
            self.settings.thread_require_resolved_on_submit
            or (self.settings.message_intents and self.settings.intent_presubmit_check)
        ):
            for entry in self._sorted_open_threads():
                if entry.last_sender == self.agent_id:
                    continue
                if callable(is_peer_exited_fn) and is_peer_exited_fn(entry.last_sender):
                    continue
                if self.settings.message_intents and entry.last_intent not in OBLIGATION_INTENTS:
                    continue
                intent_tag = f" [{entry.last_intent}]" if entry.last_intent else ""
                items.append(
                    f'- Thread {entry.thread_id}{intent_tag} from {entry.last_sender}: "{entry.last_summary}" '
                    f"(reply with --reply-to {entry.thread_id} --resolve)"
                )
            return items

        if self.settings.message_intents and self.settings.intent_presubmit_check:
            for ob in self._intent_obligations:
                if callable(is_peer_exited_fn) and is_peer_exited_fn(ob.sender):
                    continue
                items.append(
                    f'- [{ob.intent}] from {ob.sender}: "{ob.summary}" (reply with --intent ACK or --intent Response)'
                )

        return items

    def _validate_single_call(self, header: str, raw_body: str) -> SendCall | SendParseError:
        try:
            tokens = shlex.split(header)
        except ValueError as exc:
            return SendParseError(self._format_usage_error(f"invalid quoting in arguments ({exc})"))

        wait = False
        resolve = False
        reply_to: str | None = None
        raw_intent: str | None = None
        positionals: list[str] = []

        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if tok == "--wait":
                wait = True
            elif tok == "--resolve":
                if not self.settings.message_threading:
                    return SendParseError(self._format_usage_error("unknown option '--resolve'"))
                resolve = True
            elif tok == "--reply-to" or tok.startswith("--reply-to="):
                if not self.settings.message_threading:
                    return SendParseError(self._format_usage_error("unknown option '--reply-to'"))
                if tok == "--reply-to":
                    if idx + 1 >= len(tokens):
                        return SendParseError(self._format_usage_error("--reply-to requires a message id (e.g. m1)"))
                    idx += 1
                    val = tokens[idx]
                else:
                    val = tok.split("=", 1)[1]
                reply_to = val.lstrip("#").strip()
            elif tok == "--intent" or tok.startswith("--intent="):
                if not self.settings.message_intents:
                    return SendParseError(self._format_usage_error("unknown option '--intent'"))
                if tok == "--intent":
                    if idx + 1 >= len(tokens):
                        return SendParseError(
                            self._format_usage_error(f"--intent requires one of: {', '.join(INTENT_DISPLAY_ORDER)}")
                        )
                    idx += 1
                    val = tokens[idx]
                else:
                    val = tok.split("=", 1)[1]
                raw_intent = val.strip()
            elif tok.startswith("-"):
                return SendParseError(self._format_usage_error(f"unknown option '{tok}'"))
            else:
                positionals.append(tok)
            idx += 1

        if len(positionals) != 1 or not re.fullmatch(r"\w+", positionals[0]):
            return SendParseError(self._format_usage_error("expected exactly one <agent> recipient"))
        recipient = positionals[0]

        intent: str | None = None
        body = raw_body
        if not body.strip():
            return SendParseError(self._format_usage_error("message body cannot be empty"))
        if self.settings.message_intents:
            if raw_intent is not None:
                intent = CANONICAL_INTENTS.get(raw_intent.lower())
                if intent is None:
                    return SendParseError(
                        f"send_message: invalid --intent '{raw_intent}', so nothing was sent.\n"
                        f"Choose one of: {', '.join(INTENT_DISPLAY_ORDER)}."
                    )
            else:
                extracted_intent, cleaned_body = _extract_body_intent(body)
                if extracted_intent is None:
                    return SendParseError(
                        "send_message: missing required --intent tag, so nothing was sent.\n"
                        f"Specify --intent <{'|'.join(INTENT_DISPLAY_ORDER)}>, e.g.:\n"
                        f"  send_message --intent Request {recipient} <<'MSG'\n  your text\n  MSG"
                    )
                intent, body = extracted_intent, cleaned_body

        if self.settings.message_threading:
            if resolve and not reply_to:
                return SendParseError("send_message: --resolve requires --reply-to <message_id>, so nothing was sent.")
            if reply_to:
                if reply_to not in self._message_to_thread:
                    known = ", ".join(sorted(self._message_to_thread, key=_msg_id_sort_key)) or "none yet"
                    return SendParseError(
                        f"send_message: unknown --reply-to id '{reply_to}' (known ids: {known}), so nothing was sent."
                    )
                if self.settings.message_intents and intent == "ACK":
                    resolve = True

        return SendCall(
            recipient=recipient,
            content=body,
            wait=wait,
            reply_to=reply_to,
            resolve=resolve,
            intent=intent,
        )

    def _should_flush_held(self, current_step: int) -> bool:
        if not self._held_inbox:
            return False
        if current_step == 0:
            return True
        oldest_age = current_step - self._held_inbox[0].arrived_step
        if oldest_age >= self.settings.delivery_max_hold_steps:
            return True
        if self.settings.delivery_boundary_mode == "periodic":
            return False
        if self._last_returncode != 0:
            return False
        if self._last_action_kind in (ActionKind.VERIFY_OR_GIT, ActionKind.MESSAGE):
            return True
        return self._prev_action_kind == ActionKind.READ_EXPLORE and self._last_action_kind == ActionKind.FILE_EDIT

    def _finalize_delivery(
        self,
        batch: list[dict[str, Any]],
        *,
        current_step: int,
        is_awaited_fn: Any,
    ) -> list[str]:
        if not batch:
            return []

        if self.settings.message_intents:
            batch = sorted(
                batch,
                key=lambda m: (
                    0 if (callable(is_awaited_fn) and is_awaited_fn(m.get("from", ""))) else 1,
                    _INTENT_PRIORITY.get(str(m.get("intent") or ""), 1),
                ),
            )

        rendered: list[str] = []
        for msg in batch:
            self._ingest_delivered_message(msg, current_step=current_step)
            sender = msg.get("from", "")
            blocked_suffix = ""
            if callable(is_awaited_fn) and is_awaited_fn(sender):
                blocked_suffix = (
                    f" — {sender} is BLOCKED waiting for your reply and cannot continue"
                    " until you answer. Reply with send_message before your next command."
                )
            rendered.append(self._format_incoming_line(msg, blocked_suffix=blocked_suffix, prefix_label="Message"))
        return rendered

    def _ingest_delivered_message(self, msg: dict[str, Any], *, current_step: int) -> None:
        sender = str(msg.get("from") or "")
        content = str(msg.get("content") or "")
        intent = msg.get("intent")
        reply_to = msg.get("reply_to")
        resolve = bool(msg.get("resolve")) or (self.settings.message_intents and intent == "ACK" and bool(reply_to))

        if self.settings.message_threading:
            msg_id = str(msg.get("id") or "")
            if msg_id:
                self._apply_thread_event(
                    msg_id=msg_id,
                    sender=sender,
                    content=content,
                    reply_to=reply_to,
                    resolve=resolve,
                    intent=intent,
                    step=current_step,
                )

        if self.settings.message_intents:
            if intent in OBLIGATION_INTENTS and sender != self.agent_id:
                self._intent_obligations.append(
                    IntentObligation(
                        sender=sender,
                        intent=intent,
                        arrived_step=current_step,
                        summary=_summarize_snippet(content),
                    )
                )
            elif intent in RESOLUTION_INTENTS and sender != self.agent_id:
                # Peer sent ACK/Response; no incoming obligation created.
                pass

    def _apply_thread_event(
        self,
        *,
        msg_id: str,
        sender: str,
        content: str,
        reply_to: str | None,
        resolve: bool,
        intent: str | None,
        step: int,
    ) -> None:
        if not msg_id:
            return
        snippet = _summarize_snippet(content)

        if reply_to:
            root_id = self._message_to_thread.get(reply_to, reply_to)
            self._message_to_thread[msg_id] = root_id
            entry = self._threads.get(root_id)
            if entry is None:
                fyi_seed = self._fyi_roots.get(root_id)
                root_summary = _summarize_snippet(str(fyi_seed.get("content", ""))) if fyi_seed else snippet
                opened_by = str(fyi_seed.get("from", sender)) if fyi_seed else sender
                entry = ThreadEntry(
                    thread_id=root_id,
                    opened_by=opened_by,
                    opened_step=step,
                    last_sender=sender,
                    last_message_id=msg_id,
                    last_step=step,
                    last_intent=intent,
                    root_summary=root_summary,
                    last_summary=snippet,
                    status="resolved" if resolve else "open",
                )
                self._threads[root_id] = entry
                return

            entry.last_sender = sender
            entry.last_message_id = msg_id
            entry.last_step = step
            entry.last_intent = intent
            entry.last_summary = snippet
            if resolve:
                entry.status = "resolved"
            elif entry.status == "resolved" and (not self.settings.message_intents or intent in OBLIGATION_INTENTS):
                entry.status = "open"
            return

        self._message_to_thread[msg_id] = msg_id
        if self.settings.message_intents and intent == "FYI":
            self._fyi_roots[msg_id] = {"from": sender, "content": content}
            return

        self._threads[msg_id] = ThreadEntry(
            thread_id=msg_id,
            opened_by=sender,
            opened_step=step,
            last_sender=sender,
            last_message_id=msg_id,
            last_step=step,
            last_intent=intent,
            root_summary=snippet,
            last_summary=snippet,
            status="open",
        )

    def _sorted_open_threads(self) -> list[ThreadEntry]:
        open_entries = [t for t in self._threads.values() if t.status == "open"]
        return sorted(
            open_entries,
            key=lambda t: (
                0 if t.last_sender != self.agent_id else 1,
                _INTENT_PRIORITY.get(t.last_intent or "", 1) if self.settings.message_intents else 0,
                _msg_id_sort_key(t.thread_id),
            ),
        )

    def _format_send_confirmation(self, call: SendCall, sent_msg: dict[str, Any]) -> str:
        meta: list[str] = []
        if self.settings.message_threading and sent_msg.get("id"):
            meta.append(f"id: {sent_msg['id']}")
            if call.reply_to:
                root_id = self._message_to_thread.get(call.reply_to, call.reply_to)
                state = "resolved" if call.resolve else "open"
                meta.append(f"thread {root_id}: {state}")
        if self.settings.message_intents and call.intent:
            meta.append(f"intent: {call.intent}")
        suffix = f" ({', '.join(meta)})" if meta else ""
        return f"Message sent to {call.recipient}{suffix}"

    def _format_incoming_line(self, msg: dict[str, Any], *, blocked_suffix: str, prefix_label: str) -> str:
        sender = msg.get("from", "peer")
        content = msg.get("content", "")
        msg_id = msg.get("id") if self.settings.message_threading else None
        reply_to = msg.get("reply_to") if self.settings.message_threading else None
        resolved = bool(msg.get("resolve")) or (
            self.settings.message_intents and msg.get("intent") == "ACK" and bool(reply_to)
        )
        intent = msg.get("intent") if self.settings.message_intents else None

        head = f"{prefix_label} {msg_id} from {sender}" if msg_id else f"{prefix_label} from {sender}"
        tags: list[str] = []
        if reply_to:
            root_id = self._message_to_thread.get(str(reply_to), str(reply_to))
            tags.append(f"reply to {root_id}, resolved" if resolved else f"reply to {root_id}")
        if intent:
            if intent in OBLIGATION_INTENTS and not resolved:
                tags.append(f"{intent} — reply needed")
            else:
                tags.append(str(intent))
        tag_str = f" ({'; '.join(tags)})" if tags else ""
        return f"[{head}{tag_str}{blocked_suffix}]: {content}"

    def _format_usage_error(self, detail: str) -> str:
        flags = ["[--wait]"]
        if self.settings.message_intents:
            flags.append(f"--intent <{'|'.join(INTENT_DISPLAY_ORDER)}>")
        if self.settings.message_threading:
            flags.append("[--reply-to <id> [--resolve]]")
        flag_str = " ".join(flags)
        return (
            f"send_message: {detail}, so nothing was sent.\n"
            "Use one of:\n"
            f"  send_message {flag_str} <agent> <<'MSG'\n  your text\n  MSG\n"
            f'  send_message {flag_str} <agent> "your text"'
        )


def classify_command(cmd: str) -> ActionKind:
    """Classify a bash command string into a coarse workflow phase."""
    stripped = cmd.strip()
    if not stripped:
        return ActionKind.NONE
    if _VERIFY_OR_GIT_RE.search(stripped):
        return ActionKind.VERIFY_OR_GIT
    if _FILE_EDIT_RE.search(stripped):
        return ActionKind.FILE_EDIT
    if _READ_EXPLORE_RE.search(stripped):
        return ActionKind.READ_EXPLORE
    return ActionKind.OTHER


def strip_compaction_board(content: str) -> str:
    """Remove any previously pinned thread-board block before re-summarizing."""
    marker = f"\n\n{COMPACTION_BOARD_HEADING}\n"
    idx = content.find(marker)
    return content[:idx] if idx != -1 else content


def _extract_raw_send_spans(cmd: str) -> tuple[list[tuple[int, int]], list[tuple[str, str]]]:
    """Extract matched character spans and (header, body) pairs for send_message calls."""
    found: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []

    for match in _SEND_HEREDOC_RE.finditer(cmd):
        start, end = match.span()
        occupied.append((start, end))
        found.append((start, end, match.group("header"), match.group("body")))

    for match in _SEND_QUOTED_RE.finditer(cmd):
        start, end = match.span()
        if any(not (end <= s or start >= e) for s, e in occupied):
            continue
        if match.group("dq") is not None:
            body = re.sub(r'\\(["\\])', r"\1", match.group("dq"))
        else:
            body = match.group("sq") or ""
        found.append((start, end, match.group("header"), body))

    found.sort(key=lambda item: item[0])
    spans = [(s, e) for s, e, _, _ in found]
    calls = [(h, b) for _, _, h, b in found]
    return spans, calls


def _strip_spans(cmd: str, spans: list[tuple[int, int]]) -> str:
    """Remove matched send_message spans from a compound shell command and tidy operators."""
    if not spans:
        return cmd.strip()
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(cmd[cursor:start])
        cursor = end
    parts.append(cmd[cursor:])
    cleaned = "".join(parts)
    cleaned = re.sub(r"^\s*(?:&&|\|\||;)\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:&&|\|\||;)\s*$", "", cleaned)
    cleaned = re.sub(r"&&\s*&&", "&&", cleaned)
    cleaned = re.sub(r"\|\|\s*\|\|", "||", cleaned)
    cleaned = re.sub(r";\s*;", ";", cleaned)
    return cleaned.strip()


def _extract_body_intent(body: str) -> tuple[str | None, str]:
    match = _BODY_INTENT_PREFIX_RE.match(body)
    if not match:
        return None, body
    raw = match.group("bracket") or match.group("colon") or ""
    canonical = CANONICAL_INTENTS.get(raw.lower())
    if canonical is None:
        return None, body
    rest = match.group("rest").strip()
    return canonical, (rest if rest else canonical)


def _normalize_wire_intent(wire_intent: Any, content: str) -> str | None:
    if isinstance(wire_intent, str) and wire_intent.lower() in CANONICAL_INTENTS:
        return CANONICAL_INTENTS[wire_intent.lower()]
    extracted, _ = _extract_body_intent(content)
    return extracted


def _summarize_snippet(text: str, max_chars: int = 88) -> str:
    collapsed = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _msg_id_sort_key(msg_id: str) -> tuple[int, str]:
    digits = re.sub(r"\D+", "", msg_id)
    return (int(digits) if digits else 10**9, msg_id)
