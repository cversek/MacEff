# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
SHELL ["/bin/bash","-lc"]

RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget gnupg sudo openssh-server \
      git vim less build-essential python3 python3-venv python3-pip \
      nodejs npm \
      acl jq tini \
      tree \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Copy framework templates
COPY templates/ /opt/maceff/templates/
RUN chmod 644 /opt/maceff/templates/*.md

# Copy base policy set with manifest
COPY policies/base/ /opt/maceff/policies/base/
RUN chmod 644 /opt/maceff/policies/base/*.md /opt/maceff/policies/base/manifest.json

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

EXPOSE 22
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["/usr/local/bin/start.sh"]