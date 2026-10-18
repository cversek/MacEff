### Changed

- **An accepted MIS now changes in place: by a revision, or by an amendment spec** (MIS-0005, MIS-0001 amended in place, `framework/policies/base/meta/mis.md` §1.2, §1.3, §2.2, §2.3, §8.1, `framework/glossary.md`, `macf/src/macf/mis.py`). Before, any substantive change to an accepted MIS had to be a new MIS, which spread the requirements in force across documents.
  - **Revision.** The repo owner may ask an MIS's Secretary to revise it at any point. The Secretary edits it by pull request and the repo owner merges, with no MIS number.
  - **Amendment.** For a change others relied on heavily, a short amendment spec of the new Type `Amendment` gives the old and new text, the reason, and the sign-off of the MIS's other maintainers. The MIS itself is edited in the same pull request.
  - **Back-links.** Each changed requirement carries a note linking its previous text and naming any previous slug, and `mis check` accepts a citation by that slug.
  - **MIS-0001-R01** now carries MIS-0003's threshold in its own text.
