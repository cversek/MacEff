# Container Setup and Operations

The Docker demo environment, compose overrides, the Make targets, host mirroring,
shared-workspace git, and subagent jobs.

Moved out of the README, unchanged. MacEff runs on a host without any of this --
see the README for that path.

## Container Setup: ClaudeMacEff Demo Environment

"Claude MacEff" is a demo implementation of MacEff based on a Docker container running minimal Ubuntu with preinstalled Claude Code and MACF Tools.

## macOS setup: Docker Desktop (recommended), then build & run

> This setup uses **Docker Desktop for Mac** which provides Docker Engine and **Docker Compose v2** (the `docker compose ...` CLI). It works on Apple Silicon and Intel Macs. If you prefer Colima, see the note at the end.

### 1) Install prerequisites
- Install **Docker Desktop for Mac** (from Docker’s website or Homebrew Cask).
- Optional CLI tools:
  ```bash
  brew install jq rsync
  ```

Verify Compose v2 is available:
```bash
docker compose version
```

### 2) (One-time) prepare host snapshot folders for mirroring
```bash
mkdir -p sandbox-home sandbox-shared_workspace
chmod 1777 sandbox-home sandbox-shared_workspace
```

### 3) Provide SSH public keys for in-container users
Put **your own** public keys into `keys/`:
- `keys/admin.pub` → grants SSH to the `admin` user (port 2222)
- `keys/maceff_user001.pub` → grants SSH to the default PA (`maceff_user001`)

The repository ships **no** keys. It cannot: provisioning installs whatever
`.pub` files it finds here as `authorized_keys`, so a key committed upstream
would be an access grant to `admin` — a passwordless sudoer — on every machine
that cloned it. `keys/` is therefore gitignored in full, public halves included.
See `keys/README.md`.

Generate them if you don’t have them yet:
```bash
mkdir -p keys
ssh-keygen -t ed25519 -f keys/admin -N ''
ssh-keygen -t ed25519 -f keys/maceff_user001 -N ''
# both halves stay local — nothing in keys/ is committed
```

### 4) Build the images
```bash
# Build main sandbox image
docker compose build

# Build tiny rsync mirror image used for snapshots
docker build -t maceff-mirror:local -f docker/mirror.Dockerfile .
```

> **If you hit BuildKit/proxy errors:** temporarily force the legacy builder:
> ```bash
> DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 docker compose build
> ```
> Also ensure no stray `HTTP_PROXY`/`HTTPS_PROXY` environment variables are set in your shell.

### 5) Launch the sandbox
```bash
docker compose up -d
# tail logs
docker compose logs -f --tail=120
```

You should see lines creating the PA/SA users and ending with `sshd starting...`.

### 6) Log in (PA and admin)
```bash
# PA (uses keys/maceff_user001.pub)
ssh -i keys/maceff_user001 -p 2222 maceff_user001@localhost

# admin (uses keys/admin.pub)
ssh -i keys/admin -p 2222 admin@localhost
```

### 7) Create a shared project (inside the container, as PA)
```bash
cd /shared_workspace
mkdir demo && cd demo
git init -b main
git config core.sharedRepository group
git config user.name  "PA001 (maceff_user001)"
git config user.email "pa001@container.invalid"
echo "hello from PA" > README.md
git add README.md && git commit -m "feat: initial README"
```

> `/shared_workspace` is group-shared (SGID) so collaborators can work together safely.

### 8) Snapshot container data to the host (read-only export)
First build the mirror image (step 4), then:
```bash
docker compose --profile mirror up --no-deps mirror
# snapshots appear under:
ls -la sandbox-home
ls -la sandbox-shared_workspace
```

This exports the **full** `/home` (including agent private folders) and `/shared_workspace` for inspection/versioning **on the host**. Be careful not to commit secrets from `sandbox-home/` into public repos.

---

### Troubleshooting

**Build fails pulling `docker/dockerfile:…` or tries `127.0.0.1:9090`:**
- Remove any `HTTP_PROXY/HTTPS_PROXY/NO_PROXY` from your shell.
- Rebuild with the legacy builder once:
  ```bash
  DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 docker compose build
  ```

**`docker compose: cannot connect to daemon`:**
- Make sure Docker Desktop is running (launch the Docker app).
- Check your Docker context:
  ```bash
  docker context ls
  docker context show
  docker ps
  ```

**Permission denied while mirroring to `sandbox-*`:**
- Make sure those dirs are writable:
  ```bash
  chmod -R u+rwX sandbox-home sandbox-shared_workspace
  ```

---

### Note: Using Colima instead of Docker Desktop (optional)

If you prefer Colima (lightweight VM) instead of Docker Desktop:

1) Install:
```bash
brew install colima docker docker-compose jq rsync
```

2) Start Colima and select its context:
```bash
colima start --cpu 4 --memory 8 --disk 30
docker context use colima
```

> Edit Colima config if needed:  
> ```colima stop && colima start --edit``` → adjust settings, save, then:  
> ```colima start```

The rest of the steps are the same, but use `docker compose ...` with the Colima context selected.

---

## Local Configuration: docker-compose.override.yml

MacEff uses **docker-compose.override.yml** for environment-specific customization. This file is **gitignored** so each developer can configure their local environment without affecting version control.

### Why Override Files?

**Portability principle**: The base `docker-compose.yml` contains only portable configuration that works on any machine. Environment-specific settings (like local data source mounts, custom ports, or host paths) belong in `docker-compose.override.yml`.

**Benefits**:
- ✅ Base config remains portable across different environments
- ✅ No host-specific paths in version control
- ✅ Easy deployment variations (dev/CI/production)
- ✅ Automatic merging by Docker Compose (no flags needed)

### Creating Your Override File

When you run `./tools/bin/maceff-init`, it creates a template `docker-compose.override.yml` with commented examples:

```yaml
# Local Docker Compose Overrides
# This file is gitignored - customize for your development environment

services:
  maceff-sandbox:
    # Uncomment and customize as needed:
    # volumes:
    #   - "/host/path/to/data:/container/mount/point:ro"
    # ports:
    #   - "8080:8080"
```

### Common Customizations

**Mount a local data directory** (read-only):
```yaml
services:
  maceff-sandbox:
    volumes:
      - "/Users/yourname/data:/data:ro"
```

**Add a development port** (expose container service):
```yaml
services:
  maceff-sandbox:
    ports:
      - "8080:8080"  # host:container
```

**Environment variables** (supplement global.env):
```yaml
services:
  maceff-sandbox:
    environment:
      - CUSTOM_VAR=value
```

### How Docker Compose Merges Files

Docker Compose **automatically merges** `docker-compose.yml` + `docker-compose.override.yml`:

```bash
# This uses both files automatically
docker compose up

# Explicit base-only (CI/testing)
docker compose -f docker-compose.yml up

# Custom override for production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

### Best Practices

1. **Never commit** `docker-compose.override.yml` (already in `.gitignore`)
2. **Document requirements** in README if specific overrides are needed
3. **Use environment variables** in override files for flexibility:
   ```yaml
   volumes:
     - "${DATA_PATH:-/default/path}:/data:ro"
   ```
4. **Test portability** by ensuring base config works without overrides

### Troubleshooting

**Override not taking effect**:
- Verify file is named exactly `docker-compose.override.yml`
- Check YAML syntax (tabs vs spaces, indentation)
- Restart services: `docker compose down && docker compose up`

**Conflicting mounts**:
- Override volumes **merge** with base config, they don't replace
- Use specific mount targets to avoid conflicts

---

## Make quickstart

Common developer workflows are wrapped in `make` targets. These commands assume you’ve already built the images and added your SSH public keys to `keys/` (see macOS setup above).

### Targets
```bash
make build          # docker-compose build
make up             # start services
make logs           # follow logs for the sandbox
make down           # stop services
make mirror         # snapshot volumes -> ./sandbox-*
make mirror-watch   # continuous mirroring (if profile enabled)
make ssh-pa         # SSH into Primary Agent (PA)
make ssh-admin      # SSH into admin
make sa-test        # run a small SubAgent job from the PA
```

### Variables
- `PA`   — PA username (default: `maceff_user001`)
- `SID`  — SubAgent id under the PA (default: `001`)
- `PORT` — SSH port on host (default: `2222`)

### Keys and fallback resolution
The Makefile looks for private keys in this order:
1. `keys/<name>` (e.g. `keys/maceff_user001`, `keys/admin`)  
2. `~/.ssh/id_ed25519_<name>` (e.g. `~/.ssh/id_ed25519_maceff_user001`, `~/.ssh/id_ed25519_admin`)
3. For PAs with numeric suffixes (e.g. `maceff_user001`), it also tries the **base** name without digits: `~/.ssh/id_ed25519_maceff_user`.

You can override explicitly with `PA_KEY` / `ADMIN_KEY`.

### Examples

#### Start, tail logs, and stop
```bash
make build
make up
make logs
make down
```

#### SSH into the PA/admin
```bash
make ssh-pa
make ssh-admin
```

If your private key isn’t under `keys/`, point to it:
```bash
make ssh-pa PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
make ssh-admin ADMIN_KEY=$HOME/.ssh/id_ed25519_admin
```

#### Run a quick SA job from the PA
```bash
# Uses PA=maceff_user001 and SID=001 by default
make sa-test

# Or specify which PA/SID and key to use
make sa-test PA=maceff_user001 SID=001 PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
```

This launches a detached SA process via `sa-exec`, writing output to:
```bash
/home/<PA>/agent/subagents/<SID>/public/logs/make-test.log
```

#### Mirror container data to host snapshots
```bash
make mirror
ls -la sandbox-home
ls -la sandbox-shared_workspace
```

> **Note:** `mirror` exports **full** `/home` (including agent/private) and `/shared_workspace` into `./sandbox-*`. Be careful not to commit secrets from `sandbox-home/` into public repos.

### Troubleshooting
- **“PA_KEY not found”**: Provide `PA_KEY=$HOME/.ssh/id_ed25519_maceff_user` (or put a private key at `keys/maceff_user001`).
- **Cannot connect via SSH**: Ensure the container is up (`make up`) and the correct key matches the **public** key you placed in `keys/`.

## Using Claude Code inside the container

Launch Claude Code as your Primary Agent (PA) inside a shared project folder. This works with **Claude Max account login** (no API key).

### Quick start
```bash
# one-time: bring up the sandbox
make up

# verify CLI install
make claude-doctor PA_KEY=$HOME/.ssh/id_ed25519_maceff_user

# launch Claude in /shared_workspace/demo (default PROJ=demo)
make claude PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
```

On first run in the Claude prompt, type:
```bash
/login
```
Follow the browser flow and sign in with your Claude Max account. Credentials are persisted under the PA’s home (a Docker named volume), so you won’t need to log in again across restarts.

### Choose a different project directory
```bash
make claude PROJ=myproj PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
```
This creates/uses `/shared_workspace/myproj` and launches Claude there.

### Where settings live (inside the container)
- User/global settings: `~/.claude/settings.json`
- Per-project settings: `./.claude/settings.json` within the project directory
- Credentials live under `~/.claude/` and survive container restarts

### Tips
- Commit **project files** from `/shared_workspace/<PROJ>`; avoid committing anything from `/home/<PA>/.claude/`.
- If you see permission errors in shared repos, ensure SGID/group settings are intact (our startup sets `/shared_workspace` group to `agents_all` and enables SGID).

### Troubleshooting
- **“command not found: claude”**: rebuild and restart the container.
  ```bash
  make build
  make up
  make claude-doctor PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
  ```
- **Unable to SSH**: confirm your private key path and that the matching public key is in `keys/<PA>.pub` (mounted read-only into the container).
- **Login loop**: run `make claude-doctor` and check for network/proxy issues; retry `/login`.

---

## Mirror container data to the host (read-only snapshot)

Create export dirs once (host):
```bash
chmod 1777 sandbox-home sandbox-shared_workspace
```

Build the tiny image with rsync:
```bash
docker build -t maceff-mirror:local -f docker/mirror.Dockerfile .
```

One-shot mirror (reads named volumes, writes snapshots into `./sandbox-*`):
```bash
docker run --rm \
  -v maceff_home_all:/src_home:ro \
  -v maceff_shared_workspace:/src_shared:ro \
  -v "$PWD/sandbox-home:/export/home" \
  -v "$PWD/sandbox-shared_workspace:/export/shared" \
  maceff-mirror:local \
  sh -lc 'mkdir -p /export/home /export/shared; \
          rsync -rltD --delete --no-perms --no-owner --no-group /src_home/   /export/home/; \
          rsync -rltD --delete --no-perms --no-owner --no-group /src_shared/ /export/shared/; \
          echo "[mirror] sync complete"'
```

You should see `[mirror] sync complete`, then:
```bash
ls -la sandbox-home
ls -la sandbox-home/maceff_user001
ls -la sandbox-shared_workspace
```

### Notes
- **macOS:** writing to `./sandbox-*` works because we avoid owner/perms changes with `--no-owner --no-group --no-perms`.
- **Linux:** if you want a faithful copy of owners/groups instead, use:
```bash
docker run --rm \
  -v maceff_home_all:/src_home:ro \
  -v "$PWD/sandbox-home:/export/home" \
  maceff-mirror:local \
  sh -lc 'rsync -a --delete --numeric-ids /src_home/ /export/home/'
```

## Using Git in `/shared_workspace` (collaborative, group-shared)

Agents do day-to-day development inside `/shared_workspace`. The directory is group-writable with SGID so new files/dirs inherit the `agents_all` group, enabling collaboration.

**Repo-local identity (recommended):** set a neutral identity per repo to avoid leaking host details.

```bash
# inside the container, as a PA, in a project dir under /shared_workspace/<repo>
git config user.name  "PA001 (maceff_user001)"
git config user.email "pa001@container.invalid"
```

**Initialize a shared repo:**

```bash
git init -b main
git config core.sharedRepository group
# optional: initial content
echo "hello" > README.md
git add README.md
git commit -m "chore: initial commit"
```

**Why it works:** `/shared_workspace` has `agents_all` as its group and SGID set, so new files/dirs keep that group. `core.sharedRepository=group` makes Git objects group-writable.

**Pushing to remotes:**
- Safest: push from **host/CI** after mirroring.
- If pushing from inside the container, prefer **SSH agent forwarding** or **deploy keys** scoped to that repo.

> Note: The `mirror` service currently exports **full `/home`** to `./sandbox-home` (including private folders). Be careful not to commit secrets from the snapshot into public repos.


## Running subagent jobs (`sa-exec`)

Primary Agents (PAs) can launch work as their SubAgent (SA) using a safe runner that only accepts workdirs under:
```bash
/home/maceff_user*/agent/subagents/*
```

SubAgents (SAs) are launched under their own Linux user and write logs under the PA’s agent tree. We provide a thin runner (`sa-exec`) plus a Make target to exercise this from your host.

### Quick start
```bash
# one-time: container up
make up

# run a small SA job under PA=maceff_user001, SID=001
make sa-test PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
```

This launches a detached SA process that writes to:
```bash
/home/<PA>/agent/subagents/<SID>/public/logs/make-test.log
```

To read the log from the host after mirroring:
```bash
make mirror
ls -la sandbox-home/<PA>/agent/subagents/<SID>/public/logs
```

### Customize which SA to run
```bash
# change PA and SID
make sa-test PA=maceff_user001 SID=001 PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
```

### What the target does
- SSH into the PA user inside the container
- Creates the log directory (as the SA) if needed
- Runs a short test command sequence:
  - prints `id`, `whoami`, and `pwd`
  - appends output to `public/logs/make-test.log`

### Troubleshooting
- **“PA key not found”** — Provide an explicit key path:
  ```bash
  make sa-test PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
  ```
- **No log appears** — Re-run and then mirror:
  ```bash
  make sa-test PA_KEY=$HOME/.ssh/id_ed25519_maceff_user
  make mirror
  ```
- **Permission denied** — Ensure your host-side snapshots (`sandbox-*`) are writable:
  ```bash
  chmod 1777 sandbox-home sandbox-shared_workspace
  ```

**Notes**
- Output is appended to `<LOG>`. `sa-exec` starts a detached login shell with `setsid`, so jobs keep running if your PA shell exits.
- The runner **whitelists** PA agent paths; any other `WD` is rejected (`unsafe workdir`).
- Default umask is `027` to keep files private to the SA’s group.
- For multiple parallel delegates, use distinct logs (e.g., `logs/ts-$(date +%s).log`).
