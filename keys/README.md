# `keys/` — SSH public keys for in-container accounts

Put the **public** halves of your own SSH keys here. Nothing in this directory is
tracked by git, and that is deliberate.

## What goes here

Provisioning reads `/keys/<username>.pub` and installs it as that account's
`authorized_keys`. A minimal setup for the reference deployment:

```bash
ssh-keygen -t ed25519 -f keys/admin -N ''
ssh-keygen -t ed25519 -f keys/maceff_user001 -N ''
```

That writes both halves. The private halves stay on your machine; the `.pub`
files are what the container consumes.

## Why nothing here is committed

A committed public key is not documentation. **Provisioning installs it**, so it
is an access grant that ships with the repository — and it lands on accounts that
matter: `admin` is a passwordless sudoer, and the default PA account is where an
agent runs.

This directory previously tracked three `.pub` files, two of them from the same
workstation. Every fresh clone that ran `docker compose up` produced a container
trusting those keys, on machines their owner had never heard of. Nobody
introduced that on purpose; the ignore rule said "keep only `*.pub`", which reads
as sensible right up until you notice what consumes them.

Public keys are not secrets, and none of this was a key compromise. It was an
*authorization* default that nobody chose.

## If you are declaring accounts

Deployments using declarative accounts do not need this directory at all.
`AgentSpec.ssh_keys` accepts either a key **name** resolved against `/keys`, or a
literal `ssh-ed25519 AAAA...` line:

```yaml
agents:
  some_agent:
    ssh_keys:
      - "ssh-ed25519 AAAA... you@example"     # literal, no file needed
      - operator                               # resolves to /keys/operator.pub
```

Prefer literals in a **private** deployment repository. It keeps the keys with
the deployment that uses them, and keeps identifying detail — key comments carry
usernames and machine names — out of any public tree.

## Rotating a key that was published

Deleting a file from this directory does not unpublish it: it remains in git
history and in every existing clone. If a key here was ever committed and you
care about the exposure, the remediation is to **rotate the keypair** and remove
the old public half from every `authorized_keys` that trusts it. Removing the
file only stops the exposure growing.
