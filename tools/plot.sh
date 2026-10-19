#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 1 ]]; then
  WORK_INPUT="$1"
elif [[ $# -eq 2 && "$1" == "--work" ]]; then
  WORK_INPUT="$2"
else
  printf 'Usage: %s [--work] WORK_DIRECTORY\n' "$0" >&2
  printf 'Example: %s --work results/api_reproduct\n' "$0" >&2
  exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(cd "$WORK_INPUT" && pwd)"
cd "$REPO"
uv run python -m tools.reproduce --work "$WORK"
