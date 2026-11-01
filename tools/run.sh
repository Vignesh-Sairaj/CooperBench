#!/usr/bin/env bash
# Run a CooperBench benchmark with the team defaults and record how it was launched.
#
# Usage:
#   tools/run.sh <setting> <subset> <concurrency> [extra cooperbench run args...]
#   tools/run.sh solo flash_10 10
#   tools/run.sh coop flash_10 5 --git
#
# The run name is the CLI's own auto-generated name. To add a method suffix for an
# intervention or variant arm, set RUN_SUFFIX (for example RUN_SUFFIX=verifier).
# Set AGENT_CONFIG to override the default config (configs/gemini_3_8_flash_high.yaml).
#
# Gemini rate limits are per GCP project, so parallel runs need keys from different
# projects. Put them in .env as GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... and set
# KEY_SLOT=<n> to run with GEMINI_API_KEY_<n>. Without KEY_SLOT the run uses
# GEMINI_API_KEY. Only the slot number is recorded, never the key.
#
# Writes into logs/<run_name>/:
#   launch.json     command, git commit, agent config, package versions, concurrency
#   console.log     everything the run printed (model retry warnings land here)
#   resources.log   load, memory, and container count every 30 seconds
#
# Set UV_RUN to change how uv is invoked (default: "uv run --frozen").
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -lt 3 ]]; then
  sed -n '2,8p' "$0"
  exit 1
fi

SETTING="$1"; SUBSET="$2"; CONC="$3"; shift 3
EXTRA=("$@")
UV_RUN="${UV_RUN:-uv run --frozen}"
MODEL="gemini/gemini-3.8-flash"
AGENT="mini_swe_agent_v2"
CONFIG="${AGENT_CONFIG:-configs/gemini_3_8_flash_high.yaml}"
KEY_SLOT="${KEY_SLOT:-}"
if [[ -n "$KEY_SLOT" ]]; then
  KEY_VAR="GEMINI_API_KEY_${KEY_SLOT}"
  if [[ -z "${!KEY_VAR:-}" ]]; then
    echo "error: KEY_SLOT=$KEY_SLOT but $KEY_VAR is not set (run: set -a; source .env; set +a)" >&2
    exit 1
  fi
  export GEMINI_API_KEY="${!KEY_VAR}"
fi

GIT_ENABLED=False
for a in "${EXTRA[@]}"; do [[ "$a" == "--git" ]] && GIT_ENABLED=True; done

RUN_NAME=$($UV_RUN python -c "
from cooperbench.cli import _generate_run_name as g
print(g(setting='$SETTING', model='$MODEL', agent='$AGENT', subset='$SUBSET', git_enabled=$GIT_ENABLED))")
[[ -n "${RUN_SUFFIX:-}" ]] && RUN_NAME="${RUN_NAME}-${RUN_SUFFIX}"

RUN_DIR="logs/${RUN_NAME}"
mkdir -p "$RUN_DIR"

CMD=(cooperbench run -n "$RUN_NAME" -s "$SUBSET" -a "$AGENT" -m "$MODEL" --agent-config "$CONFIG"
     --setting "$SETTING" -c "$CONC" --backend docker "${EXTRA[@]}")

$UV_RUN python - "$RUN_DIR/launch.json" "$RUN_NAME" "$SETTING" "$SUBSET" "$CONC" "$GIT_ENABLED" "$CONFIG" "${CMD[*]}" "$KEY_SLOT" <<'PY'
import datetime, importlib.metadata as md, json, os, pathlib, subprocess, sys
out, run_name, setting, subset, conc, git_enabled, config, cmd, key_slot = sys.argv[1:10]
git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
json.dump({
    "run_name": run_name,
    "setting": setting,
    "subset": subset,
    "git_enabled": git_enabled == "True",
    "concurrency": int(conc),
    "key_slot": int(key_slot) if key_slot else None,
    "command": cmd,
    "launched_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "git_commit": git("rev-parse", "HEAD"),
    "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
    "agent_config_path": config,
    "agent_config": pathlib.Path(config).read_text(),
    "versions": {p: md.version(p) for p in ["cooperbench", "litellm"]},
    "cpus": os.cpu_count(),
}, open(out, "w"), indent=2)
PY

( while true; do
    echo "$(date -Is) load=$(cut -d' ' -f1-3 /proc/loadavg) mem_used_gb=$(free -g | awk '/Mem:/{print $3}') containers=$(docker ps -q | wc -l)"
    sleep 30
  done ) > "$RUN_DIR/resources.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null || true' EXIT

echo "run: $RUN_NAME (key slot: ${KEY_SLOT:-default})"
$UV_RUN "${CMD[@]}" 2>&1 | tee "$RUN_DIR/console.log"
echo "rate-limit retries (429): $(grep -ciE '^Retrying .*RateLimitError' "$RUN_DIR/console.log" || true)"
echo "server-busy retries (5xx): $(grep -ciE '^Retrying .*(ServiceUnavailableError|InternalServerError|BadGatewayError|GatewayTimeoutError)' "$RUN_DIR/console.log" || true)"
echo "total model retries: $(grep -c '^Retrying ' "$RUN_DIR/console.log" || true)"
echo "next: $UV_RUN python tools/export_results.py $RUN_NAME"
