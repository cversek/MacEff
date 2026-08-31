# amail: module provenance

Where every module in this package came from, and what has happened to it since.

This exists because the reduction that produced this package deliberately did
**not** branch from the pull request it harvested. That PR stays open and
unmerged as a quarry: a branch descended from it would carry its history, so
merging the reduction would effectively merge the quarry and manufacture the sunk
cost the pivot existed to avoid. Traceability is therefore documented rather than
inherited through ancestry -- which puts the burden on this file being *checkable*
rather than believed.

## Retained modules

Harvest commit: `bc651c2` -- twelve source files brought across **byte-identical**,
before any reduction, so that later commits could be measured against a baseline
rather than against a memory.

| module | origin commit (quarry) | state vs quarry | changed by this phase |
|---|---|---|---|
| `audit.py` | `f04db77` | modified | added mailbox-read records |
| `broker.py` | `f04db77` | modified | read operations, their audit records, provenance note on `accept_inbound` |
| `client.py` | `c39b70b` | modified | shared socket round-trip; read wrappers |
| `__init__.py` | `8082cef` | modified | exports for the read operations |
| `contacts.py` | `e4cc6e3` | **byte-identical** | -- |
| `crypto.py` | `e4cc6e3` | **byte-identical** | -- |
| `models.py` | `f04db77` | **byte-identical** | -- |
| `store.py` | `9f67ada` | **byte-identical** | -- |
| `trust.py` | `8082cef` | **byte-identical** | -- |

Five of nine are unchanged from the quarry. The four that moved are exactly the
modules the access-path work touched, and nothing else was disturbed.

## Dropped modules

**None.** Stated explicitly rather than left as an absence, because the criterion
this file answers requires every dropped module to name the inherited component
replacing it, and a silent empty section is indistinguishable from a forgotten
one.

The disposition table originally marked `store.py` **replace**. That was
corrected to **split** before any change was made, on measurement: the only
stdlib candidate inheritor provides none of the five controls `store.py` carries
(`O_NOFOLLOW` symlink guard, `dir_fd` TOCTOU-safe relative operations, `O_EXCL`
collision guard, symlink detection, quarantine), each of which was won by an
audit round. Its row above shows the consequence -- `store.py` is byte-identical,
because this phase changed the access path *around* the store rather than the
store itself. Whether the delivery mechanism later yields to an inherited MTA is
a transport decision that belongs where that inheritor is actually chosen.

## Honest net line count

This phase **added** module lines rather than only moving and deleting them. The
growth is the access path: read operations on the broker, their wrappers on the
client, and the re-pointed CLI commands. Recorded here because the phase's
anti-goal requires the number to be reported plainly rather than characterised,
and because a reduction that grows is exactly the thing a reader should be able
to notice without being told a story about it.

## Verify this file rather than trusting it

Every claim above is mechanically checkable:

```bash
# origin commit for a module in the quarry
git log --format=%h -1 origin/<quarry-branch> -- macf/src/macf/amail/<module>

# is a module still byte-identical to the quarry?
git show origin/<quarry-branch>:macf/src/macf/amail/<module> \
  | diff - macf/src/macf/amail/<module> && echo IDENTICAL

# what changed a module since the harvest
git log --oneline bc651c2..HEAD -- macf/src/macf/amail/<module>
```

If a row here disagrees with those commands, the commands are right.
