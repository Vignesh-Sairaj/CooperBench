#!/usr/bin/env python3
"""Split a subset across several runs (one per API key), then merge them into one run.

Usage:
    uv run --frozen python tools/shards.py split <subset> <n>
    uv run --frozen python tools/shards.py merge <shard_run_name> [<shard_run_name> ...]

`split` writes n shard datasets under logs/_shards/<subset>-shard<k>of<n>/. Each one links to
the real task folders in dataset/ and has its own subset file listing about 1/n of the pairs.
Start one run per shard, each with its own key:

    KEY_SLOT=2 tools/run.sh solo flash-shard1of3 4 --dataset-dir logs/_shards/flash-shard1of3

`merge` combines the finished shard runs into logs/<run_name>/, where <run_name> is the shard
run name without its -shard<k>of<n> part. The merged folder looks like a normal run, so
tools/export_results.py works unchanged. Pair folders are hard links, so merging uses no
extra disk space.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
LOGS_DIR = REPO_ROOT / "logs"
SHARD_RE = re.compile(r"-shard(\d+)of(\d+)")


def split(subset: str, n: int) -> int:
    data = json.loads((DATASET_DIR / "subsets" / f"{subset}.json").read_text())
    pairs = [(t["repo"], t["task_id"], p) for t in data["tasks"] for p in t["pairs"]]
    if n < 2 or n > len(pairs):
        print(f"error: n must be between 2 and {len(pairs)}", file=sys.stderr)
        return 1
    for k in range(1, n + 1):
        name = f"{subset}-shard{k}of{n}"
        root = LOGS_DIR / "_shards" / name
        (root / "subsets").mkdir(parents=True, exist_ok=True)
        for entry in DATASET_DIR.iterdir():
            link = root / entry.name
            if entry.is_dir() and entry.name != "subsets" and not link.exists():
                link.symlink_to(entry.resolve())
        tasks: dict[tuple[str, int], list] = {}
        for repo, task_id, pair in pairs[k - 1 :: n]:
            tasks.setdefault((repo, task_id), []).append(pair)
        shard = {
            "name": name,
            "description": f"Shard {k} of {n} of the {subset} subset (every {n}th pair).",
            "parent": subset,
            "tasks": [{"repo": r, "task_id": t, "pairs": ps} for (r, t), ps in tasks.items()],
        }
        (root / "subsets" / f"{name}.json").write_text(json.dumps(shard, indent=2) + "\n")
        n_pairs = sum(len(ps) for ps in tasks.values())
        print(f"{name}: {n_pairs} pairs -> --dataset-dir {root.relative_to(REPO_ROOT)}")
    return 0


def merge(shard_runs: list[str]) -> int:
    bases = {SHARD_RE.sub("", r) for r in shard_runs}
    if len(bases) != 1 or not all(SHARD_RE.search(r) for r in shard_runs):
        print("error: pass shard runs of one experiment (names differing only in -shard<k>of<n>)", file=sys.stderr)
        return 1
    combined = bases.pop()
    out = LOGS_DIR / combined
    if out.exists():
        print(f"error: {out} already exists", file=sys.stderr)
        return 1
    dirs = [LOGS_DIR / r for r in shard_runs]
    missing = [d for d in dirs if not (d / "summary.json").exists()]
    if missing:
        print(f"error: unfinished or missing shard runs: {[d.name for d in missing]}", file=sys.stderr)
        return 1
    configs = [json.loads((d / "config.json").read_text()) for d in dirs]
    setting = configs[0]["setting"]
    seen: dict[Path, str] = {}
    for d in dirs:
        for result in (d / setting).glob("*/*/*/result.json"):
            pair = result.parent.relative_to(d / setting)
            if pair in seen:
                print(f"error: pair {pair} is in both {seen[pair]} and {d.name}", file=sys.stderr)
                return 1
            seen[pair] = d.name
    out.mkdir(parents=True)

    summaries = [json.loads((d / "summary.json").read_text()) for d in dirs]
    launches = [json.loads((d / "launch.json").read_text()) if (d / "launch.json").exists() else {} for d in dirs]
    parent = SHARD_RE.sub("", launches[0].get("subset") or "") or None

    for d in dirs:
        if (d / setting).is_dir():
            shutil.copytree(d / setting, out / setting, copy_function=os.link, dirs_exist_ok=True)

    config = {**configs[0], "run_name": combined, "total_tasks": sum(c.get("total_tasks", 0) for c in configs)}
    config["started_at"] = min(c.get("started_at") or "" for c in configs)
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    summary = {
        "run_name": combined,
        "completed_at": max(s.get("completed_at") or "" for s in summaries),
        "total_tasks": sum(s.get("total_tasks", 0) for s in summaries),
        "completed": sum(s.get("completed", 0) for s in summaries),
        "skipped": sum(s.get("skipped", 0) for s in summaries),
        "failed": sum(s.get("failed", 0) for s in summaries),
        "total_cost": sum(s.get("total_cost", 0) for s in summaries),
        "total_time_seconds": max(s.get("total_time_seconds", 0) for s in summaries),
        "shards": shard_runs,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    launch = {
        **launches[0],
        "run_name": combined,
        "subset": parent,
        "key_slot": None,
        "shards": [{"run_name": r, "key_slot": lch.get("key_slot")} for r, lch in zip(shard_runs, launches)],
    }
    (out / "launch.json").write_text(json.dumps(launch, indent=2) + "\n")

    with (out / "console.log").open("w") as f:
        for d in dirs:
            if (d / "console.log").exists():
                f.write((d / "console.log").read_text(errors="replace"))
    print(f"merged {len(dirs)} shards into {out.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_split = sub.add_parser("split", help="write shard datasets for a subset")
    p_split.add_argument("subset")
    p_split.add_argument("n", type=int)
    p_merge = sub.add_parser("merge", help="merge finished shard runs into one run")
    p_merge.add_argument("shard_runs", nargs="+")
    args = parser.parse_args()
    if args.cmd == "split":
        return split(args.subset, args.n)
    return merge(args.shard_runs)


if __name__ == "__main__":
    sys.exit(main())
