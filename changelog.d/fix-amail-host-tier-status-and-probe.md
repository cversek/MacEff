### Fixed

- amail: `amail status` sends the agent's claim, so on a uid the host tier declares shared the broker answers with that agent's quarantine and pending counts and its rate-limit budget instead of refusing for want of a claim.
- amail: a connection that closes without sending a request (the client's readiness probe) is no longer audited as a refused submission and a broken pipe. On macOS the kernel stops answering for a closed peer, so every `amail` command wrote two error records.
- docs: `docs/AMAIL_DEPLOYMENT.md` says that `account` also fixes an agent's home, how agents with separate homes on one login are declared, and which keys a host agent's `amail.json` needs.
