"""Pytest configuration. Load .env so tests see env vars (e.g. ALCHEMY_API_KEY)."""

from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[1]
for _p in (_root / ".env", Path.cwd() / ".env", _root / "tests" / ".env"):
    if _p.exists():
        load_dotenv(_p, override=True)
