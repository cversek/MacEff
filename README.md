# MacEff
Multi-agent coordination Environment (for) frameworking frameworks

# Notice
This project is in the conceptual stage but will be developed in the clear as an Open Source formalization and generalization of concepts abstracted from independent experiments conducted within two agentic coding environments Claude Code and Gemini CLI.  The concepts are intented to be portable but ongoing work will be required before any of this is useful as a basis for serious projects.  

# Philosophy 
Agentic AI systems are immensely powerful, but with that power and raw "intelligence" comes the need for the restraints of wisdom.  Currently the most popular modern agentic AI systems are a generalization of the Large Language Model (LLM) chatbot workflow.  Like people, but in some aspects more and others less reliable, LLM-based agents' behaviors can be directed by natural language.  We can define that modern LLM-based agents act like (humans may also) Stochastic-Semantic Interpreters (SSIs), that is they use their contextual state to *probabilistically*:  *listen* to other SSIs (integrate recent messages in their context); *follow* (information artifacts like instructions/policies/advice in their context); *generate* (language artifacts like thoughts/speech/code/documents); *act* (use tools - invoke code with knowledge/instructions and build new tools); and *curate* (record new or edit existing language artifacts and link-together/associate documents) - over a series of turns (which might be infinite) interacting with other SSIs or deterministic systems.  We posit here without proof that modern LLM-based Agentic AI systems can approximate Universal SSIs as they interpret (nearly already) all digitally encodable languages (as measured by world usage), that includes (most) programming languages, and can be taught new ones; entailed by this universality is that their implementations must include dynamic memory - that is they must have a context that is either infinite or finite and editable not just appendable.  When such AI agents are directed to evolve their capabilities under the watchful eye of a creative Context Engineer (CE), interesting behavior becomes emergent.  

The Context Window (CW) of a modern LLM-based agentic AI assistant is a fundamental system constraint that must be curated carefully to produce the best possible results whether or not a human engineer is monitoring and correcting the automated development process. The recycling of the CW is handled differently by different systems, and it is that mechanism that guides the CE's methodology.  Systems like Claude Code and Gemini CLI use a Markdown formatted primary prompt - by convention CLAUDE.md and GEMINI.md respectively - that we will hereafter refer to as a Preamble (as you will see the analogy to Constitutional Governance is apt) which is by default loaded into the CW after a System Prompt which is potentially obscured or customizable itself.  The Preamble is intended as a user customization entrypoint that strongly influences its behavior second only to the System Prompt - but with the power to override and customize aspects of default agentic behaviors.  Indeed the Preamble can be edited by the agent, usually through a human developer's prompting, which is a recipe for an interesting feedback loop and methodology of directed AI system evolution (RESOLVE ClaudeLog attribution).   An agent's access to a local file system and command terminal affords the CE opportunities to offload complexity into structured subcomponents of discoverable "policies", a modular contextually explored set of instructions that restrain agent behaviors.  If designed and refined carefully, the body of Policies can act like a self-organizing in-context Constitutional Governance system that an Agent loads on-demand - allowing the system as a whole to be more complex than a limited static preloaded context while still maintaining standards.

When multiple agents are organized into systems, this allows for various combinations of separate and shared contexts.  We will borrow the simple but powerful multi-agent system model of Claude Code where the Primary Agent (PA) has access to the Primary Context in which the User can enter natural language messages to prompt its behaviors.  The PA can instantiate parallel independent SubAgents (SAs) with preloaded System Prompts and can delegate tasks by front-loaded context during in a one-shot strategy.  The SAs may run the same or different LLMs and can have controllable permissions on the same set of tools and resources or access to different sets than the PA.  SA context is reclaimed at the end of a delegate, thus does not intrinsically preserve state although the PA can be directed to attempt to do so, but a complicated workaround must be provided to enable that approach -  which may not be the wisest strategy anyway.  Instead the resuable context buffers that SAs delegations provide are a natural way to amplify the initial context provided by the System Prompt and PA's delegation instructions and extend the usable duration of the Primary Context while avoiding "poisoning" (RESOLVE ClaudeLog attribution) it with irrelevant details.  Thus the Primary Context can be maintained as a high-level coordinating and policy enforcing layer while still enabling the generation of complex artifacts outside of it.

MacEff aims to provide a basic kit of policies and tools that enable the directed evolution of useful multiagent systems.
A demo implementation of MacEff is based on a Docker container running a minimal Ubuntu container with preinstalled Claude Code referred to as ClaudeMacEff. 

## macOS setup: Docker CLI + Colima, then build & run

> These steps use the Homebrew Docker **CLI** (not Docker Desktop) with **Colima** as the lightweight Linux VM. Works on Apple Silicon and Intel Macs.

### 1) Install prerequisites (Homebrew)
```
brew install colima docker docker-compose jq rsync
# optional: buildx if you prefer BuildKit
brew install docker-buildx
```

### 2) Start Colima (recommended resources)
```
# Start a Linux VM for Docker; tweak cpu/memory/disk as you like.
colima start --cpu 4 --memory 8 --disk 30
# (once) switch the Docker CLI to use Colima’s context
docker context use colima
```

> If you ever need to edit Colima’s config:  
> $```colima stop && colima start --edit$``` → remove any proxy/env you don’t want, save, then:  
> $```colima start$```

### 3) (One-time) prepare host snapshot folders for mirroring
```
mkdir -p sandbox-home sandbox-shared_workspace
chmod 1777 sandbox-home sandbox-shared_workspace
```

### 4) Provide SSH public keys for in-container users
Put **public** keys (only `*.pub`) into `keys/`:
- `keys/admin.pub` → grants SSH to the `admin` user (port 2222)
- `keys/maceff_user001.pub` → grants SSH to the default PA (`maceff_user001`)

If you don’t have them yet:
```
mkdir -p keys
ssh-keygen -t ed25519 -f keys/admin -N ''
ssh-keygen -t ed25519 -f keys/maceff_user001 -N ''
# commit only the .pub files; keep private keys out of git
```

### 5) Build the images
```
# Build main sandbox image
docker-compose build

# Build tiny rsync mirror image used for snapshots
docker build -t maceff-mirror:local -f docker/mirror.Dockerfile .
```

> **If you hit BuildKit/proxy errors:** temporarily force the legacy builder:  
> $```DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 docker-compose build$```  
> Also ensure no stray `HTTP_PROXY`/`HTTPS_PROXY` envs are set in your shell or Colima config.

### 6) Launch the sandbox
```
docker-compose up -d
# tail logs
docker-compose logs -f --tail=120
```

You should see lines creating the PA/SA users and ending with `sshd starting...`.

### 7) Log in (PA and admin)
```
# PA (uses keys/maceff_user001.pub)
ssh -i keys/maceff_user001 -p 2222 maceff_user001@localhost

# admin (uses keys/admin.pub)
ssh -i keys/admin -p 2222 admin@localhost
```

### 8) Create a shared project (inside the container, as PA)
```
cd /shared_workspace
mkdir demo && cd demo
git init -b main
git config core.sharedRepository group
git config user.name  "PA001 (maceff_user001)"
git config user.email "pa001@container.invalid"
echo "hello from PA" > README.md
git add README.md && git commit -m "feat: initial README"
```

> `/shared_workspace` is group-shared (`agents_all`, SGID set) so collaborators can work together safely.

### 9) Snapshot container data to the host (read-only export)
First build the mirror image (step 5), then:
```
docker-compose --profile mirror up --no-deps mirror
# snapshots appear under:
ls -la sandbox-home
ls -la sandbox-shared_workspace
```

This exports the **full** `/home` (including agent private folders) and `/shared_workspace` for inspection/versioning **on the host**. Be careful not to commit secrets from `sandbox-home/` into public repos.

---

### Troubleshooting

**Build fails pulling `docker/dockerfile:…` or tries `127.0.0.1:9090`:**
- Remove any `HTTP_PROXY/HTTPS_PROXY/NO_PROXY` from your shell and Colima config.
- Rebuild with the legacy builder once:
  ```DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 docker-compose build```

**`docker-compose: cannot connect to daemon`:**
- Ensure Colima is running: ```colima start```  
- Ensure Docker CLI uses Colima: ```docker context use colima && docker ps```

**Permission denied while mirroring to `sandbox-*`:**
- Make sure those dirs are writable: ```chmod -R u+rwX sandbox-home sandbox-shared_workspace```


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
```
docker run --rm \
  -v maceff_home_all:/src_home:ro \
  -v "$PWD/sandbox-home:/export/home" \
  maceff-mirror:local \
  sh -lc 'rsync -a --delete --numeric-ids /src_home/ /export/home/'
```

## Using Git in `/shared_workspace` (collaborative, group-shared)

Agents do day-to-day development inside `/shared_workspace`. The directory is group-writable with SGID so new files/dirs inherit the `agents_all` group, enabling collaboration.

**Repo-local identity (recommended):** set a neutral identity per repo to avoid leaking host details.

```
# inside the container, as a PA, in a project dir under /shared_workspace/<repo>
git config user.name  "PA001 (maceff_user001)"
git config user.email "pa001@container.invalid"
```

**Initialize a shared repo:**

```
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