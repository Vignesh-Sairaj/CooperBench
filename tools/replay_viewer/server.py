"""Lightweight HTTP server for the CooperBench log replay viewer.

Serves static UI assets, provides JSON API endpoints for run discovery,
cross-run pair comparison, and compiled trajectory replays, or exports
a self-contained standalone HTML bundle.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tools.replay_viewer.compiler import (
    MAIN_REPO_ROOT,
    compile_pair_replay,
    list_pairs_index,
    list_runs,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ReplayRequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for replay viewer API and frontend static assets."""

    repo_root: Path = MAIN_REPO_ROOT

    def do_GET(self) -> None:
        """Route incoming GET requests to API handlers or static files."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/runs":
            self._handle_api_runs()
        elif path == "/api/index":
            self._handle_api_index()
        elif path == "/api/replay":
            self._handle_api_replay(query)
        elif path in ("/", "/index.html"):
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        else:
            rel_path = path.lstrip("/")
            file_path = STATIC_DIR / rel_path
            if file_path.exists() and file_path.is_file():
                mime, _ = mimetypes.guess_type(str(file_path))
                self._serve_file(file_path, mime or "application/octet-stream")
            else:
                self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def _handle_api_runs(self) -> None:
        try:
            logs_dir = self.repo_root / "logs"
            results_dir = self.repo_root / "results"
            data = list_runs(logs_dir=logs_dir, results_dir=results_dir)
            self._send_json(data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_api_index(self) -> None:
        try:
            logs_dir = self.repo_root / "logs"
            results_dir = self.repo_root / "results"
            data = list_pairs_index(logs_dir=logs_dir, results_dir=results_dir)
            self._send_json(data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_api_replay(self, query: dict[str, list[str]]) -> None:
        run_name = query.get("run", [""])[0]
        repo = query.get("repo", [""])[0]
        task_id = query.get("task", [""])[0]
        f1_str = query.get("f1", [""])[0]
        f2_str = query.get("f2", [""])[0]

        if not (run_name and repo and task_id and f1_str and f2_str):
            self._send_json(
                {"error": "Missing required query parameters: run, repo, task, f1, f2"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            logs_dir = self.repo_root / "logs"
            results_dir = self.repo_root / "results"
            dataset_dir = self.repo_root / "dataset"
            data = compile_pair_replay(
                run_name=run_name,
                repo=repo,
                task_id=task_id,
                features=(int(f1_str), int(f2_str)),
                logs_dir=logs_dir,
                results_dir=results_dir,
                dataset_dir=dataset_dir,
            )
            self._send_json(data)
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._send_json({"error": "Failed to read file"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def export_static_html(
    output_path: Path | str,
    *,
    repo_root: Path | str = MAIN_REPO_ROOT,
    run_filter: list[str] | None = None,
    pair_filter: list[str] | None = None,
) -> Path:
    """Exports a self-contained HTML file containing preloaded replay data."""
    root = Path(repo_root)
    logs_dir = root / "logs"
    results_dir = root / "results"
    dataset_dir = root / "dataset"
    out_file = Path(output_path)

    all_runs = list_runs(logs_dir=logs_dir, results_dir=results_dir)
    if run_filter:
        runs = [r for r in all_runs if any(rf in r["run_name"] for rf in run_filter)]
    else:
        runs = all_runs

    run_names_set = {r["run_name"] for r in runs}

    all_pairs = list_pairs_index(logs_dir=logs_dir, results_dir=results_dir)
    filtered_pairs: list[dict[str, Any]] = []
    for p in all_pairs:
        pair_id = p.get("pair_id", "")
        if pair_filter and not any(pf in pair_id or pf in p["repo"] for pf in pair_filter):
            continue
        matching_runs = {k: v for k, v in p["runs"].items() if k in run_names_set}
        if matching_runs:
            pair_copy = dict(p)
            pair_copy["runs"] = matching_runs
            filtered_pairs.append(pair_copy)

    replays: dict[str, Any] = {}
    for p in filtered_pairs:
        repo = p["repo"]
        task_id = p["task_id"]
        fa = p["feature_a"]
        fb = p["feature_b"]
        for r_name in p["runs"]:
            key = f"{r_name}:{repo}:{task_id}:f{fa}_f{fb}"
            try:
                rep = compile_pair_replay(
                    run_name=r_name,
                    repo=repo,
                    task_id=task_id,
                    features=(fa, fb),
                    logs_dir=logs_dir,
                    results_dir=results_dir,
                    dataset_dir=dataset_dir,
                )
                replays[key] = rep
            except Exception as exc:
                print(f"Warning: could not compile replay for {key}: {exc}")

    bundle = {
        "runs": runs,
        "pairs": filtered_pairs,
        "replays": replays,
    }

    bundle_json = json.dumps(bundle, separators=(",", ":"))
    safe_bundle_json = bundle_json.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")

    template_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script_tag = f"<script>window.__PRELOADED_REPLAY_BUNDLE__ = {safe_bundle_json};</script>"
    bundled_html = template_html.replace("</head>", f"  {script_tag}\n</head>")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(bundled_html, encoding="utf-8")
    print(f"Exported self-contained replay viewer ({len(replays)} replays) to {out_file}")
    return out_file


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    repo_root: Path | str = MAIN_REPO_ROOT,
) -> None:
    """Starts the replay viewer server and serves requests until interrupted."""
    root_path = Path(repo_root)
    ReplayRequestHandler.repo_root = root_path
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, ReplayRequestHandler)
    print(f"CooperBench Replay Viewer listening on http://{host}:{port}")
    print(f"Reading logs, results, and dataset from: {root_path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        httpd.server_close()


def main() -> None:
    """CLI entrypoint for running the replay viewer server or exporting standalone HTML."""
    parser = argparse.ArgumentParser(description="CooperBench 3-Pane Replay Viewer Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=MAIN_REPO_ROOT,
        help="Path to CooperBench repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--export-html",
        type=Path,
        metavar="PATH",
        help="Compile and export a standalone self-contained HTML file without starting the server",
    )
    parser.add_argument(
        "--runs",
        nargs="*",
        metavar="RUN",
        help="Optional run name substring filters for HTML export (e.g. delivery-timing, stepcounter)",
    )
    parser.add_argument(
        "--pairs",
        nargs="*",
        metavar="PAIR",
        help="Optional pair substring filters for HTML export (e.g. outlines, 1655)",
    )
    args = parser.parse_args()

    if args.export_html:
        export_static_html(
            output_path=args.export_html,
            repo_root=args.repo_root,
            run_filter=args.runs,
            pair_filter=args.pairs,
        )
    else:
        run_server(host=args.host, port=args.port, repo_root=args.repo_root)


if __name__ == "__main__":
    main()
