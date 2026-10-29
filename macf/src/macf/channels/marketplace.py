"""Where the ``maceff`` plugin marketplace is, for the installed package.

The MacEff channel plugin (``maceff-channel@maceff``) ships inside the ``macf`` package, as
package data under ``maceff_marketplace/``, so any installed macf, a container's included, can
add the marketplace and install the channel from a local directory, with no network and no
repository checkout. That directory holds the one copy of the plugin's manifests. The
repository's root marketplace (``.claude-plugin/marketplace.json``) points its plugin source at
the same directory, so ``claude plugin marketplace add <repo>`` and the packaged marketplace
install the same files; a test holds the two catalogs to the same entries.
"""
from pathlib import Path

#: The marketplace's name, as ``plugin@marketplace`` and the organization allowlist spell it.
MARKETPLACE = "maceff"
#: The channel plugin it carries.
CHANNEL_PLUGIN = "maceff-channel"
#: ``maceff-channel@maceff``, the id ``claude plugin install`` takes.
CHANNEL_PLUGIN_ID = f"{CHANNEL_PLUGIN}@{MARKETPLACE}"
#: The channel as the harness's ``--channels`` takes it.
CHANNEL_FLAG = f"plugin:{CHANNEL_PLUGIN_ID}"


def packaged_marketplace() -> Path:
    """The directory of the ``maceff`` marketplace inside the installed macf package: the path
    ``claude plugin marketplace add`` takes. Raises FileNotFoundError when the package was
    built without its data, so a caller says why rather than adding an empty directory."""
    path = Path(__file__).resolve().parent / "maceff_marketplace"
    if not (path / ".claude-plugin" / "marketplace.json").is_file():
        raise FileNotFoundError(f"{path} holds no .claude-plugin/marketplace.json: this macf was "
                                f"installed without its package data")
    return path
