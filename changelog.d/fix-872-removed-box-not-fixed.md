### Fixed

- **A refused pickup box that is removed is no longer reported as fixed** (`pd/receiver.py`, #872): the receiver's slow re-check of a refused box (#1034) read a missing box as "access is fixed", because the access check answers "fine" for a box that is gone (the next pass looks again). The refusal now stands, unsaid, until the box exists and its access checks out.
