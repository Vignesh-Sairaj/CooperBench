#!/usr/bin/env bash
# Pre-pull every task Docker image a subset needs, so runs never wait on downloads
# (the harness gives each container 120 seconds to start, including the download).
#
# Usage:
#   tools/pull_images.sh <subset> [parallel_pulls]
#   tools/pull_images.sh flash_10
#   tools/pull_images.sh flash 4
#
# Set UV_RUN to change how uv is invoked (default: "uv run --frozen").
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null 2>&1 || PATH="$HOME/.local/bin:$PATH"

if [[ $# -lt 1 ]]; then
  sed -n '2,10p' "$0"
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

SUBSET="$1"
PARALLEL="${2:-3}"
UV_RUN="${UV_RUN:-uv run --frozen}"

IMAGES=$($UV_RUN python - "$SUBSET" <<'PY'
import json, sys
from pathlib import Path
from cooperbench.utils import get_image_name
path = Path("dataset/subsets") / f"{sys.argv[1]}.json"
tasks = json.loads(path.read_text())["tasks"]
print("\n".join(sorted({get_image_name(t["repo"], t["task_id"]) for t in tasks})))
PY
)

echo "Pulling $(echo "$IMAGES" | wc -l) images for $SUBSET ($PARALLEL at a time)..."
echo "$IMAGES" | xargs -P "$PARALLEL" -n 1 docker pull -q
echo "Done."
