"""Orion Finance Python SDK."""

import importlib.metadata

from orion_finance_sdk_py.asset_map import build_asset_address_map
from orion_finance_sdk_py.cli import deploy_vault, submit_intent
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
    OrionVault,
    PriceAdapterRegistry,
    VaultFactory,
)
from orion_finance_sdk_py.costs import ExecutionCost, ExecutionCostEstimator, get_cost
from orion_finance_sdk_py.hpke import seal_intent, seal_portfolio
from orion_finance_sdk_py.intent import Intent
from orion_finance_sdk_py.order_intent_io import load_order_intent
from orion_finance_sdk_py.stats import ReturnSeries, covariance, measures, rank_products

from . import lp, manager, stats, strategist, views

__version__ = importlib.metadata.version("orion-finance-sdk-py")

__all__ = [
    "ExecutionCost",
    "ExecutionCostEstimator",
    "Intent",
    "LiquidityOrchestrator",
    "OrionConfig",
    "OrionEncryptedVault",
    "OrionTransparentVault",
    "OrionVault",
    "PriceAdapterRegistry",
    "ReturnSeries",
    "VaultFactory",
    "build_asset_address_map",
    "covariance",
    "deploy_vault",
    "get_cost",
    "load_order_intent",
    "lp",
    "manager",
    "measures",
    "rank_products",
    "seal_intent",
    "seal_portfolio",
    "stats",
    "strategist",
    "submit_intent",
    "views",
]
