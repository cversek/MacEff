### Fixed

- **`cryptography` is required at 42.0 or later** (`macf/pyproject.toml`): `pd/broker_defaults.py` reads a certificate's `not_valid_after_utc`, which arrived in 42.0, while the pin allowed 40.0. Installs that met the old pin failed with an `AttributeError` when a daemon checked its broker's certificate (#1020).
  **Upgrade note:** an editable install doesn't upgrade its dependencies when its checkout updates. Run `python -m pip install -e <checkout>/macf` (or `pip install 'cryptography>=42'`) in the interpreter that runs the primal daemon.
