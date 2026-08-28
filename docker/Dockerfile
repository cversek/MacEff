# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
SHELL ["/bin/bash","-lc"]

# tmux and rsync are load-bearing, not conveniences: macf.supervisor's
# --tmux-session is how a detached, joinable agent session runs at all (agents'
# own harness functions call tmux directly), and every maceff_tools/*-sync
# script invokes rsync. Both had been hand-installed into a running container,
# which worked right up until a rebuild removed them and left two agents unable
# to start, with nothing recording what had gone missing.
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg sudo openssh-server \
      git git-lfs vim less build-essential python3 python3-venv python3-pip \
      python3-yaml \
      acl jq tini \
      tree \
      tmux rsync \
      libgl1 libxrender1 libxext6 libx11-6 libosmesa6 \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system

# Node.js from NodeSource, PINNED to a major line.
#
# Ubuntu's `nodejs` package was v18. Claude Code declares `engines: node >= 22`,
# and npm treats an unmet engine as a WARNING -- it installs anyway, the build
# succeeds, and nothing reports that the runtime is unsupported. That is the
# quiet failure this image kept shipping: a working-looking install on an engine
# its author does not support.
#
# It genuinely ran (--help and `mcp list` both returned 0 on 18), which is
# exactly why it survived: "it works" is not "it is supported", and the gap only
# becomes visible when some feature reaches for a runtime API that is not there.
#
# Asserted rather than assumed, because an apt/NodeSource mix can leave two node
# binaries and PATH decides which one anything actually gets.
ARG NODE_MAJOR=22
RUN set -eux; \
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    rm -rf /var/lib/apt/lists/*; \
    node --version; \
    test "$(node --version | cut -d. -f1)" = "v${NODE_MAJOR}" \
        || { echo "BUILD FAILED: node $(node --version) is not v${NODE_MAJOR}"; exit 1; }; \
    echo "node ${NODE_MAJOR} OK ($(node --version), npm $(npm --version))"

# Install pydantic v2 via pip (code requires field_validator from v2)
RUN pip3 install --break-system-packages pydantic>=2.0

# GitHub CLI (gh)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
 && apt-get update \
 && apt-get install -y gh \
 && rm -rf /var/lib/apt/lists/*

# Python symlink for hooks compatibility (hooks use #!/usr/bin/env python)
RUN ln -s /usr/bin/python3 /usr/bin/python

# Claude Code, PINNED and ASSERTED.
#
# This was `npm install -g @anthropic-ai/claude-code` with no version. Two
# failures compounded: the version installed was whatever npm served the day the
# layer was first built, and because the layer then CACHES, a rebuild does not
# update it. So the image was both undeclared and frozen -- deployments drifted
# apart silently (one container sat 30 releases behind another, and nothing in
# either image said which version it carried or why).
#
# Pinning fixes both. The version is now a stated fact, bumping it is a one-line
# change that correctly invalidates the layer, and the assertion means a silent
# substitution fails the build instead of shipping.
ARG CLAUDE_CODE_VERSION=2.1.250
RUN set -eux; \
    npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    got="$(claude --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; \
    test "$got" = "${CLAUDE_CODE_VERSION}" \
        || { echo "BUILD FAILED: claude ${got} != pinned ${CLAUDE_CODE_VERSION}"; exit 1; }; \
    echo "claude code ${CLAUDE_CODE_VERSION} OK"
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# NOTE: Framework content (policies, templates, agent_defs) comes from bind mount
# at /opt/maceff/framework/ in dev mode, or baked via COPY in deployment Dockerfile

# Copy skeleton bashrc for new users (includes venv activation)
COPY docker/skel/.bashrc /etc/skel/.bashrc
RUN chmod 644 /etc/skel/.bashrc

# admin (sudoer)
RUN useradd -m -s /bin/bash admin \
 && echo "admin ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/90-admin \
 && chmod 0440 /etc/sudoers.d/90-admin

# SSH hardening
RUN mkdir -p /var/run/sshd /etc/ssh/sshd_config.d \
 && printf '%s\n' \
    'PasswordAuthentication no' \
    'PermitRootLogin no' \
    'X11Forwarding no' \
    'ClientAliveInterval 60' \
    'ClientAliveCountMax 10' \
  > /etc/ssh/sshd_config.d/10-container.conf

# Runner used for parallel SA jobs (scoped via sudoers)
# sa-exec runner
COPY docker/sa-exec /usr/local/bin/sa-exec
RUN chmod 0755 /usr/local/bin/sa-exec

COPY docker/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# NOTE: start.py moved to derived images (volatile file in volatile layer)
# Each deployment's Dockerfile should COPY start.py after this base layer
# This optimization prevents base image rebuilds when start.py changes

# ---------------------------------------------------------------------------
# amail infrastructure — the runtime, its uids, and its stores
# ---------------------------------------------------------------------------
# THIS BLOCK EXISTS BECAUSE NONE OF IT EXISTED. The first deployment to run
# amail had its entire runtime, both service uids, every store and both configs
# living ONLY in a running container's writable layer, placed by hand. Nothing
# in any Dockerfile, compose file or script produced any of it. `docker compose
# down && up` would have destroyed a working mail path, its audit ledger and its
# conservation records, and the first symptom was an inbound outage that lasted
# a day because a hand-copied file had no execute bit.
#
# It lives in the BASE image so a second deployment consumes it by declaring
# configuration rather than by copying ten files, because copies drift and that
# drift has already bitten once.
#
# The runtime is deployment-agnostic by construction: every path and endpoint
# comes from AMAIL_BROKER_CONFIG / AMAIL_INBOUND_CONFIG or an env default, and
# the sources carry no deployment identifiers. That is what makes it base-image
# material rather than a deployment's business.

# TWO SERVICE UIDS, FIXED. Identity separation is the PRECONDITION for every
# owner-scoped guarantee this subsystem makes -- a credential that "only the
# broker can read" is an unstatable rule without an owner to match. Fixed ids
# so ownership survives a rebuild: state on a volume outlives the image that
# created it, and uid drift would silently orphan every stored file.
#   amail_broker  authorizes, holds the submission credential, owns the ledgers
#   amail_ingest  accepts inbound and writes the spool; may NOT read the above
RUN set -eux; \
    groupadd -g 998 amail_broker; \
    useradd  -u 998 -g 998 -M -N -s /usr/sbin/nologin \
             -d /var/lib/amail_broker amail_broker; \
    groupadd -g 999 amail_ingest; \
    useradd  -u 999 -g 999 -M -N -s /usr/sbin/nologin \
             -d /var/lib/amail_ingest amail_ingest; \
    id amail_broker; id amail_ingest

# THE STORES, WITH THE MODES AS PROVISIONING RATHER THAN AS HAND-REPAIR.
# dispositions/ and ratelimit/ are deliberately AGENT-READABLE: a sender reads
# the fate of its own mail and its own remaining budget with no broker call, so
# the files are 0644 and the directories MUST be traversable. Creating them 0700
# makes those file modes decorative -- done by hand once, caught a minute later,
# and the reason this is a build step now.
# quarantine/ is broker-only: it holds refused inbound, which is attacker-
# supplied bytes that no agent should be able to read by accident.
RUN set -eux; \
    install -d -o amail_broker -g amail_broker -m 0755 /var/lib/amail_broker; \
    install -d -o amail_broker -g amail_broker -m 0755 /var/lib/amail_broker/dispositions; \
    install -d -o amail_broker -g amail_broker -m 0755 /var/lib/amail_broker/ratelimit; \
    install -d -o amail_broker -g amail_broker -m 0700 /var/lib/amail_broker/quarantine; \
    install -d -o amail_broker -g amail_broker -m 0755 /var/lib/amail_broker/received; \
    install -d -o amail_ingest -g amail_ingest  -m 0755 /var/lib/amail_ingest; \
    install -d -o amail_ingest -g amail_broker  -m 2770 /var/lib/amail_ingest/spool; \
    install -d -o root -g root -m 0755 /etc/amail; \
    install -d -o root -g root -m 0700 /run/maceff-secrets; \
    [ "$(stat -c %U:%a /var/lib/amail_broker/quarantine)" = "amail_broker:700" ]; \
    [ "$(stat -c %U:%a /var/lib/amail_broker/dispositions)" = "amail_broker:755" ]; \
    [ "$(stat -c %a  /run/maceff-secrets)" = "700" ]

# THE AMAIL DAEMONS ARE NOT COPIED HERE. They are package modules
# (macf.amail.daemons.*), so they arrive with the macf install and a deployment
# that mounts the package editable picks up a change on restart instead of on
# rebuild. As image content they were build-tier, and every derived image
# inherits a base rebuild -- a one-line fix to a mail daemon cost a full
# toolchain rebuild in images that have nothing to do with mail.
#
# /opt/amail_ingest remains as the deployment's drop point for its own runtime
# configuration (receiver.env and any transport it supplies).
RUN install -d -o root -g root -m 0755 /opt/amail_ingest

EXPOSE 22
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python3", "/usr/local/bin/start.py"]