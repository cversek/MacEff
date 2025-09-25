#!/usr/bin/env bash
set -euo pipefail
log(){ printf "[start.sh %s] %s\n" "$(date +%H:%M:%S)" "$*" >&2; }

ssh-keygen -A >/dev/null 2>&1 || true

# Groups for ACLs
getent group agents_all >/dev/null 2>&1 || groupadd agents_all
getent group sa_all     >/dev/null 2>&1 || groupadd sa_all

# Optionally keep admin home ephemeral even though /home is persisted
if [[ "${CLEAN_ADMIN_HOME:-0}" == "1" ]]; then
  rm -rf /home/admin/* /home/admin/.[!.]* /home/admin/..?* 2>/dev/null || true
fi

# Shared collaborative area (world-writable sticky at init; we harden below)
install -d -m 1777 /shared_workspace

install_key(){
  local user="$1"
  if id "$user" >/dev/null 2>&1; then
    install -d -m 700 -o "$user" -g "$user" "/home/$user/.ssh"
    if [[ -f "/keys/${user}.pub" ]]; then
      install -m 600 -o "$user" -g "$user" "/keys/${user}.pub" "/home/$user/.ssh/authorized_keys"
      log "SSH key: $user"
    fi
  fi
}

mk_pa(){
  local pa="$1"
  if ! id "$pa" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$pa"
    usermod -aG agents_all "$pa"
    log "PA user created: $pa"
  fi
  install -d -m 755 -o "$pa" -g "$pa" "/home/$pa"
  install_key "$pa"
  # Claude: keep working dir stable across tool calls
  su - "$pa" -c 'mkdir -p ~/.claude; jq -n --arg on "1" "{env:{CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR:\$on}}" > ~/.claude/settings.json' || true
}

mk_sa(){
  local pa="$1" sid="$2"
  local sa="sa_${pa}_${sid}"
  if ! id "$sa" >/dev/null 2>&1; then
    useradd -m -s /usr/sbin/nologin "$sa"
    usermod -aG sa_all "$sa"
    log "SA user created: $sa"
  fi
  printf '%s\n' "$sa"   # <-- only the username to stdout
}

setup_agent_tree(){
  local pa="$1" sid="$2"
  local sa; sa="$(mk_sa "$pa" "$sid")"

  local H="/home/$pa"
  local A="$H/agent"
  local PUB="$A/public"
  local PRIV="$A/private"
  local SUBS="$A/subagents"
  local ROOT="$SUBS/$sid"
  local SA_PUB="$ROOT/public"
  local SA_PRIV="$ROOT/private"
  local SA_ASN="$ROOT/assigned"
  local SA_DEF="$ROOT/SUBAGENT_DEF.md"

  # Parent non-writable, subdirs RW by their owners
  install -d -m 0555 -o root -g "$pa" "$A"
  install -d -m 0750 -o "$pa" -g "$pa" "$PUB" "$PRIV"
  install -d -m 0555 -o root -g "$pa" "$SUBS"
  install -d -m 0555 -o root -g "$pa" "$ROOT"

  install -d -m 0750 -o "$sa" -g "$sa" "$SA_PUB" "$SA_PRIV"
  install -d -m 0750 -o "$sa" -g "$sa" "$SA_PUB/logs" "$SA_PRIV/logs"
  install -d -m 0755 -o "$pa" -g "$pa" "$SA_ASN"
  [[ -f "$SA_DEF" ]] || install -m 0644 -o root -g "$pa" /dev/null "$SA_DEF"

  # ACLs
  # PA: r/w/x in assigned; r/x in SA public/private
  setfacl -m u:$pa:rwx "$SA_ASN"; setfacl -d -m u:$pa:rwx "$SA_ASN"
  setfacl -m u:$pa:rx  "$SA_PUB" "$SA_PRIV"; setfacl -d -m u:$pa:rx "$SA_PUB" "$SA_PRIV"
  # SA: rwx in own public/private; r/x in assigned
  setfacl -m u:$sa:rwx "$SA_PUB" "$SA_PRIV"; setfacl -d -m u:$sa:rwx "$SA_PUB" "$SA_PRIV"
  setfacl -m u:$sa:rx  "$SA_ASN"; setfacl -d -m u:$sa:rx "$SA_ASN"
  # Peers: read-only on public/assigned; no access to private
  setfacl -m g:sa_all:rx "$SA_PUB" "$SA_ASN"; setfacl -d -m g:sa_all:rx "$SA_PUB" "$SA_ASN"
  setfacl -m g:sa_all:--- "$SA_PRIV";      setfacl -d -m g:sa_all:--- "$SA_PRIV"

  # Seed SUBAGENT_DEF.md if present in /opt/agent_defs
  local PAD="$(printf "%s" "$pa" | sed -E 's/^maceff_user//')"
  local DEF_SRC="/opt/agent_defs/PA${PAD}/SA${sid}/SUBAGENT_DEF.md"
  if [[ -f "$DEF_SRC" ]]; then
    install -m 0644 -o root -g "$pa" "$DEF_SRC" "$SA_DEF"
    log "Seeded DEF for $pa/$sid"
  fi

  # sudoers: PA can run sa-exec as this SA (only)
  local SUDO_LINE="$pa ALL=($sa) NOPASSWD: /usr/local/bin/sa-exec"
  grep -qxF "$SUDO_LINE" /etc/sudoers.d/agents 2>/dev/null || echo "$SUDO_LINE" >> /etc/sudoers.d/agents
  chmod 0440 /etc/sudoers.d/agents
}

# --- Discover PAs/SAs from /opt/agent_defs; fallback to DEFAULT_PA + SA001 ---
declare -a PAS
if compgen -G "/opt/agent_defs/PA*/SA*/SUBAGENT_DEF.md" >/dev/null; then
  while IFS= read -r pa_dir; do
    pa_num="${pa_dir##*/PA}"; pa="maceff_user${pa_num}"
    PAS+=("$pa")
  done < <(find /opt/agent_defs -maxdepth 1 -type d -name 'PA*' | sort)
  PAS=($(printf "%s\n" "${PAS[@]}" | awk '!x[$0]++'))  # uniq
else
  PAS=("${DEFAULT_PA:-maceff_user001}")
fi

: > /etc/sudoers.d/agents  # reset sudoers scope each boot
for pa in "${PAS[@]}"; do
  mk_pa "$pa"
  pa_num="${pa#maceff_user}"

  if compgen -G "/opt/agent_defs/PA${pa_num}/SA*/SUBAGENT_DEF.md" >/dev/null; then
    while IFS= read -r sa_dir; do
      sa_id="${sa_dir##*/SA}"
      setup_agent_tree "$pa" "$sa_id"
    done < <(find "/opt/agent_defs/PA${pa_num}" -maxdepth 1 -type d -name 'SA*' | sort)
  else
    setup_agent_tree "$pa" "001"
  fi
done

# Tools (maceff) in shared venv with global CLI (+ PyYAML for policy validation)
if [[ -d /opt/tools ]]; then
  log "Installing maceff into /opt/maceff-venv..."
  VENV="/opt/maceff-venv"
  if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip -q install --upgrade pip
  fi
  uv pip install --python "$VENV/bin/python" -e /opt/tools >/dev/null
  # Ensure policyctl test can validate YAML even on a fresh boot
  uv pip install --python "$VENV/bin/python" 'pyyaml==6.*' >/dev/null 2>&1 || true
  ln -sf "$VENV/bin/macf_tools" /usr/local/bin/macf_tools
fi

# Admin key (if any)
install_key admin

# --- enforce collaborative perms on /shared_workspace ---
getent group agents_all >/dev/null 2>&1 || groupadd agents_all
chgrp -R agents_all /shared_workspace || true
chmod -R g+ws     /shared_workspace  || true
chmod g+s /shared_workspace || true   # inherit group on new dirs
chmod +t  /shared_workspace || true   # sticky bit for safer deletes
log "shared_workspace perms: $(stat -c '%A %U %G %n' /shared_workspace)"

# ---- MacEff policy editor setup (idempotent) ----
set -e
groupadd -f policyeditors || true
install -d -o root -g policyeditors -m 2770 /opt/maceff/policies
find /opt/maceff/policies -type d -exec chgrp policyeditors {} \; -exec chmod 2770 {} \; || true
find /opt/maceff/policies -type f -exec chgrp policyeditors {} \; -exec chmod 0660 {} \; || true

# Add configured users (POLICY_EDITORS="user1 user2")
if [ -n "${POLICY_EDITORS:-}" ]; then
  for u in ${POLICY_EDITORS}; do
    id -u "$u" >/dev/null 2>&1 && usermod -a -G policyeditors "$u" || echo "warn: $u not present"
  done
fi

# Expose policyctl if present on the /opt/tools bind
if [ -f /opt/tools/bin/policyctl ] && [ ! -e /usr/local/bin/policyctl ]; then
  ln -s /opt/tools/bin/policyctl /usr/local/bin/policyctl
  chmod +x /opt/tools/bin/policyctl || true
fi

# ---- MacEff: propagate container env to SSH sessions (idempotent) ----
if [ -n "${MACEFF_TZ:-}" ]; then
  # Make available to non-interactive SSH sessions via PAM
  sed -i '/^MACEFF_TZ=/d' /etc/environment 2>/dev/null || true
  printf 'MACEFF_TZ=%s\n' "$MACEFF_TZ" >> /etc/environment

  # Also export for interactive login shells
  printf 'export MACEFF_TZ=%q\n' "$MACEFF_TZ" > /etc/profile.d/99-maceff-env.sh
  chmod 0644 /etc/profile.d/99-maceff-env.sh
fi

# ---- Shell TZ bridge (so /bin/date honors MACEFF_TZ in login shells) ----
cat >/etc/profile.d/maceff_tz.sh <<'EOSH'
# Set TZ for interactive shells based on project MACEFF_TZ
[ -n "$MACEFF_TZ" ] && export TZ="$MACEFF_TZ"
EOSH
chmod 0644 /etc/profile.d/maceff_tz.sh

log "sshd starting..."
exec /usr/sbin/sshd -D
