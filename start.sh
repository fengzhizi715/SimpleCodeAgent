#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${ROOT_DIR}/.venv/bin/activate"

HAS_SESSION_ID=false
for arg in "$@"; do
  if [[ "$arg" == "--session-id" ]] || [[ "$arg" == --session-id=* ]]; then
    HAS_SESSION_ID=true
    break
  fi
done

if [[ -n "${SESSION_ID:-}" && "${HAS_SESSION_ID}" == "false" ]]; then
  python -m app.main "$@" --session-id "${SESSION_ID}"
else
  python -m app.main "$@"
fi
