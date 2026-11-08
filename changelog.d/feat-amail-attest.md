### Added

- amail: `macf.amail.attest` decides what a signature attests against the operator's registry. A retired key verifies only mail the receiving broker accepted inside its window, by that broker's own hand-off record, and never signs (MIS-0004 R45). A verified message whose key's account holds another agent's key is labelled attested on a shared login (R46).
