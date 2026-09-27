"""Roles: standing positions and their duties, a parallel store beside tasks.

See the roles policy (``macf_tools policy navigate roles``) for what a role
and a duty are; this package is the code that passes that policy's tests.
"""
from .shelf import ICON_SHELF

_LAZY = {"Duty": ".models", "Role": ".models", "Update": ".models", "ROLE_MACHINE": ".models",
         "DUTY_MACHINE": ".models", "RoleStore": ".store", "RoleError": ".store", "roles_dir": ".store"}


def __getattr__(name):
    # Loaded on first use: the models import pydantic, and importing this
    # package used to cost every command line parser that much before it had
    # parsed anything. ``from macf.roles import Role`` still works; it arrives here.
    if name in _LAZY:
        import importlib
        value = getattr(importlib.import_module(_LAZY[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
