# MIS-0011: Loopback services and caller identity, an amendment to MIS-0002

**Number**: 0011
**Type**: Amendment
**Status**: Draft
**Authors**: the head maintainer
**Secretary**: none
**Created**: 2026-11-22
**Amends**: MIS-0002: R80 (pd_MUST-NOT_listen_on_network); adds R202 (data_service_MUST-NOT_listen_on_tcp), R203 (data_service_socket_MUST_sit_in_private_directory), R204 (data_service_MUST_check_peer_account)
**Resolution**: none

---

## 1 Amendment

MIS-0002 is edited in place, and each changed or added requirement there carries a note that links this spec. The old and new text of each one:

**R80, changed.**
> Old: A primal daemon MUST NOT listen on a network port itself, so only its broker unit listens, and only as R170 allows. (pd_MUST-NOT_listen_on_network)
>
> New: A primal daemon MUST NOT listen on a network port itself, a loopback port included, so only its broker unit listens, and only as R170 allows. (pd_MUST-NOT_listen_on_network)

The slug is unchanged. The test gains `macf/tests/test_primal_daemon.py::test_no_loopback_listener`.

**New requirements, R202 to R204.** They have no old text.
> R202: Except the broker of R170, a service that reads an agent's data or acts for the agent MUST NOT listen on a TCP port, loopback included. (data_service_MUST-NOT_listen_on_tcp)
>
> R203: A service that R202 covers MUST listen on a Unix socket in a directory that only the service's account can enter. (data_service_socket_MUST_sit_in_private_directory)
>
> R204: When a connection arrives, a service that R202 covers MUST read the caller's account from the kernel's peer credentials and refuse any account but its own. (data_service_MUST_check_peer_account)

**What R202 leaves out, and why.** The issue also named a third kind of service, one that receives the agent's credential, which today is the API proxy. R202 does not cover it. Claude Code's documentation gives `ANTHROPIC_BASE_URL` as an endpoint, shows only `https://` values, and documents no setting that sends API requests over a Unix socket (sources in section 2). A requirement that the proxy's client cannot meet would only be broken, so the proxy is MIS-0002's open question Q17 (proxy_credential_to_loopback_port), with the options laid out there. The answer adds a requirement for the proxy in a later amendment or revision.

**Around them, in the same pull request:**
- MIS-0002's rationale, security note, conformance rows (R80 moves to `planned` for its new clause; R202 to R204 are `planned`), landing plan (a step 11), open questions (Q17) and revision history.
- The landing code, in later pull requests: the search service and the voice service move to a Unix socket with a peer check, using the helper in `macf/utils/peercred.py`, and each ships the tests named in MIS-0002's conformance table.
- The persistent layer policy, when it next changes, cites R80, R202, R203 and R204 by number, ID and slug (MIS-0001-R30 (policy_rule_MUST_cite_requirement)).

## 2 Reason

**The trigger.** Cversek/MacEff#868 found that three loopback services, the API proxy, the search service and the voice service, accept any local process and cannot tell callers apart. On a machine with several accounts that has two consequences. A service that answers from an agent's own data, or works for the agent, cannot check that the caller is that agent. And a loopback port is a name any local account can take while its owner is down, so a client that sends a credential there sends it to whoever holds the port.

**What the maintainers agreed.** In the deliberation on MIS-0007 (#867), the container-management maintainer wrote that "Loopback is a network, and MacEff has two such listeners of its own" and that a Unix socket in a private directory is the fix, because "peer credentials work and the name can't be taken" (comment 6550168791). The same maintainer asked for the voice service to move to a socket with peer credentials, audio passed as bytes, and no stop verb (comment 6550704872). The maintainers agreed that MIS-0002-R80 (pd_MUST-NOT_listen_on_network) should be read to cover loopback. This amendment writes the reading into the text, and makes the same rule bind the services.

**Why the voice service's other findings are not here.** The voice service no longer opens a path a caller names and no longer takes a stop request, and its request and reply sizes are bounded (#1082, #1087). What remains of it in #868 is the missing caller identity, which R202 to R204 settle.

**Why the broker is outside R202.** The MQTT broker of MIS-0002-R170 (mqtt_broker_MUST_bind_loopback) keeps its loopback port, and each client proves who it is with a certificate that the declaration names (MIS-0002-R172 (mqtt_broker_MUST_admit_only_named_certificates)). It has caller identity already, by another means. A service with no such means gets a socket, where the kernel supplies the identity.

**Whether the API proxy's client can use a Unix socket.** The answer found is no, and it comes from the documentation only. The client's environment variable reference describes `ANTHROPIC_BASE_URL` as "Override the API endpoint to route requests through a proxy or gateway" and says nothing about its accepted form (https://code.claude.com/docs/en/env-vars). The gateway setup page sets it to `https://llm-gateway.example.com` in every example, and lists no variable for a socket path (https://code.claude.com/docs/en/llm-gateway-connect.md). A web search for socket support turned up nothing in the official documentation either. This is absence from the documentation, not a test of the client: nobody has tried a `unix:` value, and the result of trying it would depend on the client's release. The same pages do document `NODE_EXTRA_CA_CERTS` for trusting a private certificate authority, which makes a TLS answer for the proxy (Q17, option c) the one that uses only documented client features.

**So:**
- The services that can use a Unix socket are bound by R202 to R204 now.
- R80 stops a reader from taking a loopback port for something other than a network.
- The proxy waits on Q17, and this amendment says so instead of binding it to a rule it cannot meet.

## 3 Sign-off

- **Asked of** MIS-0002's other maintainers: the container-management maintainer and the host-side maintainer.
- **Sign-offs:** none yet.
- **Changes requested, with each answer:** none yet.
- **The repo owner's decision:** none yet.

## Wiki-Links

[[security]] [[supervision]]
