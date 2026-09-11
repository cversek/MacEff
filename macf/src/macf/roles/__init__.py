"""Roles: standing positions and their duties, a parallel store beside tasks.

See the roles policy (``macf_tools policy navigate roles``) for what a role
and a duty are; this package is the code that passes that policy's tests.
"""
from .models import Duty, Role, Update, ROLE_MACHINE, DUTY_MACHINE, ICON_SHELF  # noqa: F401
from .store import RoleStore, RoleError, roles_dir  # noqa: F401
