"""OpenTrading MCP server (FastMCP, shareable team -> public)."""

import os as _os

__version__ = "0.1.0"


def _force_vnstock_guest() -> None:
    """Keep vnstock 6 in guest mode: drop ``VNSTOCK_API_KEY`` before any vnstock import.

    vnstock 6's core reads ``VNSTOCK_API_KEY`` and a login registers the machine as one
    of the account's devices (``VNSTOCK_AUTH_DEVICE_LIMIT``). The Render free instance
    has no persistent disk for ``VNSTOCK_HOME``, so every cold start could count as a
    new device. Guest mode serves every route this server uses (ssi/dnse/binance with
    the user's own source keys; verified on 6.0.0, 2026-11-13). Set
    ``VNSTOCK_ALLOW_LOGIN=1`` to keep the key on purpose.
    """
    if _os.environ.get("VNSTOCK_ALLOW_LOGIN", "").strip() != "1":
        _os.environ.pop("VNSTOCK_API_KEY", None)


_force_vnstock_guest()
