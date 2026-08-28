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
      nodejs npm \
      acl jq tini \
      tree \
      tmux rsync \
      libgl1 libxrender1 libxext6 libx11-6 libosmesa6 \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system

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

EXPOSE 22
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python3", "/usr/local/bin/start.py"]