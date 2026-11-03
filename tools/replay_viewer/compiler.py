"""Data compiler for the 3-pane CooperBench multi-agent replay viewer.

Discovers benchmark runs, parses and stitches solver/summarizer trajectory
segments, matches sent and received messages with delivery buffering,
reconstructs evolving thread board state, and compiles chronological timelines.
"""

from __future__ import annotations

import csv
import json
import re
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from cooperbench.agents.mini_swe_agent_v2.agents.communication import (
    COMPACTION_BOARD_HEADING,
    classify_command,
)


def _resolve_default_repo_root() -> Path:
    """Resolve repository root supporting both normal checkouts and git worktrees."""
    checkout_root = Path(__file__).resolve().parents[2]
    if (checkout_root / "logs").exists():
        return checkout_root
    git_file = checkout_root / ".git"
    if git_file.is_file():
        try:
            line = git_file.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                gitdir_path = Path(line.split(":", 1)[1].strip())
                if len(gitdir_path.parents) >= 3 and (gitdir_path.parents[2] / "logs").exists():
                    return gitdir_path.parents[2]
        except Exception:
            pass
    return checkout_root


MAIN_REPO_ROOT = _resolve_default_repo_root()

# Regular expressions with re.VERBOSE for robust trajectory parsing.

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

_TOOL_CONFIRM_RE = re.compile(
    r"""
    Message[ \t]+sent[ \t]+to[ \t]+(?P<recipient>\w+)
    (?:[ \t]*\((?P<meta>[^)]*)\))?
    """,
    re.VERBOSE,
)

_INCOMING_MSG_RE = re.compile(
    r"""
    ^\[
    (?P<kind>Message|Reply)
    (?:[ \t]+(?P<id>m\d+|\w+))?
    [ \t]+from[ \t]+(?P<sender>\w+)
    (?:\s*\((?P<meta>[^)]*)\))?
    (?:[ \t]*—[ \t]*(?P<blocked>[^\]]*))?
    \]:?[ \t]*
    (?P<body>.*)$
    """,
    re.DOTALL | re.VERBOSE,
)

_FOOTER_OPEN_THREADS_RE = re.compile(
    r"""
    \[Open[ \t]+threads[ \t]*\((?P<count>\d+)\):
    (?P<body>.*?)
    \]
    """,
    re.DOTALL | re.VERBOSE,
)

_FOOTER_PENDING_RE = re.compile(
    r"""
    \[Pending[ \t]+colleague[ \t]+requests/proposals[ \t]*\((?P<count>\d+)\):
    (?P<body>.*?)
    \]
    """,
    re.DOTALL | re.VERBOSE,
)

_FOOTER_STEP_COUNTER_RE = re.compile(
    r"""
    \[Step[ \t]+(?P<curr>\d+)[ \t]+of[ \t]+(?P<total>\d+):
    [ \t]*(?P<left>\d+)[ \t]*left\.[^\]]*\]
    """,
    re.VERBOSE,
)

_TOUCHED_FILE_RE = re.compile(
    r"""
    (?:
        (?:cat|tee|nl|head|tail|sed|python[0-9.]*|pytest|git\s+apply|patch)[ \t]+[^\n]*?
        (?P<file1>[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*\.(?:py|go|rs|js|ts|tsx|jsx|json|md|txt|sh|toml|yaml|yml))
        |
        (?:>|>>)[ \t]*(?P<file2>[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*\.(?:py|go|rs|js|ts|tsx|jsx|json|md|txt|sh|toml|yaml|yml))
    )
    """,
    re.VERBOSE,
)

# Algebraic Data Types for disjoint event/parse outcomes.


@dataclass(frozen=True, slots=True)
class CompactionEvent:
    """Context compaction boundary where history was replaced by a summary."""

    agent_id: str
    step: int
    timestamp: float
    summary: str
    pinned_board: str | None = None
    kept_turns_count: int = 0


@dataclass(frozen=True, slots=True)
class NudgeEvent:
    """Harness nudge injected into agent context to guide coordination or submission."""

    agent_id: str
    kind: Literal["held_flush", "uncommitted_submit", "obligation_presubmit", "peer_exited"]
    step: int
    timestamp: float
    message: str


@dataclass(frozen=True, slots=True)
class MessageEvent:
    """Inter-agent message with delivery timing, threading, and intent metadata."""

    id: str
    sender: str
    recipient: str
    content: str
    intent: str | None
    reply_to: str | None
    resolve: bool
    wait: bool
    sent_step: int
    sent_at: float
    receiver_step_at_send: int
    receiver_action_at_send: str
    receiver_rc_at_send: int
    delivered_step: int | None
    delivered_at: float | None
    held_steps: int
    hold_reason: str
    flush_reason: str
    delivery_status: Literal["immediate", "held", "filtered_fyi", "undelivered_peer_exited"]


@dataclass(slots=True)
class ThreadEntry:
    """Tracked conversation thread keyed by root message ID."""

    thread_id: str
    opened_by: str
    opened_step: int
    status: Literal["open", "resolved"]
    last_sender: str
    last_message_id: str
    last_step: int
    last_intent: str | None
    root_summary: str
    last_summary: str
    history: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AgentStep:
    """Single execution step taken by an agent."""

    agent_id: str
    step_number: int
    timestamp: float
    thought: str | None
    command: str | None
    action_phase: str
    touched_files: tuple[str, ...]
    returncode: int | None
    output: str
    diff_snippet: str | None
    prompt_tokens: int
    completion_tokens: int
    cumulative_cost: float
    footers: tuple[str, ...]
    injected_user_messages: tuple[str, ...] = ()


# Public API functions.


def list_runs(
    logs_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Returns a list of all cooperative benchmark runs with config badges and metrics."""
    ld, rd = _resolve_dirs(logs_dir, results_dir)
    discovered: dict[str, dict[str, Any]] = {}

    if ld.exists():
        for run_path in sorted(ld.iterdir()):
            if not run_path.is_dir():
                continue
            run_name = run_path.name
            summary = _load_json(run_path / "summary.json") or {}
            launch = _load_json(run_path / "launch.json") or {}
            setting = launch.get("setting") or summary.get("setting") or ("coop" if "coop" in run_name else "solo")
            if setting not in ("coop", "team") and "coop" not in run_name and "team" not in run_name:
                continue

            config_flags = _extract_config_flags(launch, run_path)
            headline = {
                "both_passed_count": summary.get("both_passed_count", 0),
                "total_pairs_count": summary.get("total_pairs_count", 0),
                "pass_rate_both": summary.get("pass_rate_both", 0.0),
                "total_messages_sent": summary.get("total_messages_sent", 0),
                "total_cost_usd": summary.get("total_cost_usd", 0.0),
            }

            discovered[run_name] = {
                "run_name": run_name,
                "setting": setting,
                "model": launch.get("model") or summary.get("model", ""),
                "subset": launch.get("subset") or ("flash_10" if "flash_10" in run_name else "core"),
                "git_enabled": bool(launch.get("git")),
                "headline": headline,
                "config_flags": config_flags,
                "has_results_dir": False,
            }

    if rd.exists():
        for res_path in sorted(rd.iterdir()):
            if not res_path.is_dir():
                continue
            run_name = res_path.name
            run_json = _load_json(res_path / "run.json") or {}
            if not run_json:
                continue
            setting = run_json.get("setting") or ("coop" if "coop" in run_name else "solo")
            if setting not in ("coop", "team") and "coop" not in run_name and "team" not in run_name:
                continue

            headline = run_json.get("headline") or {}
            config_flags = _extract_config_flags(run_json, ld / run_name if ld.exists() else None)
            discovered[run_name] = {
                "run_name": run_name,
                "setting": setting,
                "model": run_json.get("model", ""),
                "subset": run_json.get("subset", ""),
                "git_enabled": bool(run_json.get("git_enabled")),
                "headline": headline,
                "config_flags": config_flags,
                "has_results_dir": True,
            }

    return sorted(discovered.values(), key=lambda r: r["run_name"])


def list_pairs_index(
    logs_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Returns a cross-run pair index mapping each task pair to every run that tested it."""
    ld, rd = _resolve_dirs(logs_dir, results_dir)
    runs = list_runs(ld, rd)
    pair_map: dict[tuple[str, int, int, int], dict[str, Any]] = {}

    for run in runs:
        run_name = run["run_name"]
        pairs_data = _load_run_pairs(run_name, ld, rd)
        for p in pairs_data:
            key = (p["repo"], int(p["task_id"]), int(p["feature_a"]), int(p["feature_b"]))
            if key not in pair_map:
                pair_map[key] = {
                    "repo": p["repo"],
                    "task_id": int(p["task_id"]),
                    "feature_a": int(p["feature_a"]),
                    "feature_b": int(p["feature_b"]),
                    "pair_id": f"{p['repo']}:{p['task_id']}:f{p['feature_a']}_f{p['feature_b']}",
                    "runs": {},
                }
            pair_map[key]["runs"][run_name] = {
                "run_name": run_name,
                "both_passed": p["both_passed"],
                "merge_status": p["merge_status"],
                "messages_sent": p["messages_sent"],
                "steps_total": p["steps_total"],
                "cost_usd": p["cost_usd"],
                "config_flags": run["config_flags"],
            }

    return sorted(
        pair_map.values(),
        key=lambda item: (item["repo"], item["task_id"], item["feature_a"], item["feature_b"]),
    )


def compile_pair_replay(
    run_name: str,
    repo: str,
    task_id: int | str,
    features: list[int] | tuple[int, int] | str,
    *,
    logs_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
    dataset_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Compiles complete replay timeline, messages, diffs, and thread boards for one pair."""
    ld, rd = _resolve_dirs(logs_dir, results_dir)
    dd = Path(dataset_dir) if dataset_dir else MAIN_REPO_ROOT / "dataset"

    fa, fb = _parse_features_arg(features)
    pair_dir = _find_pair_log_dir(ld / run_name, repo, int(task_id), fa, fb)
    if not pair_dir.exists():
        raise FileNotFoundError(f"Pair log directory not found for {run_name} {repo} {task_id} f{fa}_f{fb}")

    result_data = _load_json(pair_dir / "result.json") or {}
    eval_data = _load_json(pair_dir / "eval.json") or {}
    run_info = next((r for r in list_runs(ld, rd) if r["run_name"] == run_name), None)
    config_flags = run_info["config_flags"] if run_info else _extract_config_flags({}, ld / run_name)

    t1_path = _resolve_traj_file(pair_dir, "agent1", fa)
    t2_path = _resolve_traj_file(pair_dir, "agent2", fb)

    raw1 = _load_json(t1_path) or {}
    raw2 = _load_json(t2_path) or {}

    turns1, compactions1 = _stitch_trajectory(raw1, "agent1")
    turns2, compactions2 = _stitch_trajectory(raw2, "agent2")

    steps1, nudges1 = _extract_agent_steps(turns1, "agent1")
    steps2, nudges2 = _extract_agent_steps(turns2, "agent2")

    messages = _match_and_reconstruct_messages(
        steps1=steps1,
        steps2=steps2,
        config_flags=config_flags,
    )

    timeline = _build_chronological_timeline(
        steps1=steps1,
        steps2=steps2,
        messages=messages,
        compactions1=compactions1,
        compactions2=compactions2,
        nudges1=nudges1,
        nudges2=nudges2,
    )

    spec_a = _load_feature_spec(dd, repo, int(task_id), fa)
    spec_b = _load_feature_spec(dd, repo, int(task_id), fb)

    patch_a = _load_patch(pair_dir, "agent1", fa)
    patch_b = _load_patch(pair_dir, "agent2", fb)

    return {
        "run_name": run_name,
        "repo": repo,
        "task_id": int(task_id),
        "features": [fa, fb],
        "config_flags": config_flags,
        "result": result_data,
        "eval": eval_data,
        "specs": {"feature_a": spec_a, "feature_b": spec_b},
        "patches": {"agent1": patch_a, "agent2": patch_b},
        "messages": [asdict(m) for m in messages],
        "compactions": {
            "agent1": [asdict(c) for c in compactions1],
            "agent2": [asdict(c) for c in compactions2],
        },
        "nudges": {
            "agent1": [asdict(n) for n in nudges1],
            "agent2": [asdict(n) for n in nudges2],
        },
        "steps": {
            "agent1": [asdict(s) for s in steps1],
            "agent2": [asdict(s) for s in steps2],
        },
        "timeline": timeline,
    }


# Private helper functions.


def _resolve_dirs(logs_dir: Path | str | None, results_dir: Path | str | None) -> tuple[Path, Path]:
    ld = Path(logs_dir) if logs_dir else MAIN_REPO_ROOT / "logs"
    rd = Path(results_dir) if results_dir else MAIN_REPO_ROOT / "results"
    return ld, rd


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _parse_features_arg(features: list[int] | tuple[int, int] | str) -> tuple[int, int]:
    if isinstance(features, (list, tuple)) and len(features) >= 2:
        return int(features[0]), int(features[1])
    if isinstance(features, str):
        match = re.match(r"(?:f)?(\d+)[_-](?:f)?(\d+)", features)
        if match:
            return int(match.group(1)), int(match.group(2))
    raise ValueError(f"Cannot parse features from: {features}")


def _extract_config_flags(source_dict: dict[str, Any], run_log_dir: Path | None) -> dict[str, Any]:
    flags = {
        "delivery_timing": False,
        "delivery_max_hold_steps": 4,
        "delivery_boundary_mode": "natural",
        "message_threading": False,
        "thread_pin_mode": "every_turn",
        "message_intents": False,
        "intent_filter_fyi": False,
        "intent_presubmit_check": False,
        "step_counter": False,
    }

    raw_conf = source_dict.get("agent_config") or source_dict.get("agent") or {}
    if isinstance(raw_conf, str):
        for line in raw_conf.splitlines():
            line_s = line.strip()
            for k in list(flags.keys()):
                if line_s.startswith(f"{k}:"):
                    val_str = line_s.split(":", 1)[1].strip().lower()
                    if val_str in ("true", "yes"):
                        flags[k] = True
                    elif val_str in ("false", "no"):
                        flags[k] = False
                    elif val_str.isdigit():
                        flags[k] = int(val_str)
                    else:
                        flags[k] = val_str
    elif isinstance(raw_conf, dict):
        for k in flags:
            if k in raw_conf:
                flags[k] = raw_conf[k]

    cmd = str(source_dict.get("command") or "")
    if "delivery-timing" in cmd or (run_log_dir and "delivery-timing" in run_log_dir.name):
        flags["delivery_timing"] = True
    if "threading" in cmd or (run_log_dir and "threading" in run_log_dir.name):
        flags["message_threading"] = True
    if "intents" in cmd or (run_log_dir and "intents" in run_log_dir.name):
        flags["message_intents"] = True
    if "stepcounter" in cmd or (run_log_dir and "stepcounter" in run_log_dir.name):
        flags["step_counter"] = True
    if "comm-combined" in cmd or (run_log_dir and "comm-combined" in run_log_dir.name):
        flags["delivery_timing"] = True
        flags["message_threading"] = True
        flags["message_intents"] = True
        flags["step_counter"] = True

    return flags


def _load_run_pairs(run_name: str, logs_dir: Path, results_dir: Path) -> list[dict[str, Any]]:
    pairs_csv = results_dir / run_name / "pairs.csv"
    if pairs_csv.exists():
        pairs: list[dict[str, Any]] = []
        with open(pairs_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pairs.append(
                    {
                        "repo": row["repo"],
                        "task_id": int(row["task_id"]),
                        "feature_a": int(row["feature_a"]),
                        "feature_b": int(row["feature_b"]),
                        "both_passed": row["both_passed"].lower() == "true",
                        "merge_status": row.get("merge_status", "unknown"),
                        "messages_sent": int(row.get("messages_sent") or 0),
                        "steps_total": int(row.get("steps_total") or 0),
                        "cost_usd": float(row.get("cost_usd") or 0.0),
                    }
                )
        return pairs

    run_log_dir = logs_dir / run_name
    found_pairs: list[dict[str, Any]] = []
    if not run_log_dir.exists():
        return found_pairs

    for res_path in run_log_dir.glob("coop/*/*/*/result.json"):
        res = _load_json(res_path) or {}
        eval_p = res_path.parent / "eval.json"
        ev = _load_json(eval_p) or {}
        features = res.get("features") or [0, 0]
        both_passed = bool(ev.get("both_passed"))
        merge_info = ev.get("merge") or {}
        merge_status = merge_info.get("status") or ("clean" if both_passed else "unknown")

        found_pairs.append(
            {
                "repo": res.get("repo", ""),
                "task_id": int(res.get("task_id", 0)),
                "feature_a": int(features[0]),
                "feature_b": int(features[1]),
                "both_passed": both_passed,
                "merge_status": merge_status,
                "messages_sent": int(res.get("messages_sent", 0)),
                "steps_total": int(res.get("total_steps", 0)),
                "cost_usd": float(res.get("total_cost", 0.0)),
            }
        )
    return found_pairs


def _find_pair_log_dir(run_log_dir: Path, repo: str, task_id: int, fa: int, fb: int) -> Path:
    candidates = [
        run_log_dir / "coop" / repo / str(task_id) / f"f{fa}_f{fb}",
        run_log_dir / "coop" / repo / str(task_id) / f"f{fb}_f{fa}",
        run_log_dir / "team" / repo / str(task_id) / f"f{fa}_f{fb}",
        run_log_dir / "team" / repo / str(task_id) / f"f{fb}_f{fa}",
        run_log_dir / repo / str(task_id) / f"f{fa}_f{fb}",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _resolve_traj_file(pair_dir: Path, agent_id: str, feature_id: int) -> Path:
    candidates = [
        pair_dir / f"{agent_id}_full_traj.json",
        pair_dir / f"agent{feature_id}_full_traj.json",
        pair_dir / f"{agent_id}_traj.json",
        pair_dir / f"agent{feature_id}_traj.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[2]


def _stitch_trajectory(
    raw_data: dict[str, Any],
    agent_id: str,
) -> tuple[list[dict[str, Any]], list[CompactionEvent]]:
    """Deduplicates solver turns across segments and extracts structured compaction events."""
    segments = raw_data.get("segments") or []
    if not segments:
        all_msgs = raw_data.get("messages") or []
        compactions: list[CompactionEvent] = []
        turns: list[dict[str, Any]] = []
        for m in all_msgs:
            extra = m.get("extra") or {}
            if extra.get("summary"):
                content = str(m.get("content") or "")
                summary, board = _split_compaction_content(content)
                compactions.append(
                    CompactionEvent(
                        agent_id=agent_id,
                        step=len(turns),
                        timestamp=float(extra.get("timestamp") or 0.0),
                        summary=summary,
                        pinned_board=board,
                    )
                )
            else:
                turns.append(m)
        return turns, compactions

    seen_ids: set[str] = set()
    turns = []
    compactions = []
    current_step = 0

    for seg in segments:
        kind = seg.get("kind")
        if kind == "summarizer":
            last_m = seg["messages"][-1] if seg.get("messages") else {}
            content = str(last_m.get("content") or "")
            summary, board = _split_compaction_content(content)
            ts = float((last_m.get("extra") or {}).get("timestamp") or 0.0)
            compactions.append(
                CompactionEvent(
                    agent_id=agent_id,
                    step=current_step,
                    timestamp=ts,
                    summary=summary,
                    pinned_board=board,
                    kept_turns_count=2,
                )
            )
            continue

        msgs = seg.get("messages", [])
        # Find the index after the last already-seen assistant turn (and its paired tool output)
        # so kept recent turns (and their user/tool messages) are not duplicated across segments.
        start_idx = 0
        for idx, m in enumerate(msgs):
            extra = m.get("extra") or {}
            if extra.get("summary"):
                if compactions and compactions[-1].pinned_board is None:
                    _, board = _split_compaction_content(str(m.get("content") or ""))
                    if board:
                        old_c = compactions.pop()
                        compactions.append(
                            CompactionEvent(
                                agent_id=old_c.agent_id,
                                step=old_c.step,
                                timestamp=old_c.timestamp,
                                summary=old_c.summary,
                                pinned_board=board,
                                kept_turns_count=old_c.kept_turns_count,
                            )
                        )
                start_idx = max(start_idx, idx + 1)
                continue
            if m.get("role") == "assistant":
                resp = extra.get("response") or {}
                rid = resp.get("id") or str(extra.get("timestamp") or "")
                if rid and rid in seen_ids:
                    next_idx = idx + 2 if (idx + 1 < len(msgs) and msgs[idx + 1].get("role") == "tool") else idx + 1
                    start_idx = max(start_idx, next_idx)

        for idx in range(start_idx, len(msgs)):
            m = msgs[idx]
            role = m.get("role")
            extra = m.get("extra") or {}
            if role == "system" or extra.get("summary"):
                continue
            if role == "user" and idx == 1 and turns:
                # Skip repeated initial task prompt at the start of post-compaction segments.
                continue
            if role == "assistant":
                resp = extra.get("response") or {}
                rid = resp.get("id") or str(extra.get("timestamp") or "")
                if rid:
                    seen_ids.add(rid)
                current_step += 1
            turns.append(m)

    return turns, compactions


def _split_compaction_content(content: str) -> tuple[str, str | None]:
    idx = content.find(COMPACTION_BOARD_HEADING)
    if idx != -1:
        summary = content[:idx].strip()
        board = content[idx:].strip()
        return summary, board
    return content.strip(), None


def _extract_agent_steps(
    messages: list[dict[str, Any]],
    agent_id: str,
) -> tuple[list[AgentStep], list[NudgeEvent]]:
    """Extracts step-by-step actions, returncodes, diffs, footers, and harness nudges."""
    steps: list[AgentStep] = []
    nudges: list[NudgeEvent] = []
    step_num = 0
    pending_user_notes: list[str] = []

    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        role = msg.get("role")
        content = str(msg.get("content") or "")

        if role == "user":
            nudge = _parse_nudge(content, agent_id, step_num, float((msg.get("extra") or {}).get("timestamp") or 0.0))
            if nudge:
                nudges.append(nudge)
            else:
                pending_user_notes.append(content)
            idx += 1
            continue

        if role == "assistant":
            step_num += 1
            extra = msg.get("extra") or {}
            resp = extra.get("response") or {}
            usage = resp.get("usage") or {}
            thought = resp.get("thought") or (content if not extra.get("actions") else None)
            actions = extra.get("actions") or []
            cmd = actions[0].get("command") if actions and isinstance(actions[0], dict) else None
            ts = float(extra.get("timestamp") or 0.0)
            cost = float(extra.get("cost") or 0.0)

            # Match subsequent tool message if present.
            tool_msg = None
            if idx + 1 < len(messages) and messages[idx + 1].get("role") == "tool":
                tool_msg = messages[idx + 1]
                idx += 1

            tool_extra = (tool_msg.get("extra") or {}) if tool_msg else {}
            rc = tool_extra.get("returncode")
            raw_out = tool_extra.get("raw_output")
            tool_content = str(tool_msg.get("content") or "") if tool_msg else ""
            out = raw_out if raw_out is not None else tool_content

            action_phase = _classify_action(cmd)
            touched = _extract_touched_files(cmd or "")
            diff_snip = _extract_diff_snippet(cmd or "", out)
            footers = _extract_footers(tool_content)

            steps.append(
                AgentStep(
                    agent_id=agent_id,
                    step_number=step_num,
                    timestamp=ts,
                    thought=thought,
                    command=cmd,
                    action_phase=action_phase,
                    touched_files=tuple(touched),
                    returncode=rc,
                    output=out,
                    diff_snippet=diff_snip,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    cumulative_cost=cost,
                    footers=tuple(footers),
                    injected_user_messages=tuple(pending_user_notes),
                )
            )
            pending_user_notes.clear()

        idx += 1

    return steps, nudges


def _parse_nudge(content: str, agent_id: str, step: int, ts: float) -> NudgeEvent | None:
    clow = content.lower()
    if "buffered message(s) from your colleague" in clow or "flushed before exit" in clow:
        return NudgeEvent(agent_id=agent_id, kind="held_flush", step=step, timestamp=ts, message=content)
    if "uncommitted changes" in clow or "commits that are not pushed" in clow:
        return NudgeEvent(agent_id=agent_id, kind="uncommitted_submit", step=step, timestamp=ts, message=content)
    if "unanswered coordination items" in clow or "unanswered incoming requests" in clow:
        return NudgeEvent(agent_id=agent_id, kind="obligation_presubmit", step=step, timestamp=ts, message=content)
    if "has completed their work and exited" in clow:
        return NudgeEvent(agent_id=agent_id, kind="peer_exited", step=step, timestamp=ts, message=content)
    return None


def _classify_action(cmd: str | None) -> str:
    if not cmd or not cmd.strip():
        return "none"
    if _SEND_WORD_RE.search(cmd):
        return "message"
    return classify_command(cmd).value


def _extract_touched_files(cmd: str) -> list[str]:
    files: list[str] = []
    for match in _TOUCHED_FILE_RE.finditer(cmd):
        f = match.group("file1") or match.group("file2")
        if f and f not in files:
            files.append(f)
    return files


def _extract_diff_snippet(cmd: str, output: str) -> str | None:
    if "diff" in cmd or output.startswith("diff --git") or "@@ -" in output:
        diff_lines = [line for line in output.splitlines() if line.startswith(("+", "-", "@@", "diff --git", "index "))]
        if diff_lines:
            return "\n".join(diff_lines[:150])
    return None


def _extract_footers(tool_content: str) -> list[str]:
    footers: list[str] = []
    for m in _FOOTER_OPEN_THREADS_RE.finditer(tool_content):
        footers.append(m.group(0).strip())
    for m in _FOOTER_PENDING_RE.finditer(tool_content):
        footers.append(m.group(0).strip())
    for m in _FOOTER_STEP_COUNTER_RE.finditer(tool_content):
        footers.append(m.group(0).strip())
    return footers


def _match_and_reconstruct_messages(
    steps1: list[AgentStep],
    steps2: list[AgentStep],
    config_flags: dict[str, Any],
) -> list[MessageEvent]:
    """Matches outgoing send_message calls to recipient delivery steps with buffer tracking."""
    raw_sends: list[dict[str, Any]] = []

    for s in steps1:
        if s.command and _SEND_WORD_RE.search(s.command):
            calls = _parse_send_calls(s.command, s.output, s.agent_id, s.step_number, s.timestamp)
            raw_sends.extend(calls)

    for s in steps2:
        if s.command and _SEND_WORD_RE.search(s.command):
            calls = _parse_send_calls(s.command, s.output, s.agent_id, s.step_number, s.timestamp)
            raw_sends.extend(calls)

    raw_sends.sort(key=lambda m: m["sent_at"])

    # Map recipient steps.
    receiver_steps_map = {"agent1": steps1, "agent2": steps2}

    # Assign sequential message IDs if missing.
    matched: list[MessageEvent] = []
    for idx, send in enumerate(raw_sends, start=1):
        mid = send["id"] or f"m{idx}"
        recipient = send["recipient"]
        rsteps = receiver_steps_map.get(recipient, [])

        # Find receiver step at send timestamp.
        r_step_at_send = 0
        r_action_at_send = "none"
        r_rc_at_send = 0
        for rs in rsteps:
            if rs.timestamp <= send["sent_at"]:
                r_step_at_send = rs.step_number
                r_action_at_send = rs.action_phase
                r_rc_at_send = rs.returncode if rs.returncode is not None else 0
            else:
                break

        # Discover actual delivery step by scanning recipient trajectory.
        deliv_step, deliv_at, deliv_status = _find_delivery_step(
            msg_id=mid,
            sender=send["sender"],
            content=send["content"],
            sent_at=send["sent_at"],
            rsteps=rsteps,
            config_flags=config_flags,
            intent=send["intent"],
            wait=send["wait"],
        )

        held_steps = max((deliv_step - r_step_at_send) if deliv_step is not None else 0, 0)
        hold_reason, flush_reason = _determine_hold_and_flush_reasons(
            held_steps=held_steps,
            r_action_at_send=r_action_at_send,
            r_rc_at_send=r_rc_at_send,
            deliv_step=deliv_step,
            rsteps=rsteps,
            max_hold=config_flags.get("delivery_max_hold_steps", 4),
        )

        matched.append(
            MessageEvent(
                id=mid,
                sender=send["sender"],
                recipient=recipient,
                content=send["content"],
                intent=send["intent"],
                reply_to=send["reply_to"],
                resolve=send["resolve"],
                wait=send["wait"],
                sent_step=send["sent_step"],
                sent_at=send["sent_at"],
                receiver_step_at_send=r_step_at_send,
                receiver_action_at_send=r_action_at_send,
                receiver_rc_at_send=r_rc_at_send,
                delivered_step=deliv_step,
                delivered_at=deliv_at,
                held_steps=held_steps,
                hold_reason=hold_reason,
                flush_reason=flush_reason,
                delivery_status=deliv_status,
            )
        )

    return matched


def _parse_send_calls(
    cmd: str,
    output: str,
    sender: str,
    step_num: int,
    ts: float,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    confirm_meta: dict[str, str] = {}
    for line in output.splitlines():
        m = _TOOL_CONFIRM_RE.search(line)
        if m and m.group("meta"):
            for part in m.group("meta").split(","):
                part_s = part.strip()
                if ":" in part_s:
                    k, v = part_s.split(":", 1)
                    confirm_meta[k.strip().lower()] = v.strip()

    # Extract bodies from heredocs or quoted strings.
    bodies: list[tuple[str, str]] = []
    for match in _SEND_HEREDOC_RE.finditer(cmd):
        bodies.append((match.group("header"), match.group("body")))
    if not bodies:
        for match in _SEND_QUOTED_RE.finditer(cmd):
            b = match.group("dq") if match.group("dq") is not None else match.group("sq") or ""
            bodies.append((match.group("header"), b))

    if not bodies:
        # Fallback regex
        bodies.append(("", ""))

    for header, body in bodies:
        wait = "--wait" in header or "--wait" in cmd
        resolve = "--resolve" in header or "--resolve" in cmd or confirm_meta.get("thread", "").endswith("resolved")
        reply_to = None
        m_rt = re.search(r"--reply-to(?:=|\s+)(\w+)", header or cmd)
        if m_rt:
            reply_to = m_rt.group(1).lstrip("#")

        intent = confirm_meta.get("intent")
        if not intent:
            m_it = re.search(r"--intent(?:=|\s+)(\w+)", header or cmd)
            if m_it:
                intent = m_it.group(1).capitalize()

        mid = confirm_meta.get("id")

        recipient = "agent2" if sender == "agent1" else "agent1"
        try:
            tokens = shlex.split(header)
            for t in tokens:
                if t in ("agent1", "agent2"):
                    recipient = t
        except Exception:
            pass

        calls.append(
            {
                "id": mid,
                "sender": sender,
                "recipient": recipient,
                "content": body.strip(),
                "intent": intent,
                "reply_to": reply_to,
                "resolve": resolve,
                "wait": wait,
                "sent_step": step_num,
                "sent_at": ts,
            }
        )

    return calls


def _find_delivery_step(
    msg_id: str,
    sender: str,
    content: str,
    sent_at: float,
    rsteps: list[AgentStep],
    config_flags: dict[str, Any],
    intent: str | None,
    wait: bool,
) -> tuple[int | None, float | None, Literal["immediate", "held", "filtered_fyi", "undelivered_peer_exited"]]:
    """Locates the exact step index where recipient received this message."""
    if config_flags.get("intent_filter_fyi") and intent == "FYI" and not wait:
        return None, None, "filtered_fyi"

    # In chronological order, search for the first recipient step after sent_at
    # that satisfies natural boundary or max hold.
    delivery_timing = config_flags.get("delivery_timing", False)
    urgent = wait or (config_flags.get("message_intents", False) and intent in ("Proposal", "Request"))

    subsequent_steps = [s for s in rsteps if s.timestamp >= sent_at]
    if not subsequent_steps:
        return None, None, "undelivered_peer_exited"

    # First check ground-truth injected user messages in the recipient trajectory.
    norm_snippet = " ".join(content.split())[:48]
    for idx, s in enumerate(subsequent_steps):
        for note in s.injected_user_messages:
            m_inc = _INCOMING_MSG_RE.match(note.strip())
            if not m_inc or m_inc.group("sender") != sender:
                continue
            inc_id = m_inc.group("id")
            inc_body = " ".join((m_inc.group("body") or "").split())
            if (inc_id and inc_id == msg_id) or (norm_snippet and norm_snippet in inc_body):
                status: Literal["immediate", "held"] = "held" if idx >= 1 else "immediate"
                return s.step_number, s.timestamp, status

    if not delivery_timing or urgent:
        target = subsequent_steps[0]
        return target.step_number, target.timestamp, "immediate"

    max_hold = config_flags.get("delivery_max_hold_steps", 4)
    boundary_mode = config_flags.get("delivery_boundary_mode", "natural")

    held_count = 0
    for idx, s in enumerate(subsequent_steps):
        held_count += 1
        is_last = idx == len(subsequent_steps) - 1
        hit_ceiling = held_count >= max_hold

        if hit_ceiling or is_last:
            status = "held" if held_count > 1 else "immediate"
            return s.step_number, s.timestamp, status

        if boundary_mode == "natural":
            clean_cmd = s.returncode == 0
            boundary_action = s.action_phase in ("verify_or_git", "message")
            if clean_cmd and boundary_action:
                status = "held" if held_count > 1 else "immediate"
                return s.step_number, s.timestamp, status

    fallback = subsequent_steps[0]
    return fallback.step_number, fallback.timestamp, "immediate"


def _determine_hold_and_flush_reasons(
    held_steps: int,
    r_action_at_send: str,
    r_rc_at_send: int,
    deliv_step: int | None,
    rsteps: list[AgentStep],
    max_hold: int,
) -> tuple[str, str]:
    if held_steps <= 0:
        return "delivered immediately", "immediate delivery"

    if r_rc_at_send != 0:
        hold_reason = "recipient fixing failed command (returncode != 0)"
    elif r_action_at_send == "file_edit":
        hold_reason = "recipient mid-edit (buffering until verify/git boundary)"
    elif r_action_at_send == "read_explore":
        hold_reason = "recipient exploring (buffering until edit or test boundary)"
    else:
        hold_reason = "buffering until opportune workflow boundary"

    if held_steps >= max_hold:
        flush_reason = f"reached max hold limit ({max_hold} steps)"
    else:
        # Check delivery step action
        deliv_step_obj = next((s for s in rsteps if s.step_number == deliv_step), None)
        if deliv_step_obj and deliv_step_obj.action_phase == "verify_or_git":
            flush_reason = (
                f"clean verification boundary ({deliv_step_obj.command[:30] if deliv_step_obj.command else 'test'})"
            )
        elif deliv_step_obj and deliv_step_obj.action_phase == "message":
            flush_reason = "recipient sent message (turn boundary)"
        else:
            flush_reason = "natural turn boundary"

    return hold_reason, flush_reason


def _build_chronological_timeline(
    steps1: list[AgentStep],
    steps2: list[AgentStep],
    messages: list[MessageEvent],
    compactions1: list[CompactionEvent],
    compactions2: list[CompactionEvent],
    nudges1: list[NudgeEvent],
    nudges2: list[NudgeEvent],
) -> list[dict[str, Any]]:
    """Builds discrete timeline frames for frontend scrubbing 0..T-1."""
    events: list[dict[str, Any]] = []

    for s in steps1:
        events.append({"ts": s.timestamp, "kind": "step", "agent": "agent1", "step_num": s.step_number, "data": s})
    for s in steps2:
        events.append({"ts": s.timestamp, "kind": "step", "agent": "agent2", "step_num": s.step_number, "data": s})

    for m in messages:
        events.append({"ts": m.sent_at, "kind": "msg_sent", "agent": m.sender, "msg_id": m.id, "data": m})
        if m.delivered_at is not None:
            events.append(
                {"ts": m.delivered_at, "kind": "msg_delivered", "agent": m.recipient, "msg_id": m.id, "data": m}
            )

    for c in compactions1:
        events.append({"ts": c.timestamp, "kind": "compaction", "agent": "agent1", "data": c})
    for c in compactions2:
        events.append({"ts": c.timestamp, "kind": "compaction", "agent": "agent2", "data": c})

    for n in nudges1:
        events.append({"ts": n.timestamp, "kind": "nudge", "agent": "agent1", "data": n})
    for n in nudges2:
        events.append({"ts": n.timestamp, "kind": "nudge", "agent": "agent2", "data": n})

    events.sort(key=lambda e: (e["ts"], 0 if e["kind"] == "step" else 1))

    frames: list[dict[str, Any]] = []
    threads: dict[str, ThreadEntry] = {}

    for idx, ev in enumerate(events):
        curr_ts = ev["ts"]

        # Current state for Agent 1.
        a1_steps_so_far = [s for s in steps1 if s.timestamp <= curr_ts]
        a1_curr_step = a1_steps_so_far[-1] if a1_steps_so_far else None
        a1_compactions = sum(1 for c in compactions1 if c.timestamp <= curr_ts)
        a1_held_inbox = [
            asdict(m)
            for m in messages
            if m.recipient == "agent1"
            and m.sent_at <= curr_ts
            and (m.delivered_at is None or m.delivered_at > curr_ts)
            and m.delivery_status != "filtered_fyi"
        ]

        # Current state for Agent 2.
        a2_steps_so_far = [s for s in steps2 if s.timestamp <= curr_ts]
        a2_curr_step = a2_steps_so_far[-1] if a2_steps_so_far else None
        a2_compactions = sum(1 for c in compactions2 if c.timestamp <= curr_ts)
        a2_held_inbox = [
            asdict(m)
            for m in messages
            if m.recipient == "agent2"
            and m.sent_at <= curr_ts
            and (m.delivered_at is None or m.delivered_at > curr_ts)
            and m.delivery_status != "filtered_fyi"
        ]

        # Evolving thread board up to curr_ts.
        sent_so_far = [m for m in messages if m.sent_at <= curr_ts]
        for m in sent_so_far:
            _apply_message_to_threads(threads, m)

        # Center pane visible messages with live status at curr_ts.
        center_msgs = []
        for m in sent_so_far:
            m_dict = asdict(m)
            if m.delivery_status == "filtered_fyi":
                m_dict["live_status"] = "filtered_fyi"
                m_dict["live_badge"] = "🔇 Filtered FYI"
            elif m.delivered_at is not None and curr_ts >= m.delivered_at:
                m_dict["live_status"] = "delivered"
                m_dict["live_badge"] = f"✓ Delivered @ Step {m.delivered_step}"
            else:
                m_dict["live_status"] = "held"
                m_dict["live_badge"] = f"⏸ Held in {m.recipient}'s buffer ({m.held_steps} steps)"
            center_msgs.append(m_dict)

        frames.append(
            {
                "frame_index": idx,
                "timestamp": curr_ts,
                "kind": ev["kind"],
                "agent": ev.get("agent"),
                "delivery_status": ev["data"].delivery_status if ev["kind"] == "msg_delivered" else None,
                "description": _format_event_description(ev),
                "agent1": {
                    "step": a1_curr_step.step_number if a1_curr_step else 0,
                    "action_phase": a1_curr_step.action_phase if a1_curr_step else "none",
                    "command": a1_curr_step.command if a1_curr_step else None,
                    "thought": a1_curr_step.thought if a1_curr_step else None,
                    "output": a1_curr_step.output if a1_curr_step else None,
                    "returncode": a1_curr_step.returncode if a1_curr_step else None,
                    "touched_files": a1_curr_step.touched_files if a1_curr_step else [],
                    "diff_snippet": a1_curr_step.diff_snippet if a1_curr_step else None,
                    "tokens": (a1_curr_step.prompt_tokens + a1_curr_step.completion_tokens) if a1_curr_step else 0,
                    "cost": a1_curr_step.cumulative_cost if a1_curr_step else 0.0,
                    "compactions": a1_compactions,
                    "held_inbox": a1_held_inbox,
                },
                "agent2": {
                    "step": a2_curr_step.step_number if a2_curr_step else 0,
                    "action_phase": a2_curr_step.action_phase if a2_curr_step else "none",
                    "command": a2_curr_step.command if a2_curr_step else None,
                    "thought": a2_curr_step.thought if a2_curr_step else None,
                    "output": a2_curr_step.output if a2_curr_step else None,
                    "returncode": a2_curr_step.returncode if a2_curr_step else None,
                    "touched_files": a2_curr_step.touched_files if a2_curr_step else [],
                    "diff_snippet": a2_curr_step.diff_snippet if a2_curr_step else None,
                    "tokens": (a2_curr_step.prompt_tokens + a2_curr_step.completion_tokens) if a2_curr_step else 0,
                    "cost": a2_curr_step.cumulative_cost if a2_curr_step else 0.0,
                    "compactions": a2_compactions,
                    "held_inbox": a2_held_inbox,
                },
                "center": {
                    "messages": center_msgs,
                    "threads": [asdict(t) for t in threads.values()],
                    "active_nudge": asdict(ev["data"]) if ev["kind"] == "nudge" else None,
                    "active_compaction": asdict(ev["data"]) if ev["kind"] == "compaction" else None,
                },
            }
        )

    return frames


def _apply_message_to_threads(threads: dict[str, ThreadEntry], m: MessageEvent) -> None:
    snip = m.content[:60].replace("\n", " ") + ("..." if len(m.content) > 60 else "")
    if m.reply_to and m.reply_to in threads:
        entry = threads[m.reply_to]
        entry.last_sender = m.sender
        entry.last_message_id = m.id
        entry.last_step = m.sent_step
        entry.last_intent = m.intent
        entry.last_summary = snip
        if m.resolve:
            entry.status = "resolved"
        entry.history.append(f"{m.id} ({m.sender}): {snip}")
    elif m.id not in threads:
        threads[m.id] = ThreadEntry(
            thread_id=m.id,
            opened_by=m.sender,
            opened_step=m.sent_step,
            status="resolved" if m.resolve else "open",
            last_sender=m.sender,
            last_message_id=m.id,
            last_step=m.sent_step,
            last_intent=m.intent,
            root_summary=snip,
            last_summary=snip,
            history=[f"{m.id} ({m.sender}): {snip}"],
        )


def _format_event_description(ev: dict[str, Any]) -> str:
    kind = ev["kind"]
    agent = ev.get("agent", "")
    data = ev.get("data")
    if kind == "step":
        cmd_s = data.command[:40] if data.command else "think"
        return f"{agent} Step {data.step_number}: {cmd_s}"
    if kind == "msg_sent":
        return f"{agent} sent {data.id} to {data.recipient} ({data.intent or 'msg'})"
    if kind == "msg_delivered":
        return f"{data.id} delivered to {agent} ({data.delivery_status})"
    if kind == "compaction":
        return f"{agent} context compaction ({data.summary[:30]}...)"
    if kind == "nudge":
        return f"{agent} harness nudge: {data.kind}"
    return f"{agent} {kind}"


def _load_feature_spec(dataset_dir: Path, repo: str, task_id: int, feature_id: int) -> str:
    candidates = [
        dataset_dir / repo / f"task{task_id}" / f"feature{feature_id}" / "feature.md",
        dataset_dir / repo / str(task_id) / f"feature{feature_id}" / "feature.md",
        dataset_dir / repo / f"task{task_id}" / f"feature_{feature_id}.md",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    return f"# Feature {feature_id}\n(Specification file not found in {dataset_dir})"


def _load_patch(pair_dir: Path, agent_id: str, feature_id: int) -> str:
    candidates = [
        pair_dir / f"{agent_id}.patch",
        pair_dir / f"agent{feature_id}.patch",
        pair_dir / f"agent{agent_id}.patch",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    return ""
