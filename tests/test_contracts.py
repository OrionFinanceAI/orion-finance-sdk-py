"""Tests for the contracts module."""

import json
import os
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionEncryptedVault,
    OrionSmartContract,
    OrionTransparentVault,
    OrionVault,
    PriceAdapterRegistry,
    SystemNotIdleError,
    TransactionResult,
    VaultFactory,
    _call_view,
    _get_view_call_tx,
    load_contract_abi,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS, VaultType


@pytest.fixture
def mock_w3():
    """Mock Web3 instance."""
    with (
        patch("orion_finance_sdk_py.contracts.Web3") as MockWeb3,
        patch("orion_finance_sdk_py.contracts.make_http_provider") as mock_provider,
    ):
        mock_provider.return_value = MagicMock()

        # Setup the mock instance
        w3_instance = MagicMock()
        MockWeb3.return_value = w3_instance
        # Mock chain ID
        w3_instance.eth.chain_id = 11155111

        # Mock eth.contract
        contract_mock = MagicMock()
        w3_instance.eth.contract.return_value = contract_mock

        # Mock transaction signing and sending
        w3_instance.eth.get_transaction_count.return_value = 0
        w3_instance.eth.gas_price = 1000000000
        w3_instance.eth.account.from_key.return_value = MagicMock(address="0xDeployer")

        # Mock balance (default sufficient)
        w3_instance.eth.get_balance.return_value = 10**18

        signed_tx = MagicMock()
        signed_tx.raw_transaction = b"raw_tx"
        w3_instance.eth.account.from_key.return_value.sign_transaction.return_value = (
            signed_tx
        )

        w3_instance.eth.send_raw_transaction.return_value = b"\x00" * 32

        # Mock receipt
        receipt = MagicMock()
        receipt.status = 1
        receipt.transactionHash = b"\x00" * 32
        receipt.logs = []
        # Support dict access too
        receipt.__getitem__ = lambda self, key: getattr(self, key)

        w3_instance.eth.wait_for_transaction_receipt.return_value = receipt

        # Mock to_checksum_address to return the input string
        MockWeb3.to_checksum_address.side_effect = lambda x: x

        yield w3_instance


def test_call_view_retries_connection_error():
    """_call_view retries transient ConnectionError then succeeds."""
    fn = MagicMock()
    fn.call.side_effect = [ConnectionError("reset"), "ok"]

    with patch("orion_finance_sdk_py.rpc.time.sleep"):
        assert _call_view(fn) == "ok"
    assert fn.call.call_count == 2


@pytest.fixture
def mock_load_abi():
    """Mock load_contract_abi to avoid file I/O."""
    with patch("orion_finance_sdk_py.contracts.load_contract_abi") as mock:
        mock.return_value = [{"type": "function", "name": "test"}]
        yield mock


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    env_vars = {
        "RPC_URL": "http://localhost:8545",
        "CHAIN_ID": "11155111",
        "STRATEGIST_ADDRESS": "0xStrategist",
        "CURATOR_ADDRESS": "0xCurator",
        "MANAGER_PRIVATE_KEY": "0xPrivate",
        "STRATEGIST_PRIVATE_KEY": "0xPrivate",
        "LP_PRIVATE_KEY": "0xPrivate",
        "CURATOR_PRIVATE_KEY": "0xPrivate",
        "ORION_VAULT_ADDRESS": "0xVault",
    }
    with patch.dict(os.environ, env_vars):
        yield


class TestLoadContractAbi:
    """Tests for load_contract_abi and _get_view_call_tx."""

    def test_load_contract_abi_from_package(self):
        """Load ABI from package resources (normal path)."""
        abi = load_contract_abi("OrionConfig")
        assert isinstance(abi, list)
        assert len(abi) > 0

    def test_load_contract_abi_fallback(self):
        """Load ABI from local path when package resources fail."""
        with patch("orion_finance_sdk_py.contracts.resources.files") as mock_files:
            mock_files.return_value.joinpath.return_value.open.side_effect = (
                FileNotFoundError
            )
            mock_f = MagicMock()
            mock_f.read.return_value = json.dumps(
                {"abi": [{"type": "function", "name": "test"}]}
            )
            mock_f.__enter__.return_value = mock_f
            mock_f.__exit__.return_value = None
            with patch("builtins.open", return_value=mock_f):
                abi = load_contract_abi("OrionConfig")
                assert abi == [{"type": "function", "name": "test"}]

    def test_get_view_call_tx_without_env(self):
        """_get_view_call_tx returns empty dict when ORION_FORCE_VIEW_GAS not set."""
        with patch.dict(os.environ, {"ORION_FORCE_VIEW_GAS": ""}, clear=False):
            result = _get_view_call_tx()
        assert result == {}

    def test_get_view_call_tx_with_env(self):
        """_get_view_call_tx returns gas dict when ORION_FORCE_VIEW_GAS is set."""
        with patch.dict(os.environ, {"ORION_FORCE_VIEW_GAS": "1"}, clear=False):
            result = _get_view_call_tx()
        assert result == {"gas": 15_000_000}

    def test_load_contract_abi_importlib_resources_success(self):
        """Primary path: resources.files().open() returns JSON (covers package-data return)."""
        payload = json.dumps({"abi": [{"type": "function", "name": "primary"}]})
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = StringIO(payload)
        mock_cm.__exit__.return_value = None
        with patch("orion_finance_sdk_py.contracts.resources.files") as mock_files:
            mock_files.return_value.joinpath.return_value.open.return_value = mock_cm
            abi = load_contract_abi("OrionConfig")
        assert abi == [{"type": "function", "name": "primary"}]


class TestOrionSmartContract:
    """Tests for OrionSmartContract base class."""

    def test_init(self, mock_w3, mock_load_abi, mock_env):
        """Test initialization."""
        contract = OrionSmartContract("TestContract", "0xAddress")
        assert contract.w3 == mock_w3
        assert contract.contract_name == "TestContract"
        assert contract.contract_address == "0xAddress"

    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_wait_for_transaction_receipt(self, mock_w3):
        """Test waiting for receipt."""
        contract = OrionSmartContract("TestContract", "0xAddress")
        contract._wait_for_transaction_receipt("0xHash")
        mock_w3.eth.wait_for_transaction_receipt.assert_called_with(
            "0xHash", timeout=120
        )

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_decode_logs(self):
        """Test log decoding."""
        contract = OrionSmartContract("TestContract", "0xAddress")

        # Setup event mock
        event_mock = MagicMock()
        event_mock.process_log.return_value = MagicMock(
            event="TestEvent",
            args={"arg1": 1},
            address="0xAddress",
            blockHash=b"hash",
            blockNumber=1,
            logIndex=0,
            transactionHash=b"txhash",
            transactionIndex=0,
        )
        contract.contract.events = [event_mock]

        # TxReceipt / LogReceipt are dict-like (TypedDict); production uses receipt["logs"] and log["address"].
        log_entry = {"address": "0xAddress"}
        receipt = {"logs": [log_entry]}

        logs = contract._decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0]["event"] == "TestEvent"

        # Test ignoring logs from other contracts
        log_entry_other = {"address": "0xOther"}
        receipt = {"logs": [log_entry_other]}
        logs = contract._decode_logs(receipt)
        assert len(logs) == 0

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi")
    def test_init_load_dotenv_restores_rpc_url(self):
        """When RPC_URL is unset, load_dotenv can populate it (lines 76–79)."""
        saved = dict(os.environ)
        try:
            os.environ.pop("RPC_URL", None)

            def _inject_rpc(*_a, **_k):
                os.environ["RPC_URL"] = "http://localhost:8545"

            with patch(
                "orion_finance_sdk_py.contracts.load_dotenv", side_effect=_inject_rpc
            ):
                c = OrionSmartContract("TestContract", "0xAddress")
            assert c.w3 is not None
        finally:
            os.environ.clear()
            os.environ.update(saved)

    @pytest.mark.usefixtures("mock_load_abi")
    def test_init_no_rpc_raises_when_no_default(self):
        """No RPC_URL and public RPC cascade fails: ValueError."""
        saved_env = dict(os.environ)
        try:
            os.environ.pop("RPC_URL", None)
            with (
                patch("orion_finance_sdk_py.contracts.load_dotenv"),
                patch(
                    "orion_finance_sdk_py.contracts.pick_default_rpc",
                    return_value=None,
                ),
                pytest.raises(ValueError, match="RPC_URL environment variable"),
            ):
                OrionSmartContract("TestContract", "0xAddress")
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi")
    def test_init_uses_default_public_rpc_when_no_rpc_url(self):
        """When RPC_URL is unset, use pick_default_rpc()."""
        saved_env = dict(os.environ)
        try:
            os.environ.pop("RPC_URL", None)
            with (
                patch("orion_finance_sdk_py.contracts.load_dotenv"),
                patch(
                    "orion_finance_sdk_py.contracts.pick_default_rpc",
                    return_value="https://1rpc.io/sepolia",
                ) as mock_pick,
            ):
                c = OrionSmartContract("TestContract", "0xAddress")
            mock_pick.assert_called_once()
            assert c.w3 is not None
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_decode_logs_skips_non_matching_event_then_decodes(self):
        """First event.process_log fails; second succeeds (lines 208–210 continue/break)."""
        contract = OrionSmartContract("TestContract", "0xAddress")
        bad = MagicMock()
        bad.process_log.side_effect = ValueError("no match")
        good = MagicMock()
        good.process_log.return_value = MagicMock(
            event="Matched",
            args={},
            address="0xAddress",
            blockHash=b"\x01" * 32,
            blockNumber=1,
            logIndex=0,
            transactionHash=b"\x02" * 32,
            transactionIndex=0,
        )
        contract.contract.events = [bad, good]
        receipt = {"logs": [{"address": "0xAddress"}]}
        logs = contract._decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0]["event"] == "Matched"


class TestOrionConfig:
    """Tests for OrionConfig."""

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_properties(self):
        """Test property accessors."""
        config = OrionConfig()

        # Setup mock returns
        config.contract.functions.strategistIntentDecimals().call.return_value = 18
        config.contract.functions.riskFreeRate().call.return_value = 500
        config.contract.functions.getAllWhitelistedAssets().call.return_value = [
            "0xA",
            "0xB",
        ]

        # Helper for side_effect
        def get_vaults(vault_type):
            mock_call = MagicMock()
            if vault_type == 0:
                mock_call.call.return_value = ["0xV1"]
            else:
                mock_call.call.return_value = ["0xV2"]
            return mock_call

        config.contract.functions.getAllOrionVaults.side_effect = get_vaults

        config.contract.functions.isSystemIdle().call.return_value = True

        assert config.strategist_intent_decimals == 18
        assert config.manager_intent_decimals == 18
        assert config.risk_free_rate == 500
        assert config.whitelisted_assets == ["0xA", "0xB"]
        assert config.get_investment_universe == ["0xA", "0xB"]
        assert config.orion_transparent_vaults == ["0xV1"]
        assert config.orion_encrypted_vaults == ["0xV2"]
        assert config.is_system_idle() is True

        config.contract.functions.isWhitelisted("0xToken").call.return_value = True
        assert config.is_whitelisted("0xToken") is True

        config.contract.functions.isWhitelistedManager(
            "0xManager"
        ).call.return_value = True
        assert config.is_whitelisted_manager("0xManager") is True

        config.contract.functions.underlyingAsset().call.return_value = "0xUnderlying"
        assert config.underlying_asset == "0xUnderlying"

        token = "0x1111111111111111111111111111111111111111"
        config.contract.functions.tokenDecimals(token).call.return_value = 18
        assert config.token_decimals(token) == 18

        config.contract.functions.isOrionVault("0xVaultAddr").call.return_value = True
        assert config.is_orion_vault("0xVaultAddr") is True

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_v2_properties(self):
        """Test v2.0.0 OrionConfig properties."""
        config = OrionConfig()

        config.contract.functions.minDepositAmount().call.return_value = 100
        assert config.min_deposit_amount == 100

        config.contract.functions.minRedeemAmount().call.return_value = 50
        assert config.min_redeem_amount == 50

        config.contract.functions.nettingFeeCoefficient().call.return_value = 5
        assert config.netting_fee_coefficient == 5

        config.contract.functions.rsFeeCoefficient().call.return_value = 10
        assert config.rs_fee_coefficient == 10

        config.contract.functions.feeChangeCooldownDuration().call.return_value = 86400
        assert config.fee_change_cooldown_duration == 86400

        config.contract.functions.maxFulfillBatchSize().call.return_value = 50
        assert config.max_fulfill_batch_size == 50

        config.contract.functions.getAllWhitelistedAssetNames().call.return_value = [
            "USDC",
            "WETH",
        ]
        assert config.whitelisted_asset_names == ["USDC", "WETH"]

        config.contract.functions.priceAdapterRegistry().call.return_value = (
            "0xPriceRegistry"
        )
        assert config.price_adapter_registry == "0xPriceRegistry"

        config.contract.functions.priceAdapterDecimals().call.return_value = 8
        assert config.price_adapter_decimals == 8

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi")
    def test_init_invalid_chain(self):
        """Test init with invalid chain ID (chain 1 not in CHAIN_CONFIG)."""
        # Force address from CHAIN_ID so we hit the "unsupported chain" path
        with patch.dict(
            os.environ,
            {
                "CHAIN_ID": "1",
                "RPC_URL": "http://localhost",
                "ORION_CONFIG_ADDRESS": "",  # unset so OrionConfig uses CHAIN_ID
            },
            clear=False,
        ):
            with pytest.raises(ValueError, match="Unsupported CHAIN_ID"):
                OrionConfig()

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi")
    def test_init_chain_mismatch(self):
        """Test init with chain ID mismatch warning."""
        # mock_w3 provides chain_id=11155111
        with patch.dict(os.environ, {"CHAIN_ID": "1", "RPC_URL": "http://localhost"}):
            with patch("builtins.print") as mock_print:
                # We instantiate a base contract which does the check
                OrionSmartContract("Test", "0xAddress")
                mock_print.assert_called_with(
                    "⚠️ Warning: CHAIN_ID in env (1) does not match RPC chain ID (11155111)"
                )

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi")
    def test_init_invalid_chain_id_env(self):
        """Test init with non-integer CHAIN_ID in env prints warning."""
        with patch.dict(
            os.environ, {"CHAIN_ID": "invalid", "RPC_URL": "http://localhost"}
        ):
            with patch("builtins.print") as mock_print:
                OrionSmartContract("Test", "0xAddress")
                mock_print.assert_called_with(
                    "⚠️ Warning: Invalid CHAIN_ID in env: invalid"
                )

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_decode_logs_exception(self):
        """Test decoding logs with exception."""
        contract = OrionSmartContract("TestContract", "0xAddress")

        event_mock = MagicMock()
        event_mock.process_log.side_effect = Exception("Decode error")
        contract.contract.events = [event_mock]

        receipt = MagicMock()
        log_mock = MagicMock()
        log_mock.address = "0xAddress"
        receipt.logs = [log_mock]

        logs = contract._decode_logs(receipt)
        assert len(logs) == 0


class TestLiquidityOrchestrator:
    """Tests for LiquidityOrchestrator."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_init_and_properties(self, MockConfig):
        MockConfig.return_value.contract.functions.liquidityOrchestrator().call.return_value = "0xLiquidity"

        lo = LiquidityOrchestrator()
        assert lo.contract_address == "0xLiquidity"

        lo.contract.functions.targetBufferRatio().call.return_value = 1000
        assert lo.target_buffer_ratio == 1000

        lo.contract.functions.slippageTolerance().call.return_value = 50
        assert lo.slippage_tolerance == 50

        lo.contract.functions.epochDuration().call.return_value = 3600
        assert lo.epoch_duration == 3600


class TestPriceAdapterRegistry:
    """Tests for PriceAdapterRegistry."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_init_from_config_and_get_price(self, MockConfig):
        MockConfig.return_value.price_adapter_registry = "0xRegistry"

        registry = PriceAdapterRegistry()
        assert registry.contract_address == "0xRegistry"

        registry.contract.functions.getPrice("0xA").call.return_value = 1_000_000
        assert registry.get_price("0xA") == 1_000_000

        registry.contract.functions.priceAdapterDecimals().call.return_value = 8
        assert registry.price_adapter_decimals == 8

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_get_prices_full_universe(self, MockConfig):
        MockConfig.return_value.price_adapter_registry = "0xRegistry"
        MockConfig.return_value.whitelisted_assets = ["0xA", "0xB"]

        registry = PriceAdapterRegistry()

        def get_price_side_effect(asset):
            mock_call = MagicMock()
            mock_call.call.return_value = {"0xA": 100, "0xB": 200}[asset]
            return mock_call

        registry.contract.functions.getPrice.side_effect = get_price_side_effect

        prices = registry.get_prices()
        assert prices == {"0xA": 100, "0xB": 200}

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_get_price_at_block_passes_block_identifier(self, MockConfig):
        MockConfig.return_value.price_adapter_registry = "0xRegistry"
        registry = PriceAdapterRegistry()

        call_mock = MagicMock()
        call_mock.call.return_value = 42
        registry.contract.functions.getPrice.return_value = call_mock

        assert registry.get_price("0xA", block=1_000_000) == 42
        call_mock.call.assert_called()
        _, kwargs = call_mock.call.call_args
        assert kwargs.get("block_identifier") == 1_000_000

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_init_with_explicit_address(self):
        registry = PriceAdapterRegistry(contract_address="0xExplicit")
        assert registry.contract_address == "0xExplicit"

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_get_prices_subset(self, MockConfig):
        """get_prices(assets=...) only queries the requested subset."""
        MockConfig.return_value.price_adapter_registry = "0xRegistry"
        MockConfig.return_value.whitelisted_assets = ["0xA", "0xB", "0xC"]

        registry = PriceAdapterRegistry()

        def get_price_side_effect(asset):
            mock_call = MagicMock()
            mock_call.call.return_value = {"0xA": 100, "0xB": 200, "0xC": 300}[asset]
            return mock_call

        registry.contract.functions.getPrice.side_effect = get_price_side_effect

        prices = registry.get_prices(assets=["0xA", "0xC"])
        assert prices == {"0xA": 100, "0xC": 300}
        assert registry.contract.functions.getPrice.call_count == 2
        called_assets = [
            call.args[0] for call in registry.contract.functions.getPrice.call_args_list
        ]
        assert called_assets == ["0xA", "0xC"]

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_price_history_daily(self, MockConfig):
        """price_history samples daily and returns timestamp/block/prices."""
        MockConfig.return_value.price_adapter_registry = "0xRegistry"
        MockConfig.return_value.whitelisted_assets = ["0xA", "0xB"]

        registry = PriceAdapterRegistry()

        start_ts = 1_700_000_000
        day = 86_400
        blocks = {
            10: {"timestamp": start_ts},
            20: {"timestamp": start_ts + day},
            30: {"timestamp": start_ts + 2 * day},
        }
        registry.w3.eth.block_number = 30

        def get_block(n):
            if n in blocks:
                return blocks[n]
            return {"timestamp": start_ts + (n - 10) * (2 * day) // 20}

        registry.w3.eth.get_block.side_effect = get_block
        registry.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: {
                start_ts: 10,
                start_ts + day: 20,
                start_ts + 2 * day: 30,
            }.get(ts, 10)
        )

        def get_prices_side_effect(block=None, assets=None):
            return {
                "0xA": 100 + (block or 0),
                "0xB": 200 + (block or 0),
            }

        registry.get_prices = MagicMock(side_effect=get_prices_side_effect)

        series = registry.price_history(start=10, end=30, interval="1d")
        assert len(series) >= 2
        assert set(series[0].keys()) == {"timestamp", "block", "prices"}
        assert series[0]["block"] == 10
        assert series[-1]["block"] == 30
        assert "0xA" in series[0]["prices"]
        assert "0xB" in series[0]["prices"]

        with pytest.raises(ValueError, match="Unsupported interval"):
            registry.price_history(start=10, end=30, interval="1h")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_price_history_assets_subset(self, MockConfig):
        """price_history forwards assets= subset to get_prices."""
        MockConfig.return_value.price_adapter_registry = "0xRegistry"
        MockConfig.return_value.whitelisted_assets = ["0xA", "0xB", "0xC"]

        registry = PriceAdapterRegistry()
        registry._daily_sample_points = MagicMock(
            return_value=[(1_700_000_000, 10), (1_700_086_400, 20)]
        )
        registry.get_prices = MagicMock(return_value={"0xA": 100})

        series = registry.price_history(start=10, end=20, interval="1d", assets=["0xA"])
        assert len(series) == 2
        assert all(
            call.kwargs.get("assets") == ["0xA"]
            for call in registry.get_prices.call_args_list
        )
        assert all(point["prices"] == {"0xA": 100} for point in series)


class TestVaultFactory:
    """Tests for VaultFactory."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault(self, MockConfig):
        """Test vault creation."""
        # Mock OrionConfig
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True  # Whitelisted
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)
        assert factory.contract_address == "0xTVF"

        # Mock contract calls
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}

        result = factory.create_orion_vault(
            name="Test",
            symbol="TST",
            fee_type=0,
            performance_fee=1000,
            management_fee=100,
            deposit_access_control=ZERO_ADDRESS,
            strategist_address="0xStrategist",
        )

        assert isinstance(result, TransactionResult)
        assert result.receipt["status"] == 1

        # Verify call arguments (checking if strategist address from env is used)
        factory.contract.functions.createVault.assert_called()
        args = factory.contract.functions.createVault.call_args[0]
        assert len(args) == 9
        assert args[0] == "0xStrategist"  # First arg is strategist
        assert args[6] == ZERO_ADDRESS
        assert args[7] == ZERO_ADDRESS
        assert args[8] == ZERO_ADDRESS

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault_passes_holder_and_transfer_acl(self, MockConfig):
        """createVault calldata includes holder and transfer ACL addresses."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}

        factory.create_orion_vault(
            strategist_address="0xStrategist",
            name="Test",
            symbol="TST",
            fee_type=0,
            performance_fee=0,
            management_fee=0,
            deposit_access_control="0xDeposit",
            holder_access_control="0xHolder",
            transfer_access_control="0xTransfer",
        )

        args = factory.contract.functions.createVault.call_args[0]
        assert len(args) == 9
        assert args[6] == "0xDeposit"
        assert args[7] == "0xHolder"
        assert args[8] == "0xTransfer"

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_manager_not_whitelisted(self, MockConfig, mock_w3):
        """Test vault creation fails when manager is not whitelisted."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = False  # Not whitelisted
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"

        factory = VaultFactory(VaultType.TRANSPARENT)

        with pytest.raises(ValueError, match="is not whitelisted to create vaults"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_insufficient_balance(self, MockConfig, mock_w3):
        """Test vault creation fails with insufficient balance."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)

        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        mock_w3.eth.gas_price = 1000000000
        # Cost ~ 1.2 * 10^14
        mock_w3.eth.get_balance.return_value = 0  # Not enough

        with pytest.raises(ValueError, match="Insufficient ETH balance"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault_system_busy(self):
        """Test system busy check."""
        with patch("orion_finance_sdk_py.contracts.OrionConfig") as MockConfig:
            MockConfig.return_value.is_system_idle.return_value = False
            MockConfig.return_value.is_whitelisted_manager.return_value = True
            # Mock transparent factory address
            MockConfig.return_value.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
            MockConfig.return_value.max_performance_fee = 3000
            MockConfig.return_value.max_management_fee = 300

            factory = VaultFactory(VaultType.TRANSPARENT)

            with pytest.raises(SystemNotIdleError):
                factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault_invalid_name_symbol(self):
        """Test vault creation fails with too long name or symbol."""
        factory = VaultFactory(VaultType.TRANSPARENT)

        # Name too long (> 26 bytes)
        with pytest.raises(ValueError, match="exceeds maximum length of 26 bytes"):
            factory.create_orion_vault("0xStrategist", "A" * 27, "SYM", 0, 0, 0)

        # Symbol too long (> 4 bytes)
        with pytest.raises(ValueError, match="exceeds maximum length of 4 bytes"):
            factory.create_orion_vault("0xStrategist", "Name", "SYMB1", 0, 0, 0)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_get_vault_address(self):
        """Test extracting address from logs."""
        with patch("orion_finance_sdk_py.contracts.OrionConfig") as MockConfig:
            MockConfig.return_value.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
            factory = VaultFactory(VaultType.TRANSPARENT)

        result = TransactionResult(
            tx_hash="0x",
            receipt=MagicMock(),
            decoded_logs=[
                {"event": "OtherEvent"},
                {"event": "OrionVaultCreated", "args": {"vault": "0xNewVault"}},
            ],
        )

        addr = factory.get_vault_address_from_result(result)
        assert addr == "0xNewVault"

        result.decoded_logs = []
        assert factory.get_vault_address_from_result(result) is None

        # Logs present but no OrionVaultCreated event returns None
        result.decoded_logs = [{"event": "OtherEvent"}, {"event": "AnotherEvent"}]
        assert factory.get_vault_address_from_result(result) is None

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault_unsupported_type(self):
        """Test VaultFactory with unsupported vault type raises."""
        with patch("orion_finance_sdk_py.contracts.OrionConfig") as MockConfig:
            MockConfig.return_value.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
            with pytest.raises(ValueError, match="Unsupported vault type"):
                VaultFactory(vault_type="unknown")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_encrypted_vault_factory_resolves_address(self, MockConfig):
        """Encrypted VaultFactory uses encryptedVaultFactory() and EncryptedVaultFactory ABI."""
        config_instance = MockConfig.return_value
        config_instance.contract.functions.encryptedVaultFactory().call.return_value = (
            "0xEVF"
        )

        factory = VaultFactory(VaultType.ENCRYPTED)
        assert factory.contract_address == "0xEVF"
        assert factory.contract_name == "EncryptedVaultFactory"
        assert factory.vault_type == VaultType.ENCRYPTED

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_create_orion_vault_fee_exceeds_max(self, MockConfig):
        """Test vault creation fails when performance or management fee exceeds max."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000

        with pytest.raises(ValueError, match=r"Performance fee .* exceeds maximum"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 3001, 0)
        with pytest.raises(ValueError, match=r"Management fee .* exceeds maximum"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 301)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_whitelist_revert(self, MockConfig, mock_w3):
        """Test vault creation when tx reverts with not-whitelisted selector."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.account.from_key.return_value.sign_transaction.return_value = (
            MagicMock(raw_transaction=b"raw")
        )
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.side_effect = Exception(
            "revert 0xea8e4eb5..."
        )

        with pytest.raises(ValueError, match="not whitelisted to create vaults"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_wait_receipt_reraises_other_error(
        self, MockConfig, mock_w3
    ):
        """Non-whitelist receipt errors propagate (line 513: raise e)."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.account.from_key.return_value.sign_transaction.return_value = (
            MagicMock(raw_transaction=b"raw")
        )
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.side_effect = Exception("rpc timeout")

        with pytest.raises(Exception, match="rpc timeout"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_receipt_failed(self, MockConfig, mock_w3):
        """Test vault creation when receipt status is 0."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.account.from_key.return_value.sign_transaction.return_value = (
            MagicMock(raw_transaction=b"raw")
        )
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }

        with pytest.raises(Exception, match="Transaction failed with status"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 0, 0)


class TestOrionVaults:
    """Tests for OrionVault and subclasses."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_orion_vault_methods(self, MockConfig, mock_w3):
        """Test base methods."""
        # Mock config for update_fee_model calls
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()

        # Mock fee limit calls
        vault.contract.functions.MAX_PERFORMANCE_FEE.return_value.call.return_value = (
            3000
        )
        vault.contract.functions.MAX_MANAGEMENT_FEE.return_value.call.return_value = 300

        # Mock role calls
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"

        # Mock tx methods
        vault.contract.functions.updateStrategist.return_value.estimate_gas.return_value = 100
        vault.contract.functions.updateFeeModel.return_value.estimate_gas.return_value = 100
        vault.contract.functions.setDepositAccessControl.return_value.estimate_gas.return_value = 100

        res = vault.update_strategist("0xNew")
        assert res.receipt["status"] == 1

        res = vault.update_fee_model(0, 0, 0)
        assert res.receipt["status"] == 1

        res = vault.set_deposit_access_control("0xControl")
        assert res.receipt["status"] == 1

        res = vault.set_holder_access_control("0xHolder")
        assert res.receipt["status"] == 1
        vault.contract.functions.setHolderAccessControl.assert_called_with("0xHolder")

        res = vault.set_transfer_access_control("0xTransfer")
        assert res.receipt["status"] == 1
        vault.contract.functions.setTransferAccessControl.assert_called_with(
            "0xTransfer"
        )

        # Mock view methods
        vault.contract.functions.totalAssets().call.return_value = 1000

        def convert_side_effect(shares):
            mock_call = MagicMock()
            if shares == 10:
                mock_call.call.return_value = 100
            elif shares == 10**18:
                mock_call.call.return_value = 10**18
            return mock_call

        vault.contract.functions.convertToAssets.side_effect = convert_side_effect

        vault.contract.functions.getPortfolio().call.return_value = (
            ["0xA", "0xB"],
            [100, 200],
        )
        vault.contract.functions.maxDeposit("0xReceiver").call.return_value = 5000
        vault.contract.functions.decimals().call.return_value = 18

        assert vault.total_assets == 1000
        assert vault.convert_to_assets(10) == 100
        assert vault.get_portfolio() == {"0xA": 100, "0xB": 200}
        assert vault.max_deposit("0xReceiver") == 5000
        assert vault.share_price == 10**18

        # Historical share price uses block_identifier
        assert vault.share_price_at(50) == 10**18
        assert vault.total_assets_at(50) == 1000
        assert vault.convert_to_assets(10, block=50) == 100
        assert vault.get_portfolio(block=50) == {"0xA": 100, "0xB": 200}

        with patch(
            "orion_finance_sdk_py.contracts.PriceAdapterRegistry"
        ) as MockRegistry:
            reg = MockRegistry.return_value
            reg.get_prices.return_value = {"0xA": 10**8, "0xB": 10**8}
            reg.price_adapter_decimals = 8
            # values: 100*1e8/1e8=100, 200*1e8/1e8=200 → total 300 → 1/3, 2/3
            assert vault.point_in_time_total_assets() == 300
            pct = vault.get_portfolio_pct_tvl()
            assert abs(pct["0xA"] - 100 / 300) < 1e-9
            assert abs(pct["0xB"] - 200 / 300) < 1e-9

        with patch(
            "orion_finance_sdk_py.contracts.PriceAdapterRegistry"
        ) as MockRegistry:
            reg = MockRegistry.return_value
            reg.get_prices.return_value = {"0xA": 10**8}  # missing 0xB
            reg.price_adapter_decimals = 8
            with pytest.raises(ValueError, match="No PIT price"):
                vault.point_in_time_total_assets()

        with patch(
            "orion_finance_sdk_py.contracts.PriceAdapterRegistry"
        ) as MockRegistry:
            vault.contract.functions.getPortfolio().call.return_value = ([], [])
            reg = MockRegistry.return_value
            reg.get_prices.return_value = {}
            reg.price_adapter_decimals = 8
            assert vault.point_in_time_total_assets() == 0
            assert vault.get_portfolio_pct_tvl() == {}

        config_instance.token_decimals = MagicMock(return_value=6)
        config_instance.underlying_asset = "0xUnderlying"
        vault.contract.functions.pendingVaultFees().call.return_value = 1_000_000
        assert vault.pending_vault_fees == 1.0

        # Test can_request_deposit (permissionless)
        vault.contract.functions.depositAccessControl().call.return_value = ZERO_ADDRESS
        assert vault.can_request_deposit("0xUser") is True

        # Test can_request_deposit (with access control)
        vault.contract.functions.depositAccessControl().call.return_value = "0xAC"
        with patch.object(mock_w3.eth, "contract") as mock_ac_contract:
            mock_ac_instance = mock_ac_contract.return_value
            mock_fn = mock_ac_instance.functions.canRequestDeposit
            mock_fn.return_value.call.return_value = True
            assert vault.can_request_deposit("0xUser") is True
            mock_fn.assert_called_with("0xUser", b"")
            mock_fn.return_value.call.return_value = False
            assert vault.can_request_deposit("0xUser") is False
            mock_fn.assert_called_with("0xUser", b"")

        vault.contract.functions.holderAccessControl().call.return_value = ZERO_ADDRESS
        assert vault.can_hold_shares("0xUser") is True
        vault.contract.functions.transferAccessControl().call.return_value = (
            ZERO_ADDRESS
        )
        assert vault.can_transfer_shares("0xUser") is True

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_orion_vault_explicit_contract_address(self, MockConfig):
        """OrionTransparentVault accepts contract_address without ORION_VAULT_ADDRESS."""
        MockConfig.return_value.is_orion_vault.return_value = True
        saved = os.environ.pop("ORION_VAULT_ADDRESS", None)
        try:
            vault = OrionTransparentVault(contract_address="0xExplicitVault")
        finally:
            if saved is not None:
                os.environ["ORION_VAULT_ADDRESS"] = saved
        assert vault.contract_address == "0xExplicitVault"
        MockConfig.return_value.is_orion_vault.assert_called()

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_block_at_timestamp_binary_search(self):
        """block_at_timestamp returns the latest block with timestamp <= target."""
        contract = OrionSmartContract("TestContract", "0xAddress")

        timestamps = {0: 1000, 1: 1100, 2: 1200, 3: 1300, 4: 1400}
        contract.w3.eth.block_number = 4

        def get_block(n):
            return {"timestamp": timestamps[n]}

        contract.w3.eth.get_block.side_effect = get_block

        assert contract.block_at_timestamp(1250) == 2
        assert contract.block_at_timestamp(1400) == 4
        assert contract.block_at_timestamp(1500) == 4

        with pytest.raises(ValueError, match="before the earliest"):
            contract.block_at_timestamp(500)

        # Bounded search stays within [lo, hi]
        assert contract.block_at_timestamp(1250, lo=1, hi=3) == 2
        with pytest.raises(ValueError, match="lower bound"):
            contract.block_at_timestamp(1050, lo=2, hi=4)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_share_price_history_daily(self, MockConfig):
        """share_price_history samples daily and returns timestamp/block/share_price."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()

        start_ts = 1_700_000_000
        day = 86_400
        blocks = {
            10: {"timestamp": start_ts},
            20: {"timestamp": start_ts + day},
            30: {"timestamp": start_ts + 2 * day},
        }
        vault.w3.eth.block_number = 30

        def get_block(n):
            if n in blocks:
                return blocks[n]
            return {"timestamp": start_ts + (n - 10) * (2 * day) // 20}

        vault.w3.eth.get_block.side_effect = get_block
        vault.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: {
                start_ts: 10,
                start_ts + day: 20,
                start_ts + 2 * day: 30,
            }.get(ts, 10)
        )
        vault.contract.functions.decimals().call.return_value = 18
        vault.w3.eth.get_code.return_value = b"\x60"

        def convert_side_effect(shares):
            mock_call = MagicMock()
            mock_call.call.return_value = shares // (10**16)  # scale down for asserts
            return mock_call

        vault.contract.functions.convertToAssets.side_effect = convert_side_effect

        series = vault.share_price_history(start=10, end=30, interval="1d")
        assert len(series) >= 2
        assert set(series[0].keys()) == {"timestamp", "block", "share_price"}
        assert series[0]["block"] == 10
        assert series[-1]["block"] == 30
        # decimals warmed once for the series
        assert vault.contract.functions.decimals().call.call_count == 1

        with pytest.raises(ValueError, match="Unsupported interval"):
            vault.share_price_history(start=10, end=30, interval="1h")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_share_price_history_skips_pre_deployment(self, MockConfig):
        """share_price_history omits samples from before the vault exists."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()

        start_ts = 1_700_000_000
        day = 86_400
        blocks = {
            10: {"timestamp": start_ts},
            20: {"timestamp": start_ts + day},
            30: {"timestamp": start_ts + 2 * day},
        }
        vault.w3.eth.block_number = 30

        def get_block(n):
            if n in blocks:
                return blocks[n]
            return {"timestamp": start_ts + (n - 10) * (2 * day) // 20}

        vault.w3.eth.get_block.side_effect = get_block
        vault.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: {
                start_ts: 10,
                start_ts + day: 20,
                start_ts + 2 * day: 30,
            }.get(ts, 10)
        )

        def get_code(_addr, block_identifier=None):
            if block_identifier is not None and int(block_identifier) < 20:
                return b""
            return b"\x60"

        vault.w3.eth.get_code.side_effect = get_code
        vault.contract.functions.decimals().call.return_value = 18
        vault.contract.functions.convertToAssets.return_value.call.return_value = 100

        series = vault.share_price_history(start=10, end=30, interval="1d")
        assert [p["block"] for p in series] == [20, 30]

        vault.w3.eth.get_code.side_effect = None
        vault.w3.eth.get_code.return_value = b""
        assert vault.share_price_history(start=10, end=30, interval="1d") == []

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_share_price_at_pre_deployment_error(self, MockConfig):
        """share_price_at explains empty eth_call data before deployment."""
        from web3.exceptions import BadFunctionCallOutput

        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        vault.contract.functions.decimals().call.return_value = 18
        vault.contract.functions.convertToAssets.return_value.call.side_effect = (
            BadFunctionCallOutput("Could not decode convertToAssets()")
        )
        with pytest.raises(ValueError, match="may not have been deployed"):
            vault.share_price_at(50)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_vault_name_symbol_decimals(self, MockConfig):
        """Vault name, symbol, and decimals are readable view properties."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        vault.contract.functions.name().call.return_value = "Alpha Vault"
        vault.contract.functions.symbol().call.return_value = "ALPH"
        vault.contract.functions.decimals().call.return_value = 18

        assert vault.name == "Alpha Vault"
        assert vault.symbol == "ALPH"
        assert vault.decimals == 18
        # Cached after first fetch
        assert vault.symbol == "ALPH"
        assert vault.contract.functions.symbol().call.call_count == 1
        assert vault.decimals == 18
        assert vault.contract.functions.decimals().call.call_count == 1

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_daily_sample_points_bounds_search(self, MockConfig):
        """Daily sampling searches forward from the previous day, not from genesis."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()

        # 5 days, 100 blocks/day, 12s blocks → 86400/12 = 7200 would be realistic;
        # keep the chain tiny for a clear call-count bound.
        start_ts = 1_700_000_000
        day = 86_400
        block_time = 12
        start_block = 1_000_000
        n_days = 5
        end_block = start_block + (n_days * day) // block_time

        def get_block(n):
            n = int(n)
            return {"timestamp": start_ts + (n - start_block) * block_time}

        vault.w3.eth.block_number = end_block
        vault.w3.eth.get_block.side_effect = get_block

        points = vault._daily_sample_points(start_block, end_block)
        assert len(points) >= n_days
        assert points[0][1] == start_block
        assert points[-1][1] == end_block

        # Unbounded binary search from genesis each day would be roughly
        # n_days * log2(end_block) get_block calls (~100+ here). Bounded
        # forward search must stay well under that.
        full_chain_estimate = n_days * max(end_block.bit_length(), 1)
        assert vault.w3.eth.get_block.call_count < full_chain_estimate
        assert vault.w3.eth.get_block.call_count < 80

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_resolve_block_datetime_and_timestamp(self, MockConfig):
        """Naive datetime and unix ints resolve via block_at_timestamp."""
        from datetime import datetime, timezone

        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        vault.block_at_timestamp = MagicMock(return_value=42)

        naive = datetime(2024, 1, 1, 12, 0, 0)
        assert vault._resolve_block(naive) == 42
        vault.block_at_timestamp.assert_called()
        call_ts = vault.block_at_timestamp.call_args[0][0]
        assert call_ts == int(naive.replace(tzinfo=timezone.utc).timestamp())

        vault.block_at_timestamp.reset_mock()
        assert vault._resolve_block(1_700_000_000) == 42
        vault.block_at_timestamp.assert_called_with(1_700_000_000)
        assert vault._resolve_block(99) == 99

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_daily_sample_points_end_defaults_to_tip(self, MockConfig):
        """end=None uses eth.block_number as the tip."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        start_ts = 1_700_000_000
        tip = 20
        vault.w3.eth.block_number = tip
        vault.w3.eth.get_block.side_effect = lambda n: {
            "timestamp": start_ts + (int(n) - 10) * 86_400
        }
        vault.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: 10 if ts <= start_ts else tip
        )
        points = vault._daily_sample_points(10, end=None)
        assert points[-1][1] == tip

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_daily_sample_points_appends_end_when_needed(self, MockConfig):
        """End block is appended when the last daily step did not land on it."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        start_ts = 1_700_000_000
        day = 86_400
        # 1.5 days of blocks so daily cadence lands before end_block.
        blocks = {
            10: {"timestamp": start_ts},
            15: {"timestamp": start_ts + day},
            20: {"timestamp": start_ts + day + day // 2},
        }

        def get_block(n):
            n = int(n)
            if n in blocks:
                return blocks[n]
            return {"timestamp": start_ts + (n - 10) * (day // 10)}

        vault.w3.eth.get_block.side_effect = get_block
        vault.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: {
                start_ts: 10,
                start_ts + day: 15,
            }.get(ts, 15)
        )
        points = vault._daily_sample_points(10, 20)
        assert points[-1][1] == 20
        assert points[-1][0] == start_ts + day + day // 2

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_daily_sample_points_skips_duplicate_blocks(self, MockConfig):
        """Stalled chain: consecutive days resolving to the same block are skipped."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        start_ts = 1_700_000_000
        day = 86_400
        blocks = {
            10: {"timestamp": start_ts},
            20: {"timestamp": start_ts + 3 * day},
        }

        def get_block(n):
            n = int(n)
            if n in blocks:
                return blocks[n]
            return {"timestamp": start_ts}

        vault.w3.eth.get_block.side_effect = get_block
        # Days 1 and 2 still map to start_block; day 3 reaches end.
        vault.block_at_timestamp = MagicMock(
            side_effect=lambda ts, lo=None, hi=None: (
                10 if ts < start_ts + 3 * day else 20
            )
        )
        points = vault._daily_sample_points(10, 20)
        block_nums = [b for _, b in points]
        assert block_nums == [10, 20]
        assert len(points) == len(set(block_nums))

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_earliest_code_block_start_after_end_returns_none(self, MockConfig):
        """_earliest_code_block returns None when start > end."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        assert vault._earliest_code_block(30, 10) is None

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_share_price_history_empty_points(self, MockConfig):
        """share_price_history returns [] when sampling yields no points."""
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        vault._daily_sample_points = MagicMock(return_value=[])
        assert vault.share_price_history(start=10, end=30) == []

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_share_price_history_bad_call_in_loop(self, MockConfig):
        """BadFunctionCallOutput mid-history becomes a ValueError."""
        from web3.exceptions import BadFunctionCallOutput

        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionTransparentVault()
        vault._daily_sample_points = MagicMock(
            return_value=[(1_700_000_000, 10), (1_700_086_400, 20)]
        )
        vault._earliest_code_block = MagicMock(return_value=10)
        vault.contract.functions.decimals().call.return_value = 18
        vault.contract.functions.convertToAssets.return_value.call.side_effect = (
            BadFunctionCallOutput("empty")
        )
        with pytest.raises(ValueError, match="may not have been deployed"):
            vault.share_price_history(start=10, end=20)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_get_intent_normalizes_weights(self, MockConfig):
        """get_intent returns fractional weights scaled by strategist_intent_decimals."""
        MockConfig.return_value.is_orion_vault.return_value = True
        MockConfig.return_value.strategist_intent_decimals = 4
        vault = OrionTransparentVault()
        vault.contract.functions.getIntent().call.return_value = (
            ["0xA", "0xB"],
            [6000, 4000],
        )

        intent = vault.get_intent()
        assert intent == {"0xA": 0.6, "0xB": 0.4}

        vault.contract.functions.getIntent().call.return_value = ([], [])
        assert vault.get_intent() == {}

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_orion_vault_v2_features(self, MockConfig, mock_w3):
        """Test v2.0.0 vault features: async operations and new getters."""
        # Setup config
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True
        config_instance.max_fulfill_batch_size = 10

        vault = OrionTransparentVault()

        # Test new getters
        vault.contract.functions.activeFeeModel.return_value.call.return_value = (
            0,
            1000,
            100,
            0,
        )
        assert vault.active_fee_model == {
            "feeType": 0,
            "performanceFee": 1000,
            "managementFee": 100,
            "highWaterMark": 0,
        }

        vault.contract.functions.pendingDeposit.return_value.call.return_value = 500
        assert vault.pending_deposit() == 500
        vault.contract.functions.pendingDeposit.assert_called_with(
            10
        )  # default batch size

        vault.contract.functions.pendingRedeem.return_value.call.return_value = 200
        assert vault.pending_redeem(20) == 200
        vault.contract.functions.pendingRedeem.assert_called_with(20)

        assert vault.pending_redeem() == 200
        vault.contract.functions.pendingRedeem.assert_called_with(10)

        vault.contract.functions.isDecommissioning.return_value.call.return_value = True
        assert vault.is_decommissioning is True

        # Test async operations
        # request_deposit
        vault.contract.functions.requestDeposit.return_value.build_transaction.return_value = {}
        res = vault.request_deposit(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.requestDeposit.assert_called_with(100)

        vault.contract.functions.requestDepositFor.return_value.build_transaction.return_value = {}
        res = vault.request_deposit_for("0xBeneficiary", 50)
        assert res.receipt["status"] == 1
        vault.contract.functions.requestDepositFor.assert_called_with(
            "0xBeneficiary", 50
        )

        vault.contract.functions.pendingUnderlyingClaim.return_value.call.return_value = 7
        assert vault.pending_underlying_claim("0xUser") == 7

        vault.contract.functions.claimUnderlying.return_value.build_transaction.return_value = {}
        res = vault.claim_underlying()
        assert res.receipt["status"] == 1
        vault.contract.functions.claimUnderlying.assert_called_with()

        # cancel_deposit_request
        vault.contract.functions.cancelDepositRequest.return_value.build_transaction.return_value = {}
        res = vault.cancel_deposit_request(50)
        assert res.receipt["status"] == 1
        vault.contract.functions.cancelDepositRequest.assert_called_with(50)

        # request_redeem
        vault.contract.functions.requestRedeem.return_value.build_transaction.return_value = {}
        res = vault.request_redeem(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.requestRedeem.assert_called_with(100)

        # cancel_redeem_request
        vault.contract.functions.cancelRedeemRequest.return_value.build_transaction.return_value = {}
        res = vault.cancel_redeem_request(50)
        assert res.receipt["status"] == 1
        vault.contract.functions.cancelRedeemRequest.assert_called_with(50)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_request_deposit_receipt_failed(self, MockConfig, mock_w3):
        """_execute_vault_tx raises when receipt status != 1 (line 649)."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.requestDeposit.return_value.build_transaction.return_value = {}
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }

        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.request_deposit(100)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_execute_vault_tx_with_gas_limit(self, MockConfig):
        """Test _execute_vault_tx includes gas in tx_params when gas_limit is provided."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.requestDeposit.return_value.build_transaction.return_value = {}
        vault_w3 = vault.w3
        vault_w3.eth.account.from_key.return_value.address = "0xDeployer"

        gas_limit = 500_000
        res = vault._execute_vault_tx(
            vault.contract.functions.requestDeposit(100),
            error_msg="Private key missing.",
            gas_limit=gas_limit,
        )
        assert res.receipt["status"] == 1
        # build_transaction should have been called with gas=gas_limit in tx_params
        call_args = vault.contract.functions.requestDeposit.return_value.build_transaction.call_args[
            0
        ][0]
        assert call_args.get("gas") == gas_limit

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_can_request_deposit_no_method(self, MockConfig):
        """Test can_request_deposit when contract method is missing."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        # Simulate ABI missing function or call error
        vault.contract.functions.depositAccessControl.side_effect = AttributeError

        assert vault.can_request_deposit("0xUser") is True

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_can_hold_and_can_transfer_shares(self, MockConfig, mock_w3):
        """Holder/transfer ACL views short-circuit on zero and forward otherwise."""
        MockConfig.return_value.orion_transparent_vaults = ["0xVault"]
        vault = OrionTransparentVault()

        vault.contract.functions.holderAccessControl.side_effect = AttributeError
        assert vault.can_hold_shares("0xUser") is True
        vault.contract.functions.holderAccessControl.side_effect = None

        vault.contract.functions.holderAccessControl().call.return_value = "0xHolderAcl"
        with patch.object(mock_w3.eth, "contract") as mock_ac_contract:
            mock_fn = mock_ac_contract.return_value.functions.canHoldShares
            mock_fn.return_value.call.return_value = True
            assert vault.can_hold_shares("0xUser") is True
            mock_fn.assert_called_with("0xUser")

        vault.contract.functions.transferAccessControl().call.return_value = (
            "0xTransferAcl"
        )
        with patch.object(mock_w3.eth, "contract") as mock_ac_contract:
            mock_fn = mock_ac_contract.return_value.functions.canTransferShares
            mock_fn.return_value.call.return_value = False
            assert vault.can_transfer_shares("0xUser") is False
            mock_fn.assert_called_with("0xUser", b"")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_transparent_vault_submit(self, MockConfig):
        """Test transparent vault submit."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.strategist.return_value.call.return_value = (
            "0xDeployer"
        )

        order = {"0xToken": 100}
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100
        )

        res = vault.submit_order_intent(order)
        assert res.receipt["status"] == 1

        # Verify it used the contract function
        vault.contract.functions.submitIntent.assert_called()

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_submit_order_intent_system_not_idle(self, MockConfig):
        """Test submit_order_intent raises SystemNotIdleError when system not idle."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = False

        vault = OrionTransparentVault()
        with pytest.raises(SystemNotIdleError, match="Cannot submit order intent"):
            vault.submit_order_intent({"0xToken": 1})

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_submit_order_intent_receipt_failed(self, MockConfig, mock_w3):
        """Test submit_order_intent when receipt status is 0."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.strategist.return_value.call.return_value = (
            "0xDeployer"
        )
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100
        )
        vault.contract.functions.submitIntent.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }

        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.submit_order_intent({"0xA": 1})

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_transparent_vault_transfer_fees(self, MockConfig):
        """Test transparent vault transfer fees."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"
        vault.contract.functions.claimVaultFees.return_value.build_transaction.return_value = {}

        res = vault.transfer_manager_fees(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.claimVaultFees.assert_called_with(100)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_transfer_manager_fees_system_not_idle(self, MockConfig):
        """Test transfer_manager_fees raises SystemNotIdleError when system not idle."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = False

        vault = OrionTransparentVault()
        with pytest.raises(SystemNotIdleError, match="Cannot transfer manager fees"):
            vault.transfer_manager_fees(100)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_init_invalid_vault(self, MockConfig):
        """Test OrionVault init with invalid vault address."""
        config_instance = MockConfig.return_value
        config_instance.is_orion_vault.return_value = False

        with pytest.raises(ValueError, match="is NOT a valid Orion vault registered"):
            OrionVault("Test")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_update_fee_model_errors(self, MockConfig):
        """Test update_fee_model error conditions."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        # Mock max fees
        vault.contract.functions.MAX_PERFORMANCE_FEE.return_value.call.return_value = (
            3000
        )
        vault.contract.functions.MAX_MANAGEMENT_FEE.return_value.call.return_value = 300
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"

        # 1. System not idle
        config_instance.is_system_idle.return_value = False
        with pytest.raises(SystemNotIdleError):
            vault.update_fee_model(0, 0, 0)
        config_instance.is_system_idle.return_value = True

        # 2. Performance fee too high
        with pytest.raises(ValueError, match="Performance fee .* exceeds maximum"):
            vault.update_fee_model(0, 3001, 0)

        # 3. Management fee too high
        with pytest.raises(ValueError, match="Management fee .* exceeds maximum"):
            vault.update_fee_model(0, 0, 301)

        # 4. Signer != Manager
        vault.contract.functions.manager.return_value.call.return_value = "0xOther"
        with pytest.raises(ValueError, match="Signer .* is not the vault manager"):
            vault.update_fee_model(0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_update_fee_model_receipt_failed(self, MockConfig, mock_w3):
        """Test update_fee_model when receipt status is 0."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.MAX_PERFORMANCE_FEE.return_value.call.return_value = (
            3000
        )
        vault.contract.functions.MAX_MANAGEMENT_FEE.return_value.call.return_value = 300
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"
        vault.contract.functions.updateFeeModel.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }

        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.update_fee_model(0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_update_strategist_error(self, MockConfig):
        """Test update_strategist error (signer != manager)."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xOther"

        with pytest.raises(ValueError, match="Signer .* is not the vault manager"):
            vault.update_strategist("0xNew")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_update_strategist_system_not_idle(self, MockConfig):
        """Test update_strategist raises SystemNotIdleError when system not idle."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = False
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        with pytest.raises(SystemNotIdleError, match="Cannot update strategist"):
            vault.update_strategist("0xNew")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_update_strategist_receipt_failed(self, MockConfig, mock_w3):
        """Test update_strategist when receipt status is 0."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"
        vault.contract.functions.updateStrategist.return_value.build_transaction.return_value = {}
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }

        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.update_strategist("0xNew")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_set_dac_errors(self, MockConfig):
        """Test set_deposit_access_control error conditions."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"

        # System not idle
        config_instance.is_system_idle.return_value = False
        with pytest.raises(SystemNotIdleError):
            vault.set_deposit_access_control("0xNew")
        config_instance.is_system_idle.return_value = True

        # Signer != Manager
        vault.contract.functions.manager.return_value.call.return_value = "0xOther"
        with pytest.raises(ValueError, match="Signer .* is not the vault manager"):
            vault.set_deposit_access_control("0xNew")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_submit_intent_error(self, MockConfig):
        """Test submit_order_intent error (signer != strategist)."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.strategist.return_value.call.return_value = "0xOther"

        with pytest.raises(ValueError, match="Signer .* is not the vault strategist"):
            vault.submit_order_intent({"0xA": 1})

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_transfer_fees_error(self, MockConfig):
        """Test transfer fees error (signer != manager)."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.orion_transparent_vaults = ["0xVault"]

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xOther"

        with pytest.raises(ValueError, match="Signer .* is not the vault manager"):
            vault.transfer_manager_fees(100)

    @patch("orion_finance_sdk_py.intent.Intent.encrypt")
    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_encrypted_submit_order_intent_sends_ciphertext(
        self, MockConfig, mock_encrypt
    ):
        """Encrypted submit seals intent then calls submitIntent(bytes)."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_orion_vault.return_value = True

        ciphertext = b"\x01" * 48
        mock_encrypt.return_value = ciphertext

        vault = OrionEncryptedVault()
        vault.contract.functions.strategist.return_value.call.return_value = (
            "0xDeployer"
        )
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100000
        )
        vault.contract.functions.submitIntent.return_value.build_transaction.return_value = {}

        order = {"0xToken": 1000}
        res = vault.submit_order_intent(order)

        assert res.receipt["status"] == 1
        mock_encrypt.assert_called_once()
        vault.contract.functions.submitIntent.assert_called_with(ciphertext)

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_config_extra_views_and_hpke_key(self):
        """Cover newer OrionConfig views and hpke_public_key branches."""
        config = OrionConfig()
        fn = config.contract.functions

        fn.getAllTokenDecimals().call.return_value = [6, 18]
        assert config.all_token_decimals == [6, 18]

        fn.liquidityOrchestrator().call.return_value = "0xLO"
        assert config.liquidity_orchestrator == "0xLO"

        fn.transparentVaultFactory().call.return_value = "0xTF"
        fn.encryptedVaultFactory().call.return_value = "0xEF"
        assert config.transparent_vault_factory == "0xTF"
        assert config.encrypted_vault_factory == "0xEF"

        fn.getAllOrionManagers().call.return_value = ["0xM1"]
        assert config.orion_managers == ["0xM1"]

        fn.isEncryptedVault("0xV").call.return_value = True
        assert config.is_encrypted_vault("0xV") is True

        fn.isDecommissionedVault("0xV").call.return_value = True
        fn.isDecommissioningVault("0xV").call.return_value = False
        assert config.is_decommissioned_vault("0xV") is True
        assert config.is_decommissioning_vault("0xV") is False

        fn.getAllDecommissionedVaults().call.return_value = ["0xD"]
        assert config.decommissioned_vaults == ["0xD"]

        fn.hpkePublicKey().call.return_value = b"\x01" * 32
        assert config.hpke_public_key == b"\x01" * 32

        fn.hpkePublicKey().call.return_value = "0x" + "02" * 32
        assert config.hpke_public_key == b"\x02" * 32

        fn.hpkePublicKey().call.return_value = int("03" * 32, 16)
        assert config.hpke_public_key == b"\x03" * 32

        fn.hpkePublicKey().call.return_value = b"\x01" * 16
        with pytest.raises(ValueError, match="32 bytes"):
            _ = config.hpke_public_key

        fn.hpkePublicKey().call.return_value = b"\x00" * 32
        with pytest.raises(ValueError, match="unset"):
            _ = config.hpke_public_key

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_remove_orion_vault_not_idle(self):
        config = OrionConfig()
        config.contract.functions.isSystemIdle().call.return_value = False
        with pytest.raises(SystemNotIdleError, match="Cannot remove Orion vault"):
            config.remove_orion_vault("0xVault")

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_remove_orion_vault_not_registered(self):
        config = OrionConfig()
        config.contract.functions.isSystemIdle().call.return_value = True
        config.contract.functions.isOrionVault("0xVault").call.return_value = False
        with pytest.raises(ValueError, match="not a registered Orion vault"):
            config.remove_orion_vault("0xVault")

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_remove_orion_vault_wrong_manager(self, mock_w3):
        config = OrionConfig()
        config.contract.functions.isSystemIdle().call.return_value = True
        config.contract.functions.isOrionVault("0xVault").call.return_value = True

        vault_contract = MagicMock()
        vault_contract.functions.manager.return_value.call.return_value = "0xOther"
        # OrionConfig already holds self.contract; remove_orion_vault loads vault ABI next.
        mock_w3.eth.contract.return_value = vault_contract

        with pytest.raises(ValueError, match="not the vault manager"):
            config.remove_orion_vault("0xVault")

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_remove_orion_vault_success_and_receipt_fail(self, mock_w3):
        config = OrionConfig()
        config.contract.functions.isSystemIdle().call.return_value = True
        config.contract.functions.isOrionVault("0xVault").call.return_value = True

        vault_contract = MagicMock()
        vault_contract.functions.manager.return_value.call.return_value = "0xDeployer"
        mock_w3.eth.contract.return_value = vault_contract
        config.contract.functions.removeOrionVault.return_value.build_transaction.return_value = {}

        res = config.remove_orion_vault("0xVault")
        assert res.receipt["status"] == 1

        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }
        with pytest.raises(Exception, match="Transaction failed with status"):
            config.remove_orion_vault("0xVault")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_lo_extra_views(self, MockConfig):
        MockConfig.return_value.contract.functions.liquidityOrchestrator.return_value.call.return_value = "0xLO"
        lo = LiquidityOrchestrator()
        lo.contract.functions.bufferAmount().call.return_value = 123
        lo.contract.functions.currentPhase().call.return_value = 2
        lo.contract.functions.epochCounter().call.return_value = 9
        lo.contract.functions.pendingProtocolFees().call.return_value = 7
        assert lo.buffer_amount == 123
        assert lo.current_phase == 2
        assert lo.epoch_counter == 9
        assert lo.pending_protocol_fees == 7

        fee_model = (0, 100, 10, 1)
        lo.contract.functions.getEpochState().call.return_value = (
            ["0xV"],
            5,
            6,
            [fee_model],
            b"\x00" * 32,
        )
        state = lo.get_epoch_state()
        assert state["vaultsEpoch"] == ["0xV"]
        assert state["activeNettingFeeCoefficient"] == 5
        assert state["vaultFeeModels"][0]["performanceFee"] == 100

        lo.contract.functions.getAssetPrices(["0xA"]).call.return_value = [111]
        assert lo.get_asset_prices(["0xA"]) == [111]

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_vault_erc4626_and_pending_views(self, MockConfig):
        MockConfig.return_value.is_orion_vault.return_value = True
        MockConfig.return_value.max_fulfill_batch_size = 10

        vault = OrionTransparentVault()
        fn = vault.contract.functions

        fn.pendingDepositCount().call.return_value = 3
        fn.pendingRedeemCount().call.return_value = 4
        assert vault.pending_deposit_count() == 3
        assert vault.pending_redeem_count() == 4

        fn.pendingRedeemBatch(10).call.return_value = (["0xO"], [5])
        owners, shares = vault.pending_redeem_batch()
        assert owners == ["0xO"]
        assert shares == [5]

        fn.depositAccessControl().call.return_value = "0xAcl"
        assert vault.deposit_access_control == "0xAcl"
        fn.holderAccessControl().call.return_value = "0xHolderAcl"
        assert vault.holder_access_control == "0xHolderAcl"
        fn.transferAccessControl().call.return_value = "0xTransferAcl"
        assert vault.transfer_access_control == "0xTransferAcl"

        fn.asset().call.return_value = "0xAsset"
        fn.balanceOf("0xAcc").call.return_value = 8
        fn.totalSupply().call.return_value = 100
        fn.allowance("0xOwner", "0xSpender").call.return_value = 2
        fn.convertToShares(50).call.return_value = 40
        fn.previewRedeem(10).call.return_value = 9
        fn.maxMint("0xR").call.return_value = 1
        fn.maxRedeem("0xO").call.return_value = 2
        fn.maxWithdraw("0xO").call.return_value = 3

        assert vault.asset == "0xAsset"
        assert vault.balance_of("0xAcc") == 8
        assert vault.total_supply == 100
        assert vault.allowance("0xOwner", "0xSpender") == 2
        assert vault.convert_to_shares(50) == 40
        assert vault.preview_redeem(10) == 9
        assert vault.max_mint("0xR") == 1
        assert vault.max_redeem("0xO") == 2
        assert vault.max_withdraw("0xO") == 3

    @patch("orion_finance_sdk_py.contracts.OrionVault._execute_vault_tx")
    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_vault_share_ops_and_redeem_when_decommissioned(
        self, MockConfig, mock_exec
    ):
        MockConfig.return_value.is_orion_vault.return_value = True
        MockConfig.return_value.is_decommissioned_vault.return_value = True
        mock_exec.return_value = TransactionResult(
            tx_hash="0x1", receipt={"status": 1}, decoded_logs=[]
        )

        vault = OrionTransparentVault()
        vault.approve_shares("0xS", 1)
        vault.transfer_shares("0xT", 2)
        vault.transfer_from_shares("0xF", "0xT", 3)
        vault.redeem(4, "0xR", "0xO")
        assert mock_exec.call_count == 4

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_transfer_manager_fees_receipt_failed(self, MockConfig, mock_w3):
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.manager.return_value.call.return_value = "0xDeployer"
        vault.contract.functions.claimVaultFees.return_value.build_transaction.return_value = {}
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }
        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.transfer_manager_fees(100)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_encrypted_get_portfolio_and_intent(self, MockConfig):
        MockConfig.return_value.is_orion_vault.return_value = True
        vault = OrionEncryptedVault()
        vault.contract.functions.getPortfolio().call.return_value = b"\xaa" * 10
        vault.contract.functions.getIntent().call.return_value = b"\xbb" * 10
        assert vault.get_portfolio() == b"\xaa" * 10
        assert vault.get_intent() == b"\xbb" * 10

    @patch("orion_finance_sdk_py.intent.Intent.encrypt")
    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_encrypted_submit_idle_strategist_receipt_fail(
        self, MockConfig, mock_encrypt, mock_w3
    ):
        config_instance = MockConfig.return_value
        config_instance.is_orion_vault.return_value = True
        config_instance.is_system_idle.return_value = False
        vault = OrionEncryptedVault()
        with pytest.raises(SystemNotIdleError):
            vault.submit_order_intent({"0xA": 1})

        config_instance.is_system_idle.return_value = True
        vault.contract.functions.strategist.return_value.call.return_value = "0xOther"
        with pytest.raises(ValueError, match="not the vault strategist"):
            vault.submit_order_intent({"0xA": 1})

        vault.contract.functions.strategist.return_value.call.return_value = (
            "0xDeployer"
        )
        mock_encrypt.return_value = b"\x01" * 48
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100000
        )
        vault.contract.functions.submitIntent.return_value.build_transaction.return_value = {}
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "logs": [],
        }
        with pytest.raises(Exception, match="Transaction failed with status"):
            vault.submit_order_intent({"0xA": 1})
