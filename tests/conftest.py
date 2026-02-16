"""Pytest configuration. Load .env so fork tests and other tests see env vars (e.g. ALCHEMY_API_KEY)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root, cwd, then tests/ (later files override so tests/.env can set ALCHEMY_API_KEY)
_root = Path(__file__).resolve().parents[1]
for _p in (_root / ".env", Path.cwd() / ".env", _root / "tests" / ".env"):
    if _p.exists():
        load_dotenv(_p, override=True)

# In CI, give the Hardhat fork node more time to start (default 20s is often too low on runners).
if os.getenv("GITHUB_ACTIONS") or os.getenv("CI"):
    import ape.api.providers as _ape_providers

    _original_start = _ape_providers.ProviderAPI.start

    def _start_with_ci_timeout(self, timeout: int = 90):
        return _original_start(self, timeout=timeout)

    _ape_providers.ProviderAPI.start = _start_with_ci_timeout
