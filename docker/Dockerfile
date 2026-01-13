# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
SHELL ["/bin/bash","-lc"]

RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg sudo openssh-server \
      git git-lfs vim less build-essential python3 python3-venv python3-pip \
      python3-yaml \
      nodejs npm \
      acl jq tini \
      tree \
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

RUN npm install -g @anthropic-ai/claude-code
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