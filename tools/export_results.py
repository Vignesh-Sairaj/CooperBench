#!/usr/bin/env python3
"""Export one CooperBench run from logs/ into a small, tracked results/ folder.

Usage:
    uv run --frozen python tools/export_results.py <run_name> [--logs-dir logs] [--results-dir results]

Reads logs/<run_name>/ (config.json, summary.json, launch.json if present,
console.log if present, and each pair's result.json / eval.json / trajectories)
and writes:

    results/<run_name>/run.json     how the run was launched, headline numbers, and API load
    results/<run_name>/pairs.csv    one row per task pair
    results/<run_name>/agents.csv   one row per agent per pair
    results/<run_name>/summary.md   generated numbers; the hand-written "Experiment" and
                                    "Observations" sections are kept on re-export

See notes/results_format.md for the meaning of every field.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HF_LOGS_REPO = "agent-coordination-lab/cooperbench-run-logs"
HF_LOGS_URL = f"https://huggingface.co/datasets/{HF_LOGS_REPO}/tree/main"
EXPERIMENT_HEADER = "## Experiment"
OBSERVATIONS_HEADER = "## Observations"
HAND_WRITTEN = {
    EXPERIMENT_HEADER: "_(What this run tests, how it differs from other runs, and why we ran it.)_",
    OBSERVATIONS_HEADER: "_(What we saw in the traces.)_",
}
HARNESS_CONFIG_DIR = Path(__file__).resolve().parent.parent / "src/cooperbench/agents/mini_swe_agent_v2/config"
STEP_LIMIT_RE = re.compile(r"^\s*step_limit:\s*(\d+)", re.MULTILINE)
COMPACTION_RE = re.compile(r"^\s*compaction_token_trigger:\s*(\d+)", re.MULTILINE)
THINKING_RE = re.compile(r"^\s*thinkingLevel:\s*([A-Za-z]+)", re.MULTILINE)

RATE_LIMIT_RE = re.compile(r"^Retrying .*RateLimitError", re.IGNORECASE)
SERVER_BUSY_RE = re.compile(
    r"^Retrying .*(ServiceUnavailableError|InternalServerError|BadGatewayError|GatewayTimeoutError)",
    re.IGNORECASE,
)

PAIR_FIELDS = [
    "repo",
    "task_id",
    "feature_a",
    "feature_b",
    "setting",
    "both_passed",
    "feature_a_passed",
    "feature_b_passed",
    "merge_status",
    "merge_strategy",
    "eval_error",
    "n_agents",
    "agents_at_step_limit",
    "agents_errored",
    "steps_total",
    "cost_usd",
    "duration_s",
    "messages_sent",
    "patch_lines_total",
]

AGENT_FIELDS = [
    "repo",
    "task_id",
    "feature_a",
    "feature_b",
    "agent_id",
    "feature_id",
    "role",
    "status",
    "steps",
    "cost_usd",
    "patch_lines",
    "model_calls",
    "reasoning_tokens",
    "compactions",
    "error",
]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def resolve_traj_path(pair_dir: Path, agent_id: str, feature_id: int | None) -> Path:
    """Prefer *_full_traj.json (written on >=1 compaction); fall back to *_traj.json."""
    full_name = "solo_full_traj.json" if agent_id == "solo" else f"{agent_id}_full_traj.json"
    full_path = pair_dir / full_name
    if full_path.exists():
        return full_path
    if agent_id == "solo":
        return pair_dir / "solo_traj.json"
    if feature_id is not None and (pair_dir / f"agent{feature_id}_traj.json").exists():
        return pair_dir / f"agent{feature_id}_traj.json"
    return pair_dir / f"{agent_id}_traj.json"


def trajectory_stats(path: Path) -> dict:
    """Count solver calls, reasoning tokens, and compactions in an agent trajectory."""
    traj = load_json(path)
    if traj is None:
        return {"model_calls": "", "reasoning_tokens": "", "compactions": ""}
    segments = traj.get("segments") or []
    if segments:
        compactions = sum(s.get("kind") == "summarizer" for s in segments)
        solver_msgs = [m for s in segments if s.get("kind") != "summarizer" for m in s.get("messages", [])]
    else:
        solver_msgs = traj.get("messages") or []
        compactions = sum(bool((m.get("extra") or {}).get("summary")) for m in solver_msgs)

    calls = 0
    reasoning = 0
    seen: set[object] = set()
    for m in solver_msgs:
        extra = m.get("extra") or {}
        response = extra.get("response")
        if not response or extra.get("summary"):
            continue
        rid = response.get("id") or extra.get("timestamp") or id(m)
        if rid in seen:
            continue
        seen.add(rid)
        calls += 1
        details = (response.get("usage") or {}).get("completion_tokens_details") or {}
        reasoning += details.get("reasoning_tokens") or 0
    return {
        "model_calls": calls,
        "reasoning_tokens": reasoning,
        "compactions": compactions,
    }


def compute_load(run_dir: Path, traj_paths: list[Path]) -> dict:
    """Compute per-minute input token and call load plus retry counts from console.log."""
    tokens_per_min: dict[int, int] = defaultdict(int)
    calls_per_min: dict[int, int] = defaultdict(int)
    seen: set[object] = set()

    for path in traj_paths:
        traj = load_json(path)
        if traj is None:
            continue
        segments = traj.get("segments") or []
        messages = [m for s in segments for m in s.get("messages", [])] or traj.get("messages") or []
        for m in messages:
            extra = m.get("extra") or {}
            response = extra.get("response")
            ts = extra.get("timestamp")
            if not response or not ts:
                continue
            rid = response.get("id") or (str(path), ts)
            if rid in seen:
                continue
            seen.add(rid)
            bucket = int(ts // 60)
            tokens_per_min[bucket] += (response.get("usage") or {}).get("prompt_tokens") or 0
            calls_per_min[bucket] += 1

    total_retries = 0
    rate_limit_retries = 0
    server_busy_retries = 0
    console = run_dir / "console.log"
    if console.exists():
        for line in console.read_text(errors="replace").splitlines():
            if line.startswith("Retrying "):
                total_retries += 1
                if RATE_LIMIT_RE.search(line):
                    rate_limit_retries += 1
                elif SERVER_BUSY_RE.search(line):
                    server_busy_retries += 1

    tok_vals = list(tokens_per_min.values())
    call_vals = list(calls_per_min.values())
    return {
        "peak_input_tokens_per_min": max(tok_vals) if tok_vals else 0,
        "median_input_tokens_per_min": int(statistics.median(tok_vals)) if tok_vals else 0,
        "peak_calls_per_min": max(call_vals) if call_vals else 0,
        "total_retries": total_retries,
        "rate_limit_retries": rate_limit_retries,
        "server_busy_retries": server_busy_retries,
    }


def agents_from_result(result: dict) -> dict[str, dict]:
    """Normalize solo / coop / team result.json into {agent_id: agent_dict}."""
    if "agents" in result:
        return result["agents"]
    if "agent" in result:  # solo
        return {"solo": {**result["agent"], "feature_id": None}}
    return {}


def export_pair(pair_dir: Path, setting: str) -> tuple[dict, list[dict], list[Path]] | None:
    result = load_json(pair_dir / "result.json")
    if result is None:
        return None
    ev = load_json(pair_dir / "eval.json") or {}
    features = result.get("features") or []
    fa, fb = (features + [None, None])[:2]
    merge = ev.get("merge") or {}
    lead = result.get("lead_agent")

    agents = agents_from_result(result)
    agent_rows = []
    traj_paths = []
    for agent_id, a in agents.items():
        fid = a.get("feature_id")
        traj_path = resolve_traj_path(pair_dir, agent_id, fid)
        traj_paths.append(traj_path)
        stats = trajectory_stats(traj_path)
        if setting == "team":
            role = a.get("team_role") or ("lead" if agent_id == lead else "member")
        elif setting == "solo":
            role = "solo"
        else:
            role = "peer"
        agent_rows.append(
            {
                "repo": result.get("repo"),
                "task_id": result.get("task_id"),
                "feature_a": fa,
                "feature_b": fb,
                "agent_id": agent_id,
                "feature_id": fid if fid is not None else "",
                "role": role,
                "status": a.get("status"),
                "steps": a.get("steps", 0),
                "cost_usd": round(a.get("cost") or 0, 6),
                "patch_lines": a.get("patch_lines", 0),
                **stats,
                "error": a.get("error") or "",
            }
        )

    pair_row = {
        "repo": result.get("repo"),
        "task_id": result.get("task_id"),
        "feature_a": fa,
        "feature_b": fb,
        "setting": setting,
        "both_passed": bool(ev.get("both_passed", False)),
        "feature_a_passed": bool((ev.get("feature1") or {}).get("passed", False)),
        "feature_b_passed": bool((ev.get("feature2") or {}).get("passed", False)),
        "merge_status": merge.get("status", "n/a") if setting != "solo" else "n/a",
        "merge_strategy": merge.get("strategy", "") if setting != "solo" else "",
        "eval_error": ev.get("error") or ("not evaluated" if not ev else ""),
        "n_agents": len(agent_rows),
        "agents_at_step_limit": sum(r["status"] == "LimitsExceeded" for r in agent_rows),
        "agents_errored": sum(r["status"] == "Error" for r in agent_rows),
        "steps_total": sum(r["steps"] or 0 for r in agent_rows),
        "cost_usd": round(result.get("total_cost") or sum(r["cost_usd"] for r in agent_rows), 6),
        "duration_s": round(result.get("duration_seconds") or 0, 1),
        "messages_sent": result.get("messages_sent", 0),
        "patch_lines_total": sum(r["patch_lines"] or 0 for r in agent_rows),
    }
    return pair_row, agent_rows, traj_paths


def agent_budgets(setting: str, agent_config: str | None) -> dict:
    """Step limit and compaction threshold: our agent config overrides the harness default config."""
    default_name = "solo.yaml" if setting == "solo" else "coop.yaml"
    default_path = HARNESS_CONFIG_DIR / default_name
    defaults = default_path.read_text() if default_path.exists() else ""
    budgets: dict = {}
    for key, pattern in (("step_limit", STEP_LIMIT_RE), ("compaction_token_trigger", COMPACTION_RE)):
        match = pattern.search(agent_config or "") or pattern.search(defaults)
        budgets[key] = int(match.group(1)) if match else None
    thinking = THINKING_RE.search(agent_config or "")
    budgets["thinking_level"] = thinking.group(1).lower() if thinking else None
    return budgets


def read_hand_written(summary_md: Path) -> dict[str, str]:
    """Return the bodies of the hand-written sections of an existing summary.md."""
    sections: dict[str, str] = {}
    if not summary_md.exists():
        return sections
    current: str | None = None
    for line in summary_md.read_text().splitlines():
        if line.startswith("## "):
            current = line.strip() if line.strip() in HAND_WRITTEN else None
            if current:
                sections[current] = ""
            continue
        if current:
            sections[current] += line + "\n"
    return {k: v.strip() for k, v in sections.items() if v.strip() and v.strip() != HAND_WRITTEN[k]}


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_summary(run: dict, pairs: list[dict], hand_written: dict[str, str]) -> str:
    h = run["headline"]
    load = run["load"]
    b = run.get("budgets") or {}
    n_agents = max((p["n_agents"] for p in pairs), default=0)
    steps = f"{b['step_limit']} per agent" if b.get("step_limit") else "unknown"
    trigger = b.get("compaction_token_trigger")
    compaction = f"at {trigger // 1000}K tokens" if trigger else "unknown"
    git_note = " with shared git" if run.get("git_enabled") else ""
    lines = [
        f"# {run['run_name']}",
        "",
        "<!-- Generated by tools/export_results.py. Edit only the Experiment and Observations sections. -->",
        "",
        EXPERIMENT_HEADER,
        "",
        hand_written.get(EXPERIMENT_HEADER) or HAND_WRITTEN[EXPERIMENT_HEADER],
        "",
        "## Results",
        "",
        "| | |",
        "| :--- | :--- |",
        f"| Setting | `{run.get('setting')}`{git_note}, {n_agents} agent{'s' if n_agents != 1 else ''} per pair |",
        f"| Model | `{run.get('model')}`, {b.get('thinking_level') or 'LiteLLM default'} thinking |",
        f"| Subset | `{run.get('subset') or 'custom'}` ({h['pairs']} pair{'s' if h['pairs'] != 1 else ''}) |",
        f"| Step limit | {steps} |",
        f"| Compaction | {compaction} |",
        f"| Passed | {h['passed']}/{h['pairs']} ({h['pass_rate']:.0%}) |",
        f"| Agents stopped at the step limit | {h['agents_at_step_limit']} |",
        f"| Merge conflicts | {h['merge_conflicts']} |",
        f"| Agent errors | {h['agents_errored']} |",
        f"| Cost | `${h['cost_usd']:.2f}` (`${h['cost_per_pair_usd']:.2f}` per pair) |",
        f"| Wall time | {h['wall_minutes']:.0f} min |",
        "",
        "## Pairs",
        "",
        "| Pair | Passed | Feature A | Feature B | Merge | Cost |",
        "| :--- | :---: | :---: | :---: | :--- | ---: |",
    ]
    for p in pairs:
        mark = lambda v: "yes" if v else "no"  # noqa: E731
        lines.append(
            f"| `{p['repo']}/{p['task_id']}` ({p['feature_a']},{p['feature_b']}) | {mark(p['both_passed'])} "
            f"| {mark(p['feature_a_passed'])} | {mark(p['feature_b_passed'])} | {p['merge_status']} "
            f"| `${p['cost_usd']:.2f}` |"
        )
    key_slot = run.get("key_slot")
    lines += [
        "",
        OBSERVATIONS_HEADER,
        "",
        hand_written.get(OBSERVATIONS_HEADER) or HAND_WRITTEN[OBSERVATIONS_HEADER],
        "",
        "## Run Details",
        "",
        "| | |",
        "| :--- | :--- |",
        f"| Agent config | `{run.get('agent_config_path') or 'unknown'}` |",
        f"| Concurrency | `-c {run.get('concurrency')}` (pairs run at once) |",
        f"| API key slot | {key_slot if key_slot is not None else 'default'} |",
        f"| Commit | `{(run.get('git_commit') or 'unknown')[:7]}` |",
        (
            f"| Peak input load | {load['peak_input_tokens_per_min']:,} tok/min "
            f"({load['peak_calls_per_min']} calls/min, median {load['median_input_tokens_per_min']:,}) |"
        ),
        (
            f"| Model retries | {load['rate_limit_retries']} rate-limit (429), "
            f"{load['server_busy_retries']} server-busy (5xx), {load['total_retries']} total |"
        ),
        f"| Raw logs | [{run['run_name']}/]({HF_LOGS_URL}/{run['run_name']}) (private dataset, see notes/logs_archive.md) |",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_name")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()

    run_dir = Path(args.logs_dir) / args.run_name
    if not run_dir.is_dir():
        print(f"error: {run_dir} not found", file=sys.stderr)
        return 1

    config = load_json(run_dir / "config.json") or {}
    summary = load_json(run_dir / "summary.json") or {}
    launch = load_json(run_dir / "launch.json") or {}
    setting = config.get("setting") or launch.get("setting") or "unknown"

    pairs: list[dict] = []
    agents: list[dict] = []
    traj_paths: list[Path] = []
    for result_file in sorted(run_dir.glob("*/*/*/*/result.json")):
        exported = export_pair(result_file.parent, setting)
        if exported:
            pairs.append(exported[0])
            agents.extend(exported[1])
            traj_paths.extend(exported[2])
    if not pairs:
        print(f"error: no result.json files under {run_dir}", file=sys.stderr)
        return 1

    passed = sum(p["both_passed"] for p in pairs)
    cost = sum(p["cost_usd"] for p in pairs)
    load = compute_load(run_dir, traj_paths)
    run = {
        "run_name": args.run_name,
        "setting": setting,
        "git_enabled": launch.get("git_enabled"),
        "agent_framework": config.get("agent_framework"),
        "model": config.get("model"),
        "subset": launch.get("subset"),
        "concurrency": launch.get("concurrency", config.get("concurrency")),
        "key_slot": launch.get("key_slot"),
        "command": launch.get("command"),
        "git_commit": launch.get("git_commit"),
        "git_dirty": launch.get("git_dirty"),
        "agent_config_path": launch.get("agent_config_path"),
        "agent_config": launch.get("agent_config"),
        "budgets": agent_budgets(setting, launch.get("agent_config")),
        "versions": launch.get("versions"),
        "started_at": config.get("started_at"),
        "completed_at": summary.get("completed_at"),
        "raw_logs": f"hf://datasets/{HF_LOGS_REPO}/{args.run_name}",
        "headline": {
            "pairs": len(pairs),
            "passed": passed,
            "pass_rate": passed / len(pairs),
            "merge_conflicts": sum(p["merge_status"] == "conflicts" for p in pairs),
            "agents_at_step_limit": sum(p["agents_at_step_limit"] for p in pairs),
            "agents_errored": sum(p["agents_errored"] for p in pairs),
            "cost_usd": round(cost, 4),
            "cost_per_pair_usd": round(cost / len(pairs), 4),
            "wall_minutes": round((summary.get("total_time_seconds") or 0) / 60, 1),
        },
        "load": load,
    }

    out = Path(args.results_dir) / args.run_name
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    write_csv(out / "pairs.csv", PAIR_FIELDS, pairs)
    write_csv(out / "agents.csv", AGENT_FIELDS, agents)

    summary_md = out / "summary.md"
    summary_md.write_text(render_summary(run, pairs, read_hand_written(summary_md)))

    print(f"exported {len(pairs)} pairs to {out}/ (pass rate {passed}/{len(pairs)}, cost ${cost:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
