"""Tests for the contracts module."""

import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.contracts import (
    OrionConfig,
    OrionEncryptedVault,
    OrionSmartContract,
    OrionTransparentVault,
    OrionVault,
    TransactionResult,
    VaultFactory,
)
from orion_finance_sdk_py.types import VaultType


@pytest.fixture
def mock_w3():
    """Mock Web3 instance."""
    with patch("orion_finance_sdk_py.contracts.Web3") as MockWeb3:
        # Mock the provider to avoid connection errors in init
        MockWeb3.HTTPProvider.return_value = MagicMock()

        # Setup the mock instance
        w3_instance = MagicMock()
        MockWeb3.return_value = w3_instance

        # Mock eth.contract
        contract_mock = MagicMock()
        w3_instance.eth.contract.return_value = contract_mock

        # Mock transaction signing and sending
        w3_instance.eth.get_transaction_count.return_value = 0
        w3_instance.eth.gas_price = 1000000000
        w3_instance.eth.account.from_key.return_value = MagicMock(address="0xDeployer")

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
        "STRATEGIST_ADDRESS": "0xStrategist",
        "CURATOR_ADDRESS": "0xCurator",
        "VAULT_DEPLOYER_PRIVATE_KEY": "0xPrivate",
        "STRATEGIST_PRIVATE_KEY": "0xPrivate",
        "CURATOR_PRIVATE_KEY": "0xPrivate",
        "ORION_VAULT_ADDRESS": "0xVault",
    }
    with patch.dict(os.environ, env_vars):
        yield


def test_load_contract_abi_success():
    """Test successful ABI loading."""
    # We can't easily mock resources.files without affecting other things,
    # but we can rely on the fact that the package is installed in dev mode.
    # The real load_contract_abi is tested in test_contract_abis.py.
    # Here we just verify it returns a list if we mock the open.
    pass


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
        assert config.whitelisted_assets == ["0xA", "0xB"]
        assert config.orion_transparent_vaults == ["0xV1"]
        assert config.orion_encrypted_vaults == ["0xV2"]
        assert config.is_system_idle() is True

        config.contract.functions.isWhitelisted("0xToken").call.return_value = True
        assert config.is_whitelisted("0xToken") is True


class TestVaultFactory:
    """Tests for VaultFactory."""

    @patch("orion_finance_sdk_py.contracts.OrionConfig")
    def test_create_orion_vault(self, MockConfig, mock_w3, mock_load_abi, mock_env):
        """Test vault creation."""
        # Mock OrionConfig
        config_instance = MockConfig.return_value
        config_instance.is_system_idle.return_value = True

        factory = VaultFactory(VaultType.TRANSPARENT)

        # Mock contract calls
        factory.contract.functions.createVault.return_value.estimate_gas.return_value = 100000
        factory.contract.functions.createVault.return_value.build_transaction.return_value = {}

        result = factory.create_orion_vault(
            name="Test",
            symbol="TST",
            fee_type=0,
            performance_fee=1000,
            management_fee=100,
        )

        assert isinstance(result, TransactionResult)
        assert result.receipt["status"] == 1

        # Verify call arguments (checking if strategist address from env is used)
        factory.contract.functions.createVault.assert_called()
        args = factory.contract.functions.createVault.call_args[0]
        assert args[0] == "0xStrategist"  # First arg is strategist/curator

    def test_create_orion_vault_system_busy(self, mock_w3, mock_load_abi, mock_env):
        """Test system busy check."""
        with patch("orion_finance_sdk_py.contracts.OrionConfig") as MockConfig:
            MockConfig.return_value.is_system_idle.return_value = False
            factory = VaultFactory(VaultType.TRANSPARENT)

            with pytest.raises(SystemExit):
                factory.create_orion_vault("N", "S", 0, 0, 0)

    def test_get_vault_address(self, mock_w3, mock_load_abi, mock_env):
        """Test extracting address from logs."""
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

    def test_orion_vault_methods(self, mock_w3, mock_load_abi, mock_env):
        """Test base methods."""
        vault = OrionVault("OrionVault")

        # Mock tx methods
        vault.contract.functions.updateStrategist.return_value.estimate_gas.return_value = 100
        vault.contract.functions.updateFeeModel.return_value.estimate_gas.return_value = 100

        res = vault.update_strategist("0xNew")
        assert res.receipt["status"] == 1

        res = vault.update_fee_model(0, 0, 0)
        assert res.receipt["status"] == 1

    def test_transparent_vault_submit(self, mock_w3, mock_load_abi, mock_env):
        """Test transparent vault submit."""
        vault = OrionTransparentVault()

        order = {"0xToken": 100}
        vault.contract.functions.submitIntent.return_value.estimate_gas.return_value = (
            100
        )

        res = vault.submit_order_intent(order)
        assert res.receipt["status"] == 1

        # Verify it used the contract function
        vault.contract.functions.submitIntent.assert_called()

    def test_encrypted_vault_submit(self, mock_w3, mock_load_abi, mock_env):
        """Test encrypted vault submit."""
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

    def test_encrypted_vault_update_strategist(self, mock_w3, mock_load_abi, mock_env):
        """Test encrypted vault update strategist (wrapper around updateCurator)."""
        vault = OrionEncryptedVault()

        vault.contract.functions.updateCurator.return_value.estimate_gas.return_value = 100

        res = vault.update_strategist("0xNew")
        assert res.receipt["status"] == 1

        # Verify it called updateCurator, NOT updateStrategist
        vault.contract.functions.updateCurator.assert_called_with("0xNew")
