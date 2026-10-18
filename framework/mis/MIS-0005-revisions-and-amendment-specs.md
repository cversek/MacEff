# MIS-0005: Revisions and Amendment Specs, Changing an MIS in Place

**Number**: 0005
**Type**: Amendment
**Status**: Draft
**Authors**: the repo owner; drafted by the container-management maintainer, the Secretary of MIS-0001
**Secretary**: the Secretary of deliberation #493
**Created**: 2026-10-18
**Amends**: MIS-0001: R01 (PR_MUST_cite_MIS_for_major_change), R06 (MIS_MUST_carry_header_fields), R07 (MIS_MUST_contain_sections), R08 (type_MUST_be_listed), R34 (accepted_MIS_MUST_change_editorially), R35 (substantive_change_MUST_be_made_in_place); adds R52 to R58
**Resolution**: none

---

## 1 Amendment

MIS-0001 is edited in place, and each changed requirement there carries a note that links this spec. The old and new text of each one:

**R01, brought in from MIS-0003.**
> Old: A pull request that adds a subsystem, changes architecture across components, or changes what an agent is allowed to do MUST cite an accepted MIS. (PR_MUST_cite_accepted_MIS)
>
> New: A pull request that introduces a new policy or makes a major architectural change MUST cite an accepted MIS. (PR_MUST_cite_MIS_for_major_change)

MIS-0003 decided this change on 2026-10-10, and its text stood only in MIS-0003 until now.

**R06.**
> Old: Each MIS MUST carry the header fields of MIS-0000, in their order.
>
> New: Each MIS other than an amendment spec MUST carry the header fields of MIS-0000, in their order.

**R07.**
> Old: Each MIS MUST contain the numbered sections of MIS-0000, in their order.
>
> New: Each MIS other than an amendment spec MUST contain the numbered sections of MIS-0000, in their order.

**R08.**
> Old: The Type field MUST be Standards, Process or Informational.
>
> New: The Type field MUST be Standards, Process, Informational or Amendment.

**R34.**
> Old: After an MIS is Accepted, each change to it MUST be editorial and recorded in its Revision History.
>
> New: After an MIS is Accepted, each change to it that is neither a revision nor an amendment MUST be editorial and recorded in its Revision History.

**R35.**
> Old: A substantive change to an accepted MIS MUST be a new MIS that names the old one in Updates or Supersedes. (substantive_change_MUST_be_new_MIS)
>
> New: A substantive change to an accepted MIS MUST be a revision or an amendment, made in the MIS itself. (substantive_change_MUST_be_made_in_place)

**New requirements, R52 to R58.**
> R52: The repo owner MAY ask the Secretary of an MIS for a revision of it at any point. (repo_owner_MAY_request_revision)
>
> R53: When the repo owner asks for a revision, the Secretary MUST make it by a pull request that edits the MIS in place, which the repo owner merges. (revision_MUST_edit_MIS_in_place)
>
> R54: Each requirement that a revision or an amendment changes MUST carry a note under it that links its previous text and names any previous slug. (changed_req_MUST_link_previous_text)
>
> R55: Where others relied heavily on the text a change would replace, the repo owner MAY call for an amendment instead of a revision. (repo_owner_MAY_call_for_amendment)
>
> R56: Each amendment spec MUST give the old and new text of each requirement it changes, the reason, and the sign-off record. (amendment_spec_MUST_give_change_reason_signoff)
>
> R57: Before an amendment spec merges, each maintainer of the amended MIS other than its author MUST sign off on it. (amendment_MUST_have_maintainer_signoff)
>
> R58: The repo owner MAY veto any change that a maintainer requests to an amendment spec. (repo_owner_MAY_veto_requested_change)

**Around them, in the same pull request:**
- MIS-0001's Terms, Rationale, Conformance and Revision History, and its Q05 (unmeetable_MUST_path), answered.
- The `mis` policy, the glossary, and `macf_tools mis check`. The checker learns the amendment spec's form, and accepts a citation of a previous slug that a note under the requirement records.
- MIS-0003 gains a Revision History line, saying that its R01 now stands in MIS-0001's text.

## 2 Reason

**The trigger.** MIS-0002-R09 (declaration_MUST_state_unit_fields) could not pass as written, and the head maintainer ruled on 2026-10-16 to change it. Because MIS-0001-R35 then allowed no other route, the Secretary opened a new MIS for that one sentence. The repo owner objected, on 2026-10-18, in messages to the Secretary, quoted in full:

> "Why was MIS-0005 opened? It seems to be just an amendment on MIS-0002, which should be done in its thread. What does the protocol say? I wish I was consulted. MIS is a heavy weight coordination mechanism not a catch all for tweaks of existing specs."

> "The way I see this is that until an MIS has been fully landed we shouldn't even need a formal amendment to revise its structure as problems surface. The document it self is version controlled thst should be sufficient for preserving the record. The repo owner is a BDFL and can request revisions at any point or decide on a formal amendment if the underlying flawed state was heavily relied upon. Formally amend MIS-0001 to allow for the repo owner (not just any operator) to request revisions from the Secretary which are made with a PR to directly on the MIS document. The MIS designation is a MAJOR plan not formality for its own sake! Otherwise we risk the impedance of the bureaucratic echo chamber. Rather automated version control was already the superior solution for necessary revisions encountered during implementation."

**The shape of the change.** A first draft followed MIS-0003's pattern: a separate MIS updating MIS-0001. The repo owner rejected it:

> "So the problem is see with using MIS-0003 as a template for action is that it spreads the current requirements over multiple documents making compliance more difficult. The amendment process should happen in place like a revision then you maintain a back-link reference to the previous text. Anyone can see the document was revised and find the old text via scholarship. The Secretary of the document is the repo owners delegate to make these changes. This process needs to be described in MIS-0001 directly. Likewise the MIS-0003 changes need to be brought to its text directly."

> "You may make an new MIS for formal amendments, say use MIS-0005 the document which describes amendment, but the MIS which takes the amendment is edited in place and has a link to the amendment spec. The spec for the amendment spec needs sign off approval just from the other Maintainers. This makes them aware of the history and helps them update any internal understanding."

> "MIS-0005 as is needs to be purged and its number used for the amendment spec that introduces both the simple revision and amendment spec procedures. The revision does not require an MIS number at all. The R09 change happens by revision."

**His answers to three questions, the same day:**
- **Who merges an amendment spec:** the repo owner, after the other maintainers sign off.
- **Whether a revision needs a maintainer's review:** no; his request and his merge are enough.
- **The amendment spec's form:** the short form, "but Maintainers may request changes, owner has final word and can veto changes".

**So:**
- The requirements in force stand in one document, the MIS itself (R35).
- The history is kept by version control and by a note at each changed requirement (R54).
- A revision is the simple path (R52, R53), and an amendment the formal one (R55 to R58).
- This spec is the first amendment, made by the procedure it introduces.

The draft that first held this number, a one-requirement MIS changing R09, was never merged and is purged. R09 changes by revision once this spec is accepted.

## 3 Sign-off

- **Asked of** MIS-0001's other maintainers: the head maintainer and the host-side maintainer.
- **Sign-offs:** pending.
- **Changes requested:** none yet.
- **The repo owner's decision:** pending.

## Wiki-Links

[[methodology]] [[policy_as_api]]
