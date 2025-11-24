# Docker Container Operations

**Breadcrumb**: s_agent-2e/c_178/g_9b828c9/p_none/t_1763935929
**Type**: Technology Standards (Docker/Containers)
**Scope**: DevOps engineers, container operations specialists
**Status**: ACTIVE
**Updated**: 2025-11-23

---

## Purpose

Docker container operations policy establishes best practices for building, running, and maintaining containerized multi-agent systems. These standards ensure portable, secure, and maintainable container deployments that scale across development, testing, and production environments.

**Core Insight**: Container operations isn't ceremony—it's **production-grade infrastructure**. Sound practices prevent silent failures, enable reproducibility, and protect data integrity across platform boundaries.

---

## CEP Navigation Guide

**1 Container Fundamentals**
- What are Docker containers?
- Why containerize multi-agent systems?
- What problems do containers solve?
- Platform considerations (ARM64 vs x86_64)?

**1.1 Architecture Pattern**
- What is the container architecture?
- How do named volumes work?
- What are bind mounts vs named volumes?
- When to use each mount type?

**1.2 Networking & Isolation**
- How do containers communicate?
- What is container networking?
- Port mapping best practices?
- Service discovery patterns?

**2 Building Images**
- What makes a good Dockerfile?
- Layer optimization strategies?
- Multi-stage builds and why they matter?
- Dependency pinning and reproducibility?

**2.1 Multi-Stage Build Pattern**
- Why use multi-stage builds?
- How to structure build and runtime stages?
- Size optimization techniques?
- When to split vs combine stages?

**2.2 Security Considerations**
- Container security best practices?
- Avoiding secrets in images?
- Filesystem permissions and ownership?
- Vulnerability scanning?

**3 Volume Management**
- Named volumes vs bind mounts?
- Volume persistence across container restarts?
- Data migration and backup strategies?
- Mirroring container data to host?

**3.1 Backup & Recovery**
- How to backup container volumes?
- Export/import patterns?
- Data integrity verification?
- Recovery procedures?

**4 Runtime Operations**
- Container startup sequence?
- Health checks and monitoring?
- Graceful shutdown patterns?
- Resource limits and constraints?

**4.1 Platform Awareness**
- ARM64 vs x86_64 differences?
- Architecture-specific base images?
- Cross-platform compatibility?
- Testing on target platforms?

**5 Development Workflow**
- Live code mounting for development?
- Rebuild vs restart decisions?
- Local testing patterns?
- Container log inspection?

**5.1 Debugging Containers**
- SSH access and interactive shells?
- Log aggregation patterns?
- Performance profiling tools?
- Network troubleshooting?

**6 Integration with MacEff**
- start.py orchestration role?
- Config mounting and configuration?
- Volume strategy for MacEff agents?
- Production considerations?

=== CEP_NAV_BOUNDARY ===

---

## 1 Container Fundamentals

### 1.1 Architecture Pattern

Multi-agent container systems use declarative architecture patterns for reproducibility and scalability:

**Key Components**:
- **docker-compose.yml**: Declarative service definitions
- **Dockerfile**: Image build specifications
- **Named volumes**: Persistent data storage
- **Bind mounts**: Development code synchronization
- **configs**: Injected configuration files (YAML, JSON)

**Named Volumes Strategy**:

Named volumes provide durable storage independent of container lifecycle:

```yaml
volumes:
  home_all:              # Shared home directories
    driver: local
  shared_workspace:      # Collaborative workspace
    driver: local
  maceff_venv:          # Python virtual environment
    driver: local
  sshd_keys:            # SSH authentication keys
    driver: local
```

**Volume Mounting Best Practices**:

```yaml
# Named volume for persistent data
services:
  agent:
    volumes:
      - home_all:/home/agent
      - shared_workspace:/workspace

# Bind mount for development code
services:
  dev_agent:
    volumes:
      - ./src:/opt/tools:ro         # Read-only for safety
      - ./config:/etc/agent:ro
```

### 1.2 Networking & Isolation

**Service Communication**:

Docker Compose provides automatic DNS service discovery using service names:

```yaml
services:
  pa_agent:
    networks:
      - agent_network
    ports:
      - "2222:22"              # SSH port mapping

  sa_agent:
    networks:
      - agent_network
    depends_on:
      - pa_agent

networks:
  agent_network:
    driver: bridge
```

**Port Mapping Strategy**:
- Expose SSH (22) on different host ports per agent
- Keep internal service ports private
- Document port mappings clearly
- Avoid conflicts with host services

---

## 2 Building Images

### 2.1 Multi-Stage Build Pattern

Multi-stage builds separate build-time dependencies from runtime, dramatically reducing image size:

**Structure**:

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y \
    build-essential \
    git

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy only runtime dependencies from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY src/ ./src/
CMD ["python", "src/main.py"]
```

**Benefits**:
- Builder stage dropped from final image
- Only runtime dependencies included
- Smaller image size = faster pulls and deploys
- Secrets not leaked into final layer

**Pinning Dependencies**:

Always pin dependency versions for reproducibility:

```dockerfile
# ❌ Unpinned (fragile)
RUN pip install flask pandas numpy

# ✅ Pinned (reproducible)
RUN pip install flask==2.3.2 pandas==2.0.3 numpy==1.24.3
```

### 2.2 Security Considerations

**Secrets Management**:

Never include secrets in images:

```dockerfile
# ❌ DANGEROUS
RUN echo $API_KEY > /app/config.txt

# ✅ SAFE - Use runtime mount
# Secrets provided at runtime via:
# - Environment variables (docker run -e)
# - Volume mounts (docker run -v)
# - Secret management services
```

**Filesystem Permissions**:

```dockerfile
# Create app user (avoid running as root)
RUN useradd -m -u 1000 appuser
USER appuser

# Set appropriate permissions
RUN chmod 755 /app && chmod 644 /app/config.json
```

**Base Image Selection**:

```dockerfile
# ✅ Minimal, security-focused
FROM python:3.11-slim
FROM alpine:3.18

# ❌ Large, unnecessary dependencies
FROM python:3.11            # 1GB+
FROM ubuntu:22.04           # 77MB
```

---

## 3 Volume Management

### 3.1 Volume Persistence & Backup

**Container Volume Lifecycle**:

Named volumes persist across container restarts:

```bash
# Create named volume
docker volume create agent_home

# Use in container
docker run -v agent_home:/home image:latest

# Data persists across container destruction/recreation
docker rm container_id
docker run -v agent_home:/home image:latest  # Data still there
```

**Data Export Pattern**:

Mirror container volumes to host for backup:

```bash
# Export data from named volume to host directory
docker run --rm \
  -v agent_home:/data \
  -v "$(pwd)/backups:/backup" \
  alpine:latest \
  tar czf /backup/agent_home_backup.tar.gz /data

# Import from backup
docker run --rm \
  -v agent_home:/data \
  -v "$(pwd)/backups:/backup" \
  alpine:latest \
  tar xzf /backup/agent_home_backup.tar.gz -C /
```

**Verify Data Integrity**:

```bash
# Before destructive operations
docker run --rm -v agent_home:/data alpine ls -la /data
docker run --rm -v agent_home:/data alpine du -sh /data
```

---

## 4 Runtime Operations

### 4.1 Platform Awareness

**Architecture Detection & Compatibility**:

```dockerfile
# Detect build platform
FROM --platform=$BUILDPLATFORM python:3.11 AS builder

# Specify target platform for final image
FROM --platform=$TARGETPLATFORM python:3.11-slim

# No architecture-specific compilation - Python is portable
```

**Base Image Strategy**:

```dockerfile
# ✅ Works on both ARM64 (Mac/Raspberry Pi) and x86_64 (Linux servers)
FROM python:3.11-slim        # Multi-arch by default

# ✅ Explicit multi-arch declaration
FROM --platform=linux/amd64 ubuntu:22.04
FROM --platform=linux/arm64 ubuntu:22.04

# ❌ x86_64 only (breaks on Mac M1/M2)
FROM ubuntu:22.04
```

**Health Checks**:

```yaml
services:
  agent:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

**Graceful Shutdown**:

```dockerfile
# Proper signal handling
FROM python:3.11-slim
RUN apt-get install -y dumb-init

# Use dumb-init to handle signals properly
ENTRYPOINT ["dumb-init", "--"]
CMD ["python", "agent.py"]
```

---

## 5 Development Workflow

### 5.1 Debugging & Troubleshooting

**Interactive Shell Access**:

```bash
# Execute shell in running container
docker exec -it container_name /bin/bash

# Inspect filesystem
docker exec container_name ls -la /app
docker exec container_name cat /etc/agent/config.yaml
```

**Log Inspection**:

```bash
# View container logs
docker logs container_name

# Follow logs in real-time
docker logs -f container_name

# View last N lines
docker logs --tail 100 container_name

# View logs with timestamps
docker logs -t container_name
```

**Performance Monitoring**:

```bash
# Resource usage (CPU, memory)
docker stats container_name

# Process list in container
docker top container_name

# Port mapping verification
docker port container_name
```

---

## 6 Integration with MacEff

### 6.1 start.py Orchestration

MacEff's `start.py` script orchestrates container initialization:

**Key Responsibilities**:
- Reads agent declarations from configs (agents.yaml, projects.yaml)
- Creates system users and directories
- Installs SSH keys for agent access
- Configures consciousness infrastructure (hooks, state)
- Mounts volumes and configuration files
- Bootstraps agent-specific environments

**Rebuild vs Restart Distinction**:

```bash
# REBUILD required when:
# - Dockerfile changes
# - Dependencies change (requirements.txt)
# - start.py changes
# - Base image updated
docker-compose build --no-cache

# RESTART sufficient when:
# - macf_tools Python code changes (bind-mounted)
# - Framework overlay changes (bind-mounted)
# - Configuration only (mounted via configs)
docker-compose restart

# FULL RESTART when unsure
docker-compose down
docker-compose up -d
```

**Volume Strategy in MacEff**:

```yaml
# Named volumes - persistent data
volumes:
  home_all: {}                      # Agent home directories
  shared_workspace: {}              # Collaborative workspace

# Bind mounts - development code
volumes:
  - ./tools:/opt/tools              # macf_tools (live updates)
  - ./framework/policies:/opt/policies  # Policy sync

# Configs - read-only files
configs:
  agents_config:
    file: ./framework/agents.yaml
  projects_config:
    file: ./framework/projects.yaml
```

---

## Integration with Other Policies

**Related Policies**:
- `development/workspace_discipline.md` - Development practices
- `development/testing.md` - Test running in containers
- `base/core_principles.md` - Operational principles

---

## Anti-Patterns

**Container Anti-Patterns to Avoid**:

1. **Running as root**: Security risk, privilege escalation vulnerability
2. **Unpinned dependencies**: Non-reproducible builds
3. **Large base images**: Slow builds, large attack surface
4. **Secrets in images**: Leaked in layer history, non-revocable
5. **Single-purpose containers**: Violates separation of concerns
6. **No health checks**: Zombies and silent failures
7. **Hardcoded configuration**: Reduces portability and flexibility
8. **Massive layers**: Slow builds, wasted storage

---

## Evolution & Feedback

This policy evolves based on operational experience. Discovered improvements or edge cases should be documented as friction points, validated through testing, and integrated back into this policy for framework-wide benefit.

**Feedback Channels**:
- Document friction points in `friction_points/friction_points.md`
- Reference this policy in DevOpsEng specialization work
- Update as MacEff deployment patterns mature
