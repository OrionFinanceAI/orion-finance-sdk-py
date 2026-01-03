"""Orion Finance Python SDK."""

import importlib.metadata

from orion_finance_sdk_py.cli import deploy_vault, submit_order

__version__ = importlib.metadata.version("orion-finance-sdk-py")

__all__ = ["deploy_vault", "submit_order"]
