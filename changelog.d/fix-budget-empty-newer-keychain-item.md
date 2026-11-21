### Fixed

- **The usage sampler and the login check no longer read an empty Keychain item as the login** (`budget.py`): a session started without `USER` can leave a newer item under the account "unknown" that holds no token and an expiry of zero, beside the login in use. `read_credential` took the newest item, so `budget sample` failed with "no token in the credential" and the usage reading on every hook line went stale, while the login check read the same item as expired. The newest item that holds a token is now the one read; an empty one is returned only when no item holds any.
