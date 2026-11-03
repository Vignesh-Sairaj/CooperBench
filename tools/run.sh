#!/usr/bin/env bash
# Run a CooperBench benchmark with the team defaults and record how it was launched.
#
# Usage:
#   tools/run.sh <setting> <subset> <concurrency> [extra cooperbench run args...]
#   tools/run.sh solo flash 8
#   tools/run.sh coop flash 4 --git
#
# By default every run uses the frozen reference config (configs/reference/medium.yaml,
# see notes/model_config.md#reference-setup) and its name ends in "-ref", so it never
# reuses the folder of an older run made with other settings. To add a method suffix for
# an intervention or variant arm, set RUN_SUFFIX (for example RUN_SUFFIX=verifier).
# Set AGENT_CONFIG to use another config (for example configs/reference/low.yaml), and
# MODEL to use another model or provider (default vertex_ai/gemini-3.8-flash; the run name
# strips the provider prefix and keeps the model name).
#
# Credentials come from .env (gitignored):
#   - For vertex_ai/* models (default): authenticate once with
#     `gcloud auth application-default login`, set VERTEXAI_PROJECT (and optional
#     VERTEXAI_PROJECT_1, VERTEXAI_PROJECT_2, ... for parallel runs via KEY_SLOT=<n>),
#     and VERTEXAI_LOCATION defaults to "global".
#   - For gemini/* models (AI Studio): set GEMINI_API_KEY (and optional
#     GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... for KEY_SLOT=<n>).
# Only the slot number is recorded in launch.json, never project IDs or API keys.
#
# Writes into logs/<run_name>/:
#   launch.json     command, git commit, agent config, package versions, concurrency
#   console.log     everything the run printed (model retry warnings land here)
#   resources.log   load, memory, and container count every 30 seconds
#
# Set UV_RUN to change how uv is invoked (default: "uv run --frozen").
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null 2>&1 || PATH="$HOME/.local/bin:$PATH"

if [[ $# -lt 3 ]]; then
  sed -n '2,8p' "$0"
  exit 1
fi

if [[ -f .env ]]; then
  while IFS='=' read -r -d '' _k _v; do
    if [[ "$_k" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && -z "${!_k+x}" ]]; then
      export "$_k=$_v"
    fi
  done < <(env -i HOME="${HOME:-}" bash -c 'set -a; source .env >/dev/null 2>&1; env -0')
  unset _k _v
fi

SETTING="$1"; SUBSET="$2"; CONC="$3"; shift 3
EXTRA=("$@")
UV_RUN="${UV_RUN:-uv run --frozen}"
MODEL="${MODEL:-vertex_ai/gemini-3.8-flash}"
AGENT="mini_swe_agent_v2"
CONFIG="${AGENT_CONFIG:-configs/reference/medium.yaml}"
# Reference runs get a "-ref" name suffix unless RUN_SUFFIX is set.
if [[ -z "${AGENT_CONFIG:-}" && -z "${RUN_SUFFIX:-}" ]]; then RUN_SUFFIX="ref"; fi
KEY_SLOT="${KEY_SLOT:-}"
if [[ "$MODEL" == vertex_ai/* ]]; then
  export VERTEXAI_LOCATION="${VERTEXAI_LOCATION:-global}"
  if [[ -n "$KEY_SLOT" ]]; then
    PROJ_VAR="VERTEXAI_PROJECT_${KEY_SLOT}"
    if [[ -z "${!PROJ_VAR:-}" ]]; then
      echo "error: KEY_SLOT=$KEY_SLOT with $MODEL requires $PROJ_VAR (run: set -a; source .env; set +a)" >&2
      exit 1
    fi
    export VERTEXAI_PROJECT="${!PROJ_VAR}"
  else
    export VERTEXAI_PROJECT="${VERTEXAI_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
    if [[ -z "$VERTEXAI_PROJECT" ]]; then
      echo "error: $MODEL requires VERTEXAI_PROJECT in .env (run: set -a; source .env; set +a)" >&2
      exit 1
    fi
  fi
elif [[ -n "$KEY_SLOT" ]]; then
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
