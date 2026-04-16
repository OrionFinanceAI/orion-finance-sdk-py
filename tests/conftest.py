"""Pytest configuration. Load .env so fork tests and other tests see env vars (e.g. ALCHEMY_API_KEY)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root, cwd, then tests/ (later files override so tests/.env can set ALCHEMY_API_KEY)
_root = Path(__file__).resolve().parents[1]
for _p in (_root / ".env", Path.cwd() / ".env", _root / "tests" / ".env"):
    if _p.exists():
        load_dotenv(_p, override=True)


def _alchemy_key_for_ape() -> str:
    """Key for ape-alchemy WEB3_* vars: explicit ALCHEMY_API_KEY or /v2/<key> in RPC_URL."""
    direct = (os.getenv("ALCHEMY_API_KEY") or "").strip()
    if direct:
        return direct
    rpc = (os.getenv("RPC_URL") or "").strip()
    if "alchemy.com" in rpc and "/v2/" in rpc:
        try:
            return rpc.split("/v2/", 1)[1].split("?", 1)[0].strip().rstrip("/")
        except IndexError:
            return ""
    return ""


_k = _alchemy_key_for_ape()
if _k:
    os.environ.setdefault("WEB3_ALCHEMY_API_KEY", _k)
    os.environ.setdefault("WEB3_ETHEREUM_SEPOLIA_ALCHEMY_API_KEY", _k)

# Fork tests use Hardhat node (16M gas cap); SDK view calls need explicit gas when forking
if os.getenv("ALCHEMY_API_KEY") or os.getenv("RPC_URL"):
    os.environ.setdefault("ORION_FORCE_VIEW_GAS", "1")

# Ape's SubprocessProvider.start() defaults to 20s waiting for the local Hardhat JSON-RPC port. That runs for
# `ape test --network ...` (connects at collection) and for fork fixtures. CI historically used 90s; default 90
# elsewhere (override with APE_HARDHAT_RPC_READY_TIMEOUT).
try:
    import ape.api.providers as _ape_providers
except ImportError:
    pass
else:
    _original_subprocess_start = _ape_providers.SubprocessProvider.start

    def _subprocess_start_with_floor(self, timeout: int = 20):
        raw = os.getenv("APE_HARDHAT_RPC_READY_TIMEOUT", "90")
        try:
            floor = int(raw)
        except ValueError:
            floor = 90
        return _original_subprocess_start(self, timeout=max(timeout, floor))

    _ape_providers.SubprocessProvider.start = _subprocess_start_with_floor
