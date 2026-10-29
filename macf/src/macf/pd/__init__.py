"""The primal daemon (MIS-0002): one per agent, keeping that agent's managed units alive.

This package holds, so far, only the interface that step 1 and the later steps share:
the declaration format, the events a unit and the daemon write, the daemon's sockets and
the messages they carry. See ``macf/docs/developer/primal_daemon_interface.md``.
"""
