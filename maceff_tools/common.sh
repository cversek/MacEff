#!/usr/bin/env bash
set -euo pipefail

# Hard defaults (only if not already set in environment)
PA="${PA:-maceff_user001}"
SID="${SID:-001}"
PORT="${PORT:-2222}"
KEYS_DIR="${KEYS_DIR:-keys}"
PROJ="${PROJ:-demo}"

repo_root() { git rev-parse --show-toplevel 2>/dev/null || pwd; }

# Load dotenv-like files if present
_dotenv() { # usage: _dotenv FILE
  local f="$1"
  [[ -f "$f" ]] || return 0
  # ignore comments/blank lines; export KEY=VALUE (no spaces)
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"; val="${BASH_REMATCH[2]}"
      export "${key}=${val}"
    fi
  done < "$f"
}

# 1) global env
_dotenv "$(repo_root)/.maceff/global.env"

# 2) project from selector file if not provided by env/CLI
if [[ -z "${PROJ:-}" || "${PROJ}" == "demo" ]]; then
  if [[ -s "$(repo_root)/.maceff/project" ]]; then
    PROJ="$(cat "$(repo_root)/.maceff/project")"
  fi
fi

# 3) per-project env (overrides)
_dotenv "$(repo_root)/.maceff/projects/${PROJ}.env"

# Finally, allow existing environment to override loaded values
PA="${PA:-$PA}"
SID="${SID:-$SID}"
PORT="${PORT:-$PORT}"
KEYS_DIR="${KEYS_DIR:-$KEYS_DIR}"
PROJ="${PROJ:-$PROJ}"
MACEFF_POLICY_SET="${MACEFF_POLICY_SET:-${MACEFF_POLICY_SET:-default}}"
MACEFF_TOOLSET="${MACEFF_TOOLSET:-${MACEFF_TOOLSET:-base}}"

find_pa_key() {
  local key="${PA_KEY:-}"
  if [[ -n "${key}" && -f "${key}" ]]; then echo "${key}"; return 0; fi
  local base; base="$(echo "${PA}" | sed -E 's/[0-9]+$//')"
  for cand in "${KEYS_DIR}/${PA}" "$HOME/.ssh/id_ed25519_${PA}" "$HOME/.ssh/id_ed25519_${base}"; do
    [[ -f "$cand" ]] && { echo "$cand"; return 0; }
  done
  echo "PA key not found. Set PA_KEY or create one of: ${KEYS_DIR}/${PA}, \$HOME/.ssh/id_ed25519_${PA}, \$HOME/.ssh/id_ed25519_${base}" >&2
  return 1
}

find_admin_key() {
  local key="${ADMIN_KEY:-}"
  if [[ -n "${key}" && -f "${key}" ]]; then echo "${key}"; return 0; fi
  for cand in "${KEYS_DIR}/admin" "$HOME/.ssh/id_ed25519_admin"; do
    [[ -f "$cand" ]] && { echo "$cand"; return 0; }
  done
  echo "ADMIN key not found. Set ADMIN_KEY or create one of: ${KEYS_DIR}/admin, \$HOME/.ssh/id_ed25519_admin" >&2
  return 1
}

# If HOST_SSH_PORT is set, prefer it for host connections
if [[ -n "${HOST_SSH_PORT:-}" ]]; then
  PORT="${HOST_SSH_PORT}"
fi
