"""Account and group numbers across a host and the containers it runs.

A container without user-namespace remapping shares the host's uid and gid space: a number
inside it and the same number on the host are one kernel identity. Each side's table is
coherent on its own, so an overlap shows only in their union. ``audit`` reads that union.
"""
