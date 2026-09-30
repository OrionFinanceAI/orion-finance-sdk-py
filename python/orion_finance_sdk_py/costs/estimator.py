"""Estimate execution cost via mainnet adapters vs oracle fair value."""

from __future__ import annotations

import math
from decimal import ROUND_DOWN, Decimal

from web3 import Web3
from web3.exceptions import ContractLogicError

from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    PriceAdapterRegistry,
    load_contract_abi,
)
from orion_finance_sdk_py.costs.types import ExecutionCost
from orion_finance_sdk_py.orion_config_env import MAINNET_CHAIN_ID
from orion_finance_sdk_py.utils import checksum_address, to_base_units


def looks_like_address(symbol: str) -> bool:
    """Return True if ``symbol`` looks like a 20-byte hex address."""
    return symbol.startswith("0x") and len(symbol) == 42


def _quantize_human_size(size: float, token_decimals: int) -> Decimal:
    """Floor ``size`` to ``token_decimals`` so float noise does not reject conversion."""
    quantum = Decimal(1).scaleb(-int(token_decimals))
    return Decimal(str(abs(size))).quantize(quantum, rounding=ROUND_DOWN)


def _require_mainnet(config: OrionConfig) -> None:
    if int(config.chain_id) != MAINNET_CHAIN_ID:
        raise ValueError(
            "Execution cost estimation requires mainnet Orion deployment "
            f"(active chain_id={config.chain_id}). Set CHAIN=mainnet and "
            "MAINNET_RPC_URL / MAINNET_ORION_CONFIG_ADDRESS."
        )


def _resolve_asset(config: OrionConfig, symbol: str) -> tuple[str, str]:
    """Return ``(label, checksummed_address)`` for a ticker or address."""
    raw = symbol.strip()
    if looks_like_address(raw):
        addr = checksum_address(raw)
        whitelist = [checksum_address(a) for a in config.whitelisted_assets]
        if addr not in whitelist:
            raise ValueError(
                f"Asset {addr} is not in the mainnet whitelisted investment universe."
            )
        names = list(config.whitelisted_asset_names)
        label = raw
        for i, a in enumerate(whitelist):
            if a == addr and i < len(names) and names[i]:
                label = names[i]
                break
        return label, addr

    needle = raw.upper()
    names = [n.strip() for n in config.whitelisted_asset_names]
    assets = [checksum_address(a) for a in config.whitelisted_assets]
    for name, addr in zip(names, assets, strict=False):
        if name and name.upper() == needle:
            return name, addr
    raise ValueError(
        f"Unknown symbol {symbol!r}. Pass a whitelisted ticker or mainnet address."
    )


def fair_underlying_amount(
    *,
    shares: int,
    price: int,
    price_adapter_decimals: int,
    token_decimals: int,
    underlying_decimals: int,
) -> int:
    """Oracle mark of ``shares`` in underlying base units (PIT TVL scaling)."""
    if shares < 0 or price < 0:
        raise ValueError("shares and price must be non-negative")
    price_scale = 10**price_adapter_decimals
    token_scale = 10**token_decimals
    underlying_scale = 10**underlying_decimals
    return (int(shares) * int(price) * underlying_scale) // (price_scale * token_scale)


def cost_pct(execution: int, fair: int) -> float:
    """Positive means worse than oracle (buy pays more underlying than mark)."""
    if fair <= 0:
        raise ValueError("fair_underlying must be positive to compute cost_pct")
    return (execution - fair) / fair


class ExecutionCostEstimator:
    """Manager-facing execution cost estimator.

    Compares mainnet ``previewBuy`` quotes to price-adapter oracle fair value.
    Requires ``CHAIN=mainnet``, ``MAINNET_RPC_URL``, and
    ``MAINNET_ORION_CONFIG_ADDRESS``.
    """

    def __init__(self) -> None:
        """Bind OrionConfig / LO / registry on the active (mainnet) chain."""
        self.config = OrionConfig()
        _require_mainnet(self.config)
        self.lo = LiquidityOrchestrator()
        self.registry = PriceAdapterRegistry()
        self.w3: Web3 = self.config.w3

    def get_cost(
        self,
        symbol: str,
        size: float,
        *,
        netting_eta: float = 0.0,
        block: int | None = None,
        shares: int | None = None,
    ) -> ExecutionCost:
        """Estimate buy-side execution cost in human asset units.

        Args:
            symbol: Whitelisted ticker or mainnet asset address.
            size: Positive human units of the risk asset to buy. Ignored
                when ``shares`` is set. The protocol **underlying**
                (numeraire) is a no-op: ``cost_pct`` is always ``0``.
            netting_eta: Fraction of the nominal size that is internally
                netted. The adapter quote uses ``(1 - eta) * size``;
                ``cost_pct`` is that of the residual swap, not scaled by
                ``(1 - eta)``.
            block: Optional historical block for eth_call / getPrice.
            shares: Optional raw ERC-20 units for the residual swap;
                overrides ``swap_size`` when provided.
        """
        size_f = float(size)
        if not math.isfinite(size_f) or size_f <= 0:
            raise ValueError("size must be a positive finite number")
        if not 0.0 <= float(netting_eta) <= 1.0:
            raise ValueError("netting_eta must be in [0, 1]")

        swap_size = (1.0 - float(netting_eta)) * size_f

        label, asset = _resolve_asset(self.config, symbol)
        token_decimals = int(self.config.token_decimals(asset))

        if swap_size == 0 and shares is None:
            return ExecutionCost(
                symbol=label,
                asset=asset,
                size=size_f,
                netting_eta=float(netting_eta),
                swap_size=0.0,
                shares=0,
                cost_pct=0.0,
                execution_underlying=0,
                fair_underlying=0,
                price=0,
                execution_adapter="",
                block=block,
            )

        if shares is None:
            human_q = _quantize_human_size(swap_size, token_decimals)
            if human_q <= 0:
                shares_i = 0
                swap_size = 0.0
            else:
                shares_i = to_base_units(human_q, token_decimals)
                swap_size = float(human_q)
        else:
            if isinstance(shares, bool) or not isinstance(shares, int):
                raise TypeError("shares must be an int of raw token units")
            shares_i = shares
            if shares_i <= 0:
                raise ValueError("shares must be positive")
            swap_size = shares_i / (10**token_decimals)

        if shares_i <= 0:
            return ExecutionCost(
                symbol=label,
                asset=asset,
                size=size_f,
                netting_eta=float(netting_eta),
                swap_size=float(swap_size),
                shares=0,
                cost_pct=0.0,
                execution_underlying=0,
                fair_underlying=0,
                price=0,
                execution_adapter="",
                block=block,
            )

        underlying = checksum_address(self.config.underlying_asset)
        # Numeraire: buying underlying with underlying is a no-op onchain.
        if asset.lower() == underlying.lower():
            price = int(self.registry.get_price(asset, block=block))
            return ExecutionCost(
                symbol=label,
                asset=asset,
                size=size_f,
                netting_eta=float(netting_eta),
                swap_size=float(swap_size),
                shares=shares_i,
                cost_pct=0.0,
                execution_underlying=shares_i,
                fair_underlying=shares_i,
                price=price,
                execution_adapter="",
                block=block,
            )

        adapter = self.lo.execution_adapter_of(asset, block=block)
        price = int(self.registry.get_price(asset, block=block))
        underlying_decimals = int(self.config.token_decimals(underlying))
        fair = fair_underlying_amount(
            shares=shares_i,
            price=price,
            price_adapter_decimals=int(self.registry.price_adapter_decimals),
            token_decimals=token_decimals,
            underlying_decimals=underlying_decimals,
        )
        if fair <= 0:
            raise ValueError(
                f"Oracle fair value is zero for {label} ({asset}); cannot compute cost."
            )

        execution = self._preview_buy(adapter, asset, shares_i, block=block)
        return ExecutionCost(
            symbol=label,
            asset=asset,
            size=size_f,
            netting_eta=float(netting_eta),
            swap_size=float(swap_size),
            shares=shares_i,
            cost_pct=cost_pct(int(execution), int(fair)),
            execution_underlying=int(execution),
            fair_underlying=int(fair),
            price=price,
            execution_adapter=adapter,
            block=block,
        )

    def _adapter_contract(self, adapter: str):
        return self.w3.eth.contract(
            address=checksum_address(adapter),
            abi=load_contract_abi("IExecutionAdapter"),
        )

    def _preview_buy(
        self,
        adapter: str,
        asset: str,
        shares: int,
        *,
        block: int | None,
    ) -> int:
        contract = self._adapter_contract(adapter)
        fn = contract.functions.previewBuy(checksum_address(asset), int(shares))
        try:
            if block is None:
                return int(fn.call())
            return int(fn.call(block_identifier=block))
        except ContractLogicError as exc:
            raise RuntimeError(
                f"previewBuy reverted for asset {asset} on adapter {adapter}: {exc}"
            ) from exc


_DEFAULT_ESTIMATOR: ExecutionCostEstimator | None = None


def get_cost(
    symbol: str,
    size: float,
    *,
    netting_eta: float = 0.0,
    block: int | None = None,
    shares: int | None = None,
) -> ExecutionCost:
    """Module-level wrapper around a process-default :class:`ExecutionCostEstimator`."""
    global _DEFAULT_ESTIMATOR
    if _DEFAULT_ESTIMATOR is None:
        _DEFAULT_ESTIMATOR = ExecutionCostEstimator()
    return _DEFAULT_ESTIMATOR.get_cost(
        symbol,
        size,
        netting_eta=netting_eta,
        block=block,
        shares=shares,
    )
