"""Tests for the contracts module."""

import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionEncryptedVault,
    OrionSmartContract,
    OrionTransparentVault,
    OrionVault,
    SystemNotIdleError,
    TransactionResult,
    VaultFactory,
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


class TestOrionSmartContract:
    """Tests for OrionSmartContract base class."""

    def test_init(self, mock_w3, mock_load_abi, mock_env):
        """Test initialization."""
        contract = OrionSmartContract("TestContract", "0xAddress")
        assert contract.w3 == mock_w3
        assert contract.contract_name == "TestContract"
        assert contract.contract_address == "0xAddress"

    def test_wait_for_transaction_receipt(self, mock_w3, mock_load_abi, mock_env):
        """Test waiting for receipt."""
        contract = OrionSmartContract("TestContract", "0xAddress")
        contract._wait_for_transaction_receipt("0xHash")
        mock_w3.eth.wait_for_transaction_receipt.assert_called_with(
            "0xHash", timeout=120
        )

    def test_decode_logs(self, mock_w3, mock_load_abi, mock_env):
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

    def test_properties(self, mock_w3, mock_load_abi, mock_env):
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

    def test_init_invalid_chain(self, mock_w3, mock_load_abi):
        """Test init with invalid chain ID."""
        with patch.dict(os.environ, {"CHAIN_ID": "1", "RPC_URL": "http://localhost"}):
            with pytest.raises(ValueError, match="Unsupported CHAIN_ID"):
                OrionConfig()

    def test_init_chain_mismatch(self, mock_w3, mock_load_abi):
        """Test init with chain ID mismatch warning."""
        # mock_w3 provides chain_id=11155111
        with patch.dict(os.environ, {"CHAIN_ID": "1", "RPC_URL": "http://localhost"}):
            with patch("builtins.print") as mock_print:
                # We instantiate a base contract which does the check
                OrionSmartContract("Test", "0xAddress")
                mock_print.assert_called_with(
                    "⚠️ Warning: CHAIN_ID in env (1) does not match RPC chain ID (11155111)"
                )

    def test_decode_logs_exception(self, mock_w3, mock_load_abi, mock_env):
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
    def test_init_and_properties(self, MockConfig, mock_w3, mock_load_abi, mock_env):
        MockConfig.return_value.contract.functions.liquidityOrchestrator().call.return_value = "0xLiquidity"

        lo = LiquidityOrchestrator()
        assert lo.contract_address == "0xLiquidity"

        lo.contract.functions.targetBufferRatio().call.return_value = 1000
        assert lo.target_buffer_ratio == 1000

        lo.contract.functions.slippageTolerance().call.return_value = 50
        assert lo.slippage_tolerance == 50


class TestVaultFactory:
    """Tests for VaultFactory."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_create_orion_vault(self, MockConfig, mock_w3, mock_load_abi, mock_env):
        """Test vault creation."""
        # Mock OrionConfig
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
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
        )

        assert isinstance(result, TransactionResult)
        assert result.receipt["status"] == 1

        # Verify call arguments (checking if strategist address from env is used)
        factory.contract.functions.createVault.assert_called()
        args = factory.contract.functions.createVault.call_args[0]
        assert args[0] == "0xStrategist"  # First arg is strategist/curator
        # Check deposit access control passed
        assert args[6] == ZERO_ADDRESS

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_create_orion_vault_insufficient_balance(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test vault creation fails with insufficient balance."""
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300

        factory = VaultFactory(VaultType.TRANSPARENT)

        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        mock_w3.eth.gas_price = 1000000000
        # Cost ~ 1.2 * 10^14
        mock_w3.eth.get_balance.return_value = 0  # Not enough

        with pytest.raises(ValueError, match="Insufficient ETH balance"):
            factory.create_orion_vault("N", "S", 0, 0, 0)

    def test_create_orion_vault_system_busy(self, mock_w3, mock_load_abi, mock_env):
        """Test system busy check."""
        with patch("orion_finance_sdk_py.contracts.OrionConfig") as MockConfig:
            MockConfig.return_value.is_system_idle.return_value = False
            # Mock transparent factory address
            MockConfig.return_value.contract.functions.transparentVaultFactory().call.return_value = "0xTVF"
            MockConfig.return_value.max_performance_fee = 3000
            MockConfig.return_value.max_management_fee = 300

            factory = VaultFactory(VaultType.TRANSPARENT)

            with pytest.raises(SystemNotIdleError):
                factory.create_orion_vault("N", "S", 0, 0, 0)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_vault_factory_encrypted_fallback(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test VaultFactory encrypted address fallback."""
        with patch.dict(
            "orion_finance_sdk_py.contracts.CHAIN_CONFIG",
            {11155111: {"OrionConfig": "0x..."}},
        ):
            # Missing EncryptedVaultFactory key
            factory = VaultFactory(VaultType.ENCRYPTED)
            assert (
                factory.contract_address == "0xdD7900c4B6abfEB4D2Cb9F233d875071f6e1093F"
            )  # Fallback hardcoded

    def test_get_vault_address(self, mock_w3, mock_load_abi, mock_env):
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


class TestOrionVaults:
    """Tests for OrionVault and subclasses."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_orion_vault_methods(self, MockConfig, mock_w3, mock_load_abi, mock_env):
        """Test base methods."""
        # Mock config for update_fee_model calls
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True
        config_instance.max_performance_fee = 3000
        config_instance.max_management_fee = 300
        # Mock vault validation (assume it's in transparent list)
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.orion_encrypted_vaults = []

        vault = OrionVault("OrionVault")

        # Mock fee limit calls
        vault.contract.functions.MAX_PERFORMANCE_FEE.return_value.call.return_value = (
            3000
        )
        vault.contract.functions.MAX_MANAGEMENT_FEE.return_value.call.return_value = 300

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
    def test_transparent_vault_submit(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test transparent vault submit."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.orion_encrypted_vaults = []
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()

        order = {"0xToken": 100}
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100
        )

        res = vault.submit_order_intent(order)
        assert res.receipt["status"] == 1

        # Verify it used the contract function
        vault.contract.functions.submitIntent.assert_called()

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_transparent_vault_transfer_fees(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test transparent vault transfer fees."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = ["0xVault"]
        config_instance.orion_encrypted_vaults = []
        config_instance.is_system_idle.return_value = True

        vault = OrionTransparentVault()
        vault.contract.functions.claimVaultFees.return_value.build_transaction.return_value = {}

        res = vault.transfer_manager_fees(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.claimVaultFees.assert_called_with(100)

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_encrypted_vault_submit(self, MockConfig, mock_w3, mock_load_abi, mock_env):
        """Test encrypted vault submit."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = []
        config_instance.orion_encrypted_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionEncryptedVault()

        order = {"0xToken": b"encrypted"}
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100
        )

        res = vault.submit_order_intent(order, "0xProof")
        assert res.receipt["status"] == 1

        # Verify inputs
        args = vault.contract.functions.submitIntent.call_args[0]
        assert args[1] == "0xProof"

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_encrypted_vault_update_strategist(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test encrypted vault update strategist (wrapper around updateCurator)."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = []
        config_instance.orion_encrypted_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionEncryptedVault()

        vault.contract.functions.updateCurator.return_value.estimate_gas.return_value = 100

        res = vault.update_strategist("0xNew")
        assert res.receipt["status"] == 1

        # Verify it called updateCurator, NOT updateStrategist
        vault.contract.functions.updateCurator.assert_called_with("0xNew")

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_encrypted_vault_transfer_fees(
        self, MockConfig, mock_w3, mock_load_abi, mock_env
    ):
        """Test encrypted vault transfer fees."""
        # Mock config validation
        config_instance = MockConfig.return_value
        config_instance.orion_transparent_vaults = []
        config_instance.orion_encrypted_vaults = ["0xVault"]
        config_instance.is_system_idle.return_value = True

        vault = OrionEncryptedVault()
        vault.contract.functions.claimCuratorFees.return_value.build_transaction.return_value = {}

        res = vault.transfer_strategist_fees(100)
        assert res.receipt["status"] == 1
        vault.contract.functions.claimCuratorFees.assert_called_with(100)
