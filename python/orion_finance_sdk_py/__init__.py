"""Orion Finance Python SDK."""

import importlib.metadata

from orion_finance_sdk_py.asset_map import build_asset_address_map
from orion_finance_sdk_py.cli import deploy_vault, submit_order
from orion_finance_sdk_py.contracts import (
    OrionConfig,
    OrionTransparentVault,
    PriceAdapterRegistry,
)
from orion_finance_sdk_py.order_intent_io import load_order_intent

__version__ = importlib.metadata.version("orion-finance-sdk-py")

__all__ = [
    "OrionConfig",
    "OrionTransparentVault",
    "PriceAdapterRegistry",
    "build_asset_address_map",
    "deploy_vault",
    "load_order_intent",
    "submit_order",
]
