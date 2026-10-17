# MIS-0005: A Unit's Exit-Code Contract May Be the Default

**Number**: 0005
**Type**: Standards
**Status**: Draft
**Authors**: the head maintainer, whose wording R01 adopts; drafted by the Secretary of MIS-0002
**Secretary**: none
**Deliberation**: pending
**Created**: 2026-10-17
**Updates**: MIS-0002: R09 (declaration_MUST_state_unit_fields)
**Supersedes**: none
**Lands-in**: framework/policies/base/infrastructure/persistent_layer.md, macf/tests/test_pd_interface.py, framework/mis/MIS-0002-persistent-layer.md (an editorial line in its Revision History)
**Resolution**: none

---

## 1 Summary

MIS-0002-R09 (declaration_MUST_state_unit_fields) says each declared unit must state five things, its exit-code contract among them. The declaration model has always let that contract default (exit 0 is success, exit 78 asks not to be restarted), and the persistent layer's policy documents the default. So R09 and the code disagree. This MIS keeps the code's behavior and changes the requirement: a unit states its exit-code contract unless the default is the contract it means. The other four fields stay required. Only authors of unit declarations are affected, and nothing they have written needs to change.

## 2 Motivation

- **R09 cannot pass as written.** In the MIS-0002 conformance work, R09 was found "partly built": the model requires the command, the account, the restart policy and the liveness interval, and refuses a unit missing any of them, but gives the exit-code contract a default. Evidence: the conformance map posted on the deliberation issue, 2026-10-16 (https://github.com/cversek/MacEff/issues/552#issuecomment-6226122169), and `macf.pd.interface.ExitCodes` (a measurement: the code as written).
- **The head maintainer, who wrote the declaration model, ruled to keep the default.** "Keep the default and revise the row. Requiring the contract would break every declaration in the field to restate what most units mean anyway." Evidence: https://github.com/cversek/MacEff/issues/552#issuecomment-6226208335 (a ruling on the record).
- **The revision changes what R09 requires, so it can't be an edit.** MIS-0001-R35 (substantive_change_MUST_be_new_MIS) requires a new MIS for a change to an accepted requirement's meaning. The Secretary said so on the deliberation issue and proposed this MIS. Evidence: https://github.com/cversek/MacEff/issues/552#issuecomment-6229435982.

## 3 Goals and Non-Goals

**Goals**
- Make the requirement say what the declaration model does, so that R09's successor can pass.
- Keep every declaration in use valid.

**Non-goals**
- Changing the default contract itself, or any other unit field.
- Changing R59 (unit_MUST_declare_memory_limit), which already requires the memory limit with no default.

## 4 Guide-Level Explanation

An agent writing a unit declaration names the command, the account the unit runs as, its restart policy and its liveness interval; leaving any of them out fails when the declaration is read. It doesn't name an exit-code contract when exit 0 means done and exit 78 means "don't restart me", because that is the default. It names one only when the unit means something else, for example a unit whose exit 2 is a normal, finished run.

## 5 Terms

- **default exit-code contract**: exit 0 is success, and exit 78 asks the daemon not to restart the unit. Defined in `macf.pd.interface` and described in the `persistent_layer` policy.

## 6 Specification

- **R01** [MUST · decidable: macf/tests/test_pd_interface.py::test_unit_fields_are_required_and_the_exit_code_contract_defaults] Each declared unit MUST state its command, owning account, restart policy and liveness interval, and its exit-code contract unless the default exit-code contract is the one it means. (declaration_MUST_state_unit_fields_or_default_contract)

## 7 Rationale and Rejected Alternatives

**Why R01 replaces MIS-0002-R09.** R01 is R09 with the head maintainer's exception added, in the head maintainer's words: "a unit MUST state its exit-code contract unless the default (success on 0, no restart on 78) is the contract it means." Most units mean the default. A requirement that makes every declaration restate it adds lines that say nothing, and a declaration's author learns to copy them without reading. The four required fields have no default that would be right for most units, so they stay required. R01 is decidable as the code stands: the test refuses a unit missing any of the four, and loads a unit with no contract as the default.

**Rejected**
- **Require the contract, as R09 says.** Rejected by the head maintainer's ruling: it is a breaking change to every declaration in use, for no change in behavior.
- **Revise R09's row in a conformance sweep.** Rejected: a sweep may make only editorial changes (MIS-0001-R34 (accepted_MIS_MUST_change_editorially)), and this one changes what R09 requires.
- **Fold the change into the next MIS that touches the declaration model.** Possible, but it would leave R09 unable to pass, and its row unexplained, until an unrelated MIS came along. The change is small enough to decide on its own.

## 8 Prior Art

- systemd's `SuccessExitStatus=` and `RestartPreventExitStatus=` are optional: a service that sets neither gets the defaults (exit 0 and a few clean signals count as success, and no exit code prevents a restart). https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- The sysexits convention, where 78 (`EX_CONFIG`) means a configuration error, the case in which a restart cannot help.
- MIS-0002, whose R09 this MIS updates.

## 9 Compatibility and Deployment

- **No declaration changes.** Every declaration that loads today still loads, with the same meaning.
- **Deployments** receive the changed policy line through the framework overlay at their next refresh, and need do nothing else.

## 10 Security and Safety

- **No change at run time.** The daemon's behavior is unchanged. A unit that leaves out its contract already gets the default, and a unit that exits 78 because it can't recover is already left stopped, with the reason recorded.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | macf/tests/test_pd_interface.py::test_unit_fields_are_required_and_the_exit_code_contract_defaults | passing |

**Cold-reader trial.** Not yet held. Due before this MIS becomes Final, on the landed `persistent_layer` policy's declaration section: a reader who saw neither this MIS nor its discussion writes a unit declaration for a unit whose normal finish is exit 2, and one for a unit with no special codes.

## 12 Landing Plan

One pull request carries this MIS and its landing:
- `persistent_layer` policy, the declaration section: the citation of MIS-0002-R09 (declaration_MUST_state_unit_fields) becomes MIS-0005-R01 (declaration_MUST_state_unit_fields_or_default_contract), and the sentence says the contract may be left to the default;
- `macf/tests/test_pd_interface.py`: the test R01 names;
- MIS-0002: an editorial line in its Revision History naming this MIS and R09 (MIS-0001 §8.1).

## 13 Open Questions

None.

## 14 Deliberation Record

- **P01** The head maintainer, as the declaration model's author, 2026-10-16, in answer to the Secretary's question on the deliberation issue, quoted in full: "**R09:** keep the default and revise the row. Requiring the contract would break every declaration in the field to restate what most units mean anyway. My wording would be: a unit MUST state its exit-code contract unless the default (success on 0, no restart on 78) is the contract it means. The default stays documented in `persistent_layer.md`." https://github.com/cversek/MacEff/issues/552#issuecomment-6226208335 (keep_the_default_contract)

- **P02** The Secretary of MIS-0002, 2026-10-17, quoted in part: "your wording changes what the requirement says. It moves from 'each unit MUST state its exit-code contract' to 'MUST state it unless the default is the one it means'. `mis` 8.1 counts any change to a requirement's meaning as substantive [...] I agree with the outcome: keeping the default is right, and requiring every declaration to restate it would be churn." https://github.com/cversek/MacEff/issues/552#issuecomment-6229435982 (substantive_so_a_new_MIS)

Objections recorded: none.

## 15 Revision History

- 2026-10-17: first version, with the pull request that lands it.

## Wiki-Links

[[primal_daemon]] [[supervision]]
