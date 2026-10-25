# Search Service Policy

**Version**: 2.0
**Tier**: CORE
**Category**: Infrastructure
**Status**: ACTIVE
**Updated**: 2026-10-25

---

## Policy Statement

The search service keeps the policy index's embedding model loaded, so a policy recommendation answers in well under a second instead of paying the model's cold start on every call. On an agent with a primal daemon it runs as a declared unit of a daemon (`persistent_layer` 6.4), supervised like any other long-lived process.

## Scope

All MacEff agents and deployments, on hosts and in containers.

---

## CEP Navigation Guide

**1 What It Is**
- What does the search service hold, and how do clients reach it?
- What happens when it isn't running?

**2 How It Runs**
- How does it run under a primal daemon, and how is it declared?
- What happens to the old starts when a unit declares it?
- How does it run where no daemon declares it?

**3 Operating It**
- How do I check it, restart it, or rebuild the index?
- What if it doesn't answer, or answers slowly?

---

## 1 What It Is

**One process per host or container holds the policy retriever warm.** It loads the embedding model (sentence-transformers) and the hybrid policy index (SQLite FTS5 with vector similarity, built by `macf_tools policy build_index`), and answers queries over TCP on `127.0.0.1:9001`.

- **Clients:** `macf.search_service.client.query_search_service()` sends one query and waits up to its timeout (0.5 s by default; `macf_tools policy recommend` allows 1 s). `get_policy_injection()` formats the result for a hook.
- **When it isn't running, nothing breaks.** A client that can't connect, or times out, gets an error result, and the caller falls back to searching directly, paying the cold start (several seconds) for that call.
- **It is shared, not per agent.** The port is fixed, so one copy serves everything on the host or in the container. The index it serves is the framework's policy index, the same for every agent.

## 2 How It Runs

### 2.1 Under a primal daemon (the normal case)

**Declare it as a service unit of one daemon on the host or in the container** (`persistent_layer` 6.4, 10.2). On a host, that is the host agent's own daemon. In a container, it is the daemon of the account the container's start step used to start it as, normally the first agent's.

```yaml
        - name: search
          kind: service
          command: ["/opt/maceff-venv/bin/python", "-m", "macf.search_service.daemon", "--unit"]
          account: <that agent's login>
          restart: always
          liveness_interval_s: 60
          memory_limit_mb: 2048
          environment:
            HOME: "{agent_home}"
```

- **`--unit` never forks.** It stays in the foreground as the daemon's child, so the daemon can stop it, restart it and watch its memory. `--daemon` (a double fork) and `--unit` refuse each other.
- **It beats from the first second.** It sends its liveness before anything heavy, about once a second while the model loads (up to ten minutes, so a hung load shows as overdue), and then on every pass of its serve loop. A slow cold start is never failed for missing liveness.
- **It binds the port before loading, and listens after.** A port already taken fails in seconds, with exit 1 and a message that says to stop the other copy (`macf_tools search-service stop`). A client that connects during the load is refused at once instead of waiting in a queue.
- **SIGTERM ends it cleanly,** during the load or while serving.
- **The memory limit comes from measurement:** a running copy held 1,273 MB resident, the same as its peak, after a day and a half. 2048 MB leaves about 60 % headroom; the limit is watched, not enforced (`persistent_layer` 10.2).

**When a unit declares it, nothing else starts it.** The container's start step logs one line naming the account and unit that run it, and starts none itself. It warns if that unit's command lacks `--unit`. `macf_tools search-service start` refuses, naming the unit and pointing to `macf_tools pd status`, which is where to look. The check reads this agent's own declaration and every rendered declaration in the container (`/etc/maceff/pd/*`), and matches a unit whose command runs `macf.search_service`.

### 2.2 Where no daemon declares it

Where no daemon declares a search unit, the old starts work as before. A container's start step runs `python -m macf.search_service.daemon --daemon` once, as the first agent, and `macf_tools search-service start` starts it by hand. Nothing supervises such a copy: if it dies, nothing restarts it, and the clients fall back to direct search until someone starts it again. Declaring it as a unit is how to fix that.

## 3 Operating It

- **Check it:** `macf_tools search-service status`. Under a unit, the pid file may not be where an agent shell looks, since a unit gets only its declared environment, so `status` also probes the port and says when only the port answers. `macf_tools pd status`, as the account whose daemon declares it, shows the unit's state.
- **Restart it:** under a unit, the daemon restarts it by its policy after a failure. To restart it on purpose, `macf_tools search-service stop` sends it SIGTERM, and a unit with `restart: always` comes back a second later. Where no unit declares it, `macf_tools search-service stop`, then `start`.
- **Rebuild the index** after policies change: `macf_tools policy build_index`. Then restart the service as above, so the warm copy serves the rebuilt index rather than whatever it loaded at its start.
- **It doesn't answer:** run `status`. A unit stuck in `starting` hasn't sent its first beat; read its `pd_unit_state` events (`macf_tools events query --event pd_unit_state -v`). A port held by another copy makes a unit fail at once with exit 1.
- **It answers slowly:** a first query after a restart may wait for the model to finish loading. Timing `macf_tools policy recommend "<question>"` shows whether answers come from the warm service (well under a second) or the cold fallback (several seconds).

---

## Wiki-Links

<!-- NORMATIVE node. Links are what this policy governs: the warm policy search service,
     and its supervision as a daemon unit. -->

[[primal_daemon]] [[search]] [[tooling]] [[persistent_layer]]
