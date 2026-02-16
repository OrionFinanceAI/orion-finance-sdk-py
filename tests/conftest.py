"""Pytest configuration. Load .env so fork tests and other tests see env vars (e.g. ALCHEMY_API_KEY)."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root, cwd, then tests/ (later files override so tests/.env can set ALCHEMY_API_KEY)
_root = Path(__file__).resolve().parents[1]
for _p in (_root / ".env", Path.cwd() / ".env", _root / "tests" / ".env"):
    if _p.exists():
        load_dotenv(_p, override=True)
