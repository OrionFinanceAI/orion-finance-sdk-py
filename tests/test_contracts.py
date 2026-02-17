"""Tests for the contracts module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionSmartContract,
    OrionTransparentVault,
    OrionVault,
    SystemNotIdleError,
    TransactionResult,
    VaultFactory,
    _get_view_call_tx,
    load_contract_abi,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS, VaultType


@pytest.fixture
def mock_w3():
    """Mock Web3 instance."""
    with patch("orion_finance_sdk_py.contracts.Web3") as MockWeb3:
        # Mock the provider to avoid connection errors in init
        MockWeb3.HTTPProvider.return_value = MagicMock()

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

        receipt = MagicMock()
        log_mock = MagicMock()
        log_mock.address = "0xAddress"  # Matching address
        receipt.logs = [log_mock]

        logs = contract._decode_logs(receipt)
        assert len(logs) == 1
        assert logs[0]["event"] == "TestEvent"

        # Test ignoring logs from other contracts
        log_mock_other = MagicMock()
        log_mock_other.address = "0xOther"
        receipt.logs = [log_mock_other]
        logs = contract._decode_logs(receipt)
        assert len(logs) == 0


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
        assert config.is_system_idle() is True

        config.contract.functions.isWhitelisted("0xToken").call.return_value = True
        assert config.is_whitelisted("0xToken") is True

        config.contract.functions.isWhitelistedManager(
            "0xManager"
        ).call.return_value = True
        assert config.is_whitelisted_manager("0xManager") is True

    @pytest.mark.usefixtures("mock_w3", "mock_load_abi", "mock_env")
    def test_v2_properties(self):
        """Test v2.0.0 OrionConfig properties."""
        config = OrionConfig()

        config.contract.functions.minDepositAmount().call.return_value = 100
        assert config.min_deposit_amount == 100

        config.contract.functions.minRedeemAmount().call.return_value = 50
        assert config.min_redeem_amount == 50

        config.contract.functions.vFeeCoefficient().call.return_value = 5
        assert config.v_fee_coefficient == 5

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
        assert args[0] == "0xStrategist"  # First arg is strategist

        # Check deposit access control passed
        assert args[6] == ZERO_ADDRESS

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
    @pytest.mark.usefixtures("mock_load_abi", "mock_env")
    def test_create_orion_vault_fee_exceeds_max(self, MockConfig, mock_w3):
        """Test vault creation fails when performance or management fee exceeds max."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.is_whitelisted_manager.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000

        with pytest.raises(ValueError, match="Performance fee .* exceeds maximum"):
            factory.create_orion_vault("0xStrategist", "N", "S", 0, 3001, 0)
        with pytest.raises(ValueError, match="Management fee .* exceeds maximum"):
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

        # Test can_request_deposit (permissionless)
        vault.contract.functions.depositAccessControl().call.return_value = ZERO_ADDRESS
        assert vault.can_request_deposit("0xUser") is True

        # Test can_request_deposit (with access control)
        vault.contract.functions.depositAccessControl().call.return_value = "0xAC"
        with patch.object(mock_w3.eth, "contract") as mock_ac_contract:
            mock_ac_instance = mock_ac_contract.return_value
            mock_ac_instance.functions.canRequestDeposit().call.return_value = True
            assert vault.can_request_deposit("0xUser") is True
            mock_ac_instance.functions.canRequestDeposit().call.return_value = False
            assert vault.can_request_deposit("0xUser") is False

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

        vault.contract.functions.isDecommissioning.return_value.call.return_value = True
        assert vault.is_decommissioning is True

        # Test async operations
        # request_deposit
        vault.contract.functions.requestDeposit.return_value.build_transaction.return_value = {}
        res = vault.request_deposit(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.requestDeposit.assert_called_with(100)

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
    def test_execute_vault_tx_with_gas_limit(self, MockConfig):
        """Test _execute_vault_tx includes gas in tx_params when gas_limit is provided."""
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.requestDeposit.return_value.build_transaction.return_value = {}
        mock_w3 = vault.w3
        mock_w3.eth.account.from_key.return_value.address = "0xDeployer"

        res = vault._execute_vault_tx(
            vault.contract.functions.requestDeposit(100),
            error_msg="Private key missing.",
            gas_limit=0,
        )
        assert res.receipt["status"] == 1
        # build_transaction should have been called with gas=0 in tx_params
        call_args = vault.contract.functions.requestDeposit.return_value.build_transaction.call_args[
            0
        ][0]
        assert call_args.get("gas") == 0

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

        with pytest.raises(
            ValueError, match="is NOT a valid Orion Transparent Vault registered"
        ):
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
