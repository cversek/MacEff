# MIS-0010: A Session That Can't Log In Waits on a Person, Not Failed

**Number**: 0010
**Type**: Amendment
**Status**: Draft
**Authors**: the repo owner, who asked for the change on issue #1161; drafted by the container-management maintainer
**Secretary**: the Secretary of deliberation #493
**Created**: 2026-11-27
**Amends**: MIS-0002: R19 (auth_failure_MUST_read_failed, now auth_failure_MUST_read_waiting_on_login); adds R202 (login_wait_MUST_alert_at_once), R203 (wake_MUST-NOT_type_into_login_wait) and R204 (login_wait_MUST_end_when_credential_renewed)
**Resolution**: pending: the sign-offs of MIS-0002's other two maintainers (section 3), then the repo owner's merge. The number is provisional: the next one no open pull request holds, for the Secretary to confirm.

---

## 1 Amendment

MIS-0002 is edited in place, and R19 carries a note that links this spec. The old and new text:

**R19.**
> Old: When a harness adapter reads an authentication failure, the primal daemon MUST set the session's state to failed. (auth_failure_MUST_read_failed)
>
> New: When a harness adapter reads an authentication failure, the primal daemon MUST set the session's state to waiting on a person, naming the login in its `waiting_on`. (auth_failure_MUST_read_waiting_on_login)

R19's decidable path changes with it: `test_auth_failure_is_failed` becomes `test_auth_failure_waits_on_login`.

The session stays running so a person can attach and log in. That needs no new text: R22 (layer_MUST-NOT_restart_waiting_unit) forbids restarting a waiting unit, and the attach reaches every live state.

**New requirements, R202 to R204.**
> R202: The outside watch MUST alert on a session waiting on its login at the first pass that reads the wait, keyed on the state record's `waiting_on`. (login_wait_MUST_alert_at_once)
>
> R203: The keystroke fallback MUST NOT type into a session while it waits on its login. (wake_MUST-NOT_type_into_login_wait)
>
> R204: When the stored credential a session waiting on its login uses is renewed, the primal daemon MUST set the session's state back to running. (login_wait_MUST_end_when_credential_renewed)

**Around them, in the same pull request:**
- MIS-0002's Rationale and Conformance gain lines for R19 and R202 to R204, and its Revision History gains a line.
- The `persistent_layer` policy describes the login wait: what the status, the attach and the watch show, how the wait ends, and that notices are held meanwhile.
- The code: the state record and the daemon's status carry `waiting_on`; the core enters and leaves the wait; the watch, the status line and the attach key on the field; the session's monitor reads the stored credential's expiry dates so that a login made elsewhere ends the wait.

## 2 Reason

**The trigger.** A container seat's login expired overnight. Its session unit read `failed`, and the person who tried to reach it over SSH was refused: "nothing attachable hosts its session (the session unit is failed; no session runs)". Renewing it took the operator at the host. The repo owner asked, on #1161:

> "this behavior is annoying, the system should warn the agent with a few days notice and also the session unit should allow an SSH connection so the /login can be done remotely without needing host access."

and then: "Work on the fix with the attachable login expired waiting state."

**Why R19 had to change.** Most of the behavior already existed. R19 held the session running while it read failed, and #1022 let the attach reach it, so the refusal came from a deployment that predated #1022. The label is the part a requirement fixed. R19 required `failed`, and "failed" reads as "broken: go to the host". The session was waiting for a person, which is the case R21 (pd_MUST_report_waiting_on_person) and R22 (layer_MUST-NOT_restart_waiting_unit) already define. R22 forbids restarting a waiting unit, which is the behavior the core spelled out by hand for a failed login.

**What R19 keeps.** R19 exists so that a session that can't work never reads idle or healthy (the expired login of 2026-10-04). Waiting on a person is neither. The status, the attach and the outside watch all treat it as needing someone, and R202 makes the watch say so at once.

**What the host-side maintainer asked for** (#1161, comment 7230662153), and where each landed:
1. **Name the wait as data, not only as words.** R19 now names `waiting_on`, and R202 keys the watch on it. The status and the attach read the field too. A login wait can't be confused with a permission prompt, which R23 forbids the layer to answer.
2. **Alert on a login wait at once, not after the hold allowance.** R202. A prompt may be answered within minutes; a login doesn't come back by itself.
3. **Return to running should follow the credential.** Where several sessions share one credential, a `/login` in one renews it for all, and the others, quiet, write nothing that would show it. R204. The session's monitor compares the stored credential's two expiry dates with those it saw at the failure, and only those two fields are read. R204's test has two sessions waiting and one login, and both return.
4. **Say what happens to notices meanwhile.** R203. The keystroke fallback already holds while the session waits on a person, and the core now names the login as what it waits on. R203 makes that a requirement, so no later path types into a `/login` flow.

**The test rename.** R19 keeps its id and changes its slug, as MIS-0001-R54 (changed_req_MUST_link_previous_text) provides; the note under it names the previous slug, so citations made before the change still resolve.

**A deployment whose wait spans the upgrade.** A build before this amendment recorded a login wait as `failed` with the authentication reason. A restarted daemon on the new build adopts a session recorded that way, as it adopts any live one, so it never starts a second session beside it. The session's next beat records the wait in the new form.

## 3 Sign-off

MIS-0001-R57 (amendment_MUST_have_maintainer_signoff) requires each maintainer of MIS-0002 other than the drafter to sign off before this merges.

- **The host-side maintainer:** agreed on #1161 (comment 7230662153) with four points for the spec, each answered in section 2. Sign-off on this text: pending.
- **The head maintainer:** pending. Holding its view until its usage reading is restored.
- **The repo owner's decision:** pending, by merge.

## Wiki-Links

[[persistent_layer]] [[mis]] [[login]] [[deployment]]
