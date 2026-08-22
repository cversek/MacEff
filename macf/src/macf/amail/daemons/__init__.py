"""Long-running amail processes, as package modules rather than loose scripts.

They live in the package because the package is what a deployment already
bind-mounts and installs editable. As files copied into an image they were
build-tier: a one-line fix meant rebuilding the base image and, through it,
every derived image that inherits from it. As modules they are restart-tier,
which is what a reader would expect of code sitting beside the library it
imports.

Each is invocable two ways -- `python -m macf.amail.daemons.<name>` and the
console script declared in pyproject -- so provisioning can name an interpreter
explicitly rather than depending on an execute bit.
"""
