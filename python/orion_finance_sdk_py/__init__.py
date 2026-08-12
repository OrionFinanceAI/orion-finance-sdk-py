"""Orion Finance Python SDK."""

import importlib.metadata

from orion_finance_sdk_py.asset_map import build_asset_address_map
from orion_finance_sdk_py.cli import deploy_vault, submit_order
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
    OrionVault,
    PriceAdapterRegistry,
    VaultFactory,
)
from orion_finance_sdk_py.hpke import seal_intent, seal_portfolio
from orion_finance_sdk_py.intent import Intent
from orion_finance_sdk_py.order_intent_io import load_order_intent

from . import lp, manager, strategist, views

__version__ = importlib.metadata.version("orion-finance-sdk-py")

__all__ = [
    "Intent",
    "LiquidityOrchestrator",
    "OrionConfig",
    "OrionEncryptedVault",
    "OrionTransparentVault",
    "OrionVault",
    "PriceAdapterRegistry",
    "VaultFactory",
    "build_asset_address_map",
    "deploy_vault",
    "load_order_intent",
    "lp",
    "manager",
    "seal_intent",
    "seal_portfolio",
    "strategist",
    "submit_order",
    "views",
]
