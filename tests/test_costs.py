"""Tests for adapter-backed execution cost estimation."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.costs.estimator import (
    ExecutionCostEstimator,
    cost_pct,
    fair_underlying_amount,
    get_cost,
)
from orion_finance_sdk_py.costs.state_override import (
    allowance_storage_slot,
    balance_storage_slot,
    build_erc20_state_override,
    to_storage_hex,
    vyper_mapping_slot,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS
from orion_finance_sdk_py.utils import checksum_address


def test_fair_underlying_amount_scaling():
    # 1 whole token (6 decimals), price 1e8, price decimals 8, underlying 6
    # fair = 1e6 * 1e8 * 1e6 / (1e8 * 1e6) = 1e6
    assert (
        fair_underlying_amount(
            shares=1_000_000,
            price=10**8,
            price_adapter_decimals=8,
            token_decimals=6,
            underlying_decimals=6,
        )
        == 1_000_000
    )


def test_cost_pct_buy_and_sell():
    assert cost_pct(execution=110, fair=100, side="buy") == pytest.approx(0.1)
    assert cost_pct(execution=90, fair=100, side="sell") == pytest.approx(0.1)
    assert cost_pct(execution=110, fair=100, side="sell") == pytest.approx(-0.1)
    with pytest.raises(ValueError, match="fair_underlying"):
        cost_pct(execution=1, fair=0)
    with pytest.raises(ValueError, match="side"):
        cost_pct(execution=1, fair=1, side="hold")  # type: ignore[arg-type]


def test_get_cost_quantizes_float_noise_to_token_decimals():
    """Float USD→size conversion must not raise on excess fractional digits."""
    from decimal import Decimal

    from orion_finance_sdk_py.costs.estimator import _quantize_human_size
    from orion_finance_sdk_py.utils import to_base_units

    q = _quantize_human_size(0.0011976863350237987, 8)
    assert q == Decimal("0.00119768")
    assert to_base_units(q, 8) == 119768


def test_state_override_slots_and_packing():
    holder = "0x" + "11" * 20
    spender = "0x" + "33" * 20
    token = "0x" + "aa" * 20
    bal = balance_storage_slot(holder, 0)
    allow = allowance_storage_slot(holder, spender, 1)
    assert bal.startswith("0x") and len(bal) == 66
    assert allow.startswith("0x") and len(allow) == 66
    assert bal != allow
    assert to_storage_hex(10**18) == "0x" + (10**18).to_bytes(32, "big").hex()

    overrides = build_erc20_state_override(
        token, holder=holder, spender=spender, amount=10**18
    )
    token_c = checksum_address(token)
    assert token_c in overrides
    diff = overrides[token_c]["stateDiff"]
    assert diff[bal] == to_storage_hex(10**18)
    assert diff[allow] == to_storage_hex(10**18)

    # Non-adjacent slots (WBTC/PAXG-style): balance@0, allowance@2
    split = build_erc20_state_override(
        token,
        holder=holder,
        spender=spender,
        amount=10**18,
        balance_mapping_slot=0,
        allowance_mapping_slot=2,
    )
    allow2 = allowance_storage_slot(holder, spender, 2)
    assert allow2 in split[token_c]["stateDiff"]
    assert allow not in split[token_c]["stateDiff"]

    # Vyper HashMap order differs from Solidity (Yearn V3).
    sol = balance_storage_slot(holder, 17, layout="solidity")
    vyp = balance_storage_slot(holder, 17, layout="vyper")
    assert sol != vyp
    assert vyp == "0x" + vyper_mapping_slot(holder, 17).hex()
    vyp_allow = allowance_storage_slot(holder, spender, 18, layout="vyper")
    vyp_ov = build_erc20_state_override(
        token,
        holder=holder,
        spender=spender,
        amount=1,
        balance_mapping_slot=17,
        allowance_mapping_slot=18,
        layout="vyper",
    )
    assert vyp in vyp_ov[token_c]["stateDiff"]
    assert vyp_allow in vyp_ov[token_c]["stateDiff"]


def _mock_mainnet_stack(MockConfig, MockLO, MockRegistry):
    config = MockConfig.return_value
    config.chain_id = 1
    config.w3 = MagicMock()
    config.whitelisted_assets = ["0x" + "11" * 20]
    config.whitelisted_asset_names = ["WETH"]
    config.underlying_asset = "0x" + "22" * 20
    config.liquidity_orchestrator = checksum_address("0x" + "44" * 20)
    config.token_decimals.side_effect = lambda a: 18 if "11" in a.lower() else 6

    adapter = checksum_address("0x" + "33" * 20)
    MockLO.return_value.execution_adapter_of.return_value = adapter
    MockLO.return_value.contract_address = checksum_address("0x" + "44" * 20)

    reg = MockRegistry.return_value
    reg.get_price.return_value = 10**8
    reg.price_adapter_decimals = 8
    return config, adapter


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_get_cost_buy_uses_preview(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with patch.object(est, "_preview_buy", return_value=2_000_000) as preview:
        # fair = 1e18 * 1e8 * 1e6 / (1e8 * 1e18) = 1e6
        out = est.get_cost("WETH", 1.0, block=12_345_678)
    preview.assert_called_once()
    MockLO.return_value.execution_adapter_of.assert_called_once_with(
        checksum_address("0x" + "11" * 20), block=12_345_678
    )
    assert out.size == 1.0
    assert out.swap_size == 1.0
    assert out.side == "buy"
    assert out.fair_underlying == 1_000_000
    assert out.execution_underlying == 2_000_000
    assert out.cost_pct == pytest.approx(1.0)
    assert out.block == 12_345_678


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_get_cost_sell_uses_simulation(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    # fair = 1e6; receive 900k → cost_pct = (1e6 - 9e5) / 1e6 = 0.1
    with patch.object(est, "_simulate_sell", return_value=900_000) as sim:
        out = est.get_cost("WETH", 1.0, side="sell", block=99)
    sim.assert_called_once()
    assert out.side == "sell"
    assert out.fair_underlying == 1_000_000
    assert out.execution_underlying == 900_000
    assert out.cost_pct == pytest.approx(0.1)
    assert out.block == 99


@patch("orion_finance_sdk_py.costs.estimator.probe_erc20_overrides")
@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_simulate_sell_passes_from_and_state_override(
    MockConfig, MockLO, MockRegistry, mock_probe
):
    config, adapter = _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    lo = config.liquidity_orchestrator
    asset = checksum_address("0x" + "11" * 20)
    overrides = {asset: {"stateDiff": {"0x" + "00" * 32: to_storage_hex(1)}}}
    mock_probe.return_value = overrides

    est = ExecutionCostEstimator()
    sell_fn = MagicMock()
    sell_fn.call.return_value = 900_000
    contract = MagicMock()
    contract.functions.sell.return_value = sell_fn

    with patch.object(est, "_adapter_contract", return_value=contract):
        out = est._simulate_sell(adapter, asset, 10**18, block=42)

    assert out == 900_000
    mock_probe.assert_called_once()
    assert mock_probe.call_args.kwargs["holder"] == lo
    assert mock_probe.call_args.kwargs["spender"] == adapter
    assert mock_probe.call_args.kwargs["amount"] == 10**18
    sell_fn.call.assert_called_once_with(
        {"from": lo},
        block_identifier=42,
        state_override=overrides,
    )


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_rejects_invalid_side(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with pytest.raises(ValueError, match="side"):
        est.get_cost("WETH", 1.0, side="hold")


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_rejects_non_int_shares(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with pytest.raises(TypeError, match="shares must be an int"):
        est.get_cost("WETH", 1.0, shares=1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="shares must be an int"):
        est.get_cost("WETH", 1.0, shares=True)  # type: ignore[arg-type]


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_rejects_negative_or_zero_size(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with pytest.raises(ValueError, match="size must be a positive"):
        est.get_cost("WETH", 0.0)
    with pytest.raises(ValueError, match="size must be a positive"):
        est.get_cost("WETH", -1.0)


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_netting_reduces_swap_size_not_cost_linearly(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    nominal = 2.0
    eta = 0.5

    with patch.object(est, "_preview_buy") as preview:
        preview.side_effect = [
            1_100_000,  # netted residual of 1.0
            1_100_000,  # direct size 1.0
            1_300_000,  # unnetted size 2.0
        ]
        netted = est.get_cost("WETH", nominal, netting_eta=eta)
        direct = est.get_cost("WETH", (1.0 - eta) * nominal, netting_eta=0.0)
        unnetted = est.get_cost("WETH", nominal)

    assert netted.swap_size == pytest.approx((1.0 - eta) * nominal)
    assert netted.cost_pct == pytest.approx(direct.cost_pct, rel=1e-9)
    assert netted.cost_pct != pytest.approx(unnetted.cost_pct * (1.0 - eta))
    assert preview.call_args_list[0].args[2] == pytest.approx(10**18)
    assert preview.call_args_list[1].args[2] == pytest.approx(10**18)
    assert preview.call_args_list[2].args[2] == pytest.approx(2 * 10**18)


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_sell_netting_and_numeraire(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with patch.object(est, "_simulate_sell", return_value=900_000) as sim:
        netted = est.get_cost("WETH", 2.0, side="sell", netting_eta=0.5)
    assert netted.side == "sell"
    assert netted.swap_size == pytest.approx(1.0)
    sim.assert_called_once()
    assert sim.call_args.args[2] == pytest.approx(10**18)

    full = est.get_cost("WETH", 1.0, side="sell", netting_eta=1.0)
    assert full.swap_size == 0.0
    assert full.cost_pct == 0.0
    assert full.side == "sell"


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_full_netting_is_zero_cost(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    cost = est.get_cost("WETH", 1.0, netting_eta=1.0)
    assert cost.swap_size == 0.0
    assert cost.shares == 0
    assert cost.cost_pct == 0.0
    MockLO.return_value.execution_adapter_of.assert_not_called()


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_underlying_numeraire_is_zero_cost(MockConfig, MockLO, MockRegistry):
    """Trading the underlying with itself is a no-op → cost_pct = 0."""
    config = MockConfig.return_value
    config.chain_id = 1
    config.w3 = MagicMock()
    underlying = "0x" + "22" * 20
    config.whitelisted_assets = [underlying]
    config.whitelisted_asset_names = ["USDC"]
    config.underlying_asset = underlying
    config.liquidity_orchestrator = checksum_address("0x" + "44" * 20)
    config.token_decimals.return_value = 6
    MockRegistry.return_value.get_price.return_value = 10**8
    MockRegistry.return_value.price_adapter_decimals = 8

    est = ExecutionCostEstimator()
    out = est.get_cost(underlying, 100.0, side="sell")
    assert out.cost_pct == 0.0
    assert out.side == "sell"
    assert out.execution_underlying == out.fair_underlying == out.shares
    assert out.execution_adapter == ""
    MockLO.return_value.execution_adapter_of.assert_not_called()


@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_rejects_non_mainnet(MockConfig):
    MockConfig.return_value.chain_id = 11155111
    with pytest.raises(ValueError, match="mainnet"):
        ExecutionCostEstimator()


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_netting_eta_must_be_unit_interval(MockConfig, MockLO, MockRegistry):
    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    with pytest.raises(ValueError, match="netting_eta"):
        est.get_cost("WETH", 0.01, netting_eta=-0.1)
    with pytest.raises(ValueError, match="netting_eta"):
        est.get_cost("WETH", 0.01, netting_eta=1.1)


def test_execution_adapter_of_rejects_zero():
    from orion_finance_sdk_py.contracts import LiquidityOrchestrator

    lo = object.__new__(LiquidityOrchestrator)
    lo.contract = MagicMock()
    lo.contract.functions.executionAdapterOf.return_value = MagicMock()
    with patch(
        "orion_finance_sdk_py.contracts._call_view", return_value=ZERO_ADDRESS
    ) as call_view:
        with pytest.raises(ValueError, match="is not whitelisted"):
            LiquidityOrchestrator.execution_adapter_of(
                lo, "0x" + "11" * 20, block=99
            )
    assert call_view.call_args.kwargs.get("block_identifier") == 99


@patch("orion_finance_sdk_py.costs.estimator.PriceAdapterRegistry")
@patch("orion_finance_sdk_py.costs.estimator.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.costs.estimator.OrionConfig")
def test_module_get_cost_uses_default_estimator(MockConfig, MockLO, MockRegistry):
    import orion_finance_sdk_py.costs.estimator as estimator_mod

    _mock_mainnet_stack(MockConfig, MockLO, MockRegistry)
    est = ExecutionCostEstimator()
    estimator_mod._DEFAULT_ESTIMATOR = est
    with patch.object(est, "get_cost", return_value=MagicMock()) as mocked:
        get_cost("WETH", 1.0, netting_eta=0.1, side="sell")
    mocked.assert_called_once_with(
        "WETH", 1.0, side="sell", netting_eta=0.1, block=None, shares=None
    )
    estimator_mod._DEFAULT_ESTIMATOR = None
