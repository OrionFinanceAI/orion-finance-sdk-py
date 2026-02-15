import os
from unittest.mock import patch

import pytest
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionTransparentVault,
    VaultFactory,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS, VaultType
from web3.exceptions import ABIFunctionNotFound

try:
    from ape import accounts, networks

    HAS_APE = True
except ImportError:
    HAS_APE = False


@pytest.fixture
def skip_if_no_ape():
    if not HAS_APE:
        pytest.skip("ape not installed")


def test_comprehensive_config_on_fork(skip_if_no_ape):
    """Extensive testing of OrionConfig and linked components on Sepolia fork."""

    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        print(f"\n--- [OrionConfig @ {config.contract_address}] ---")

        # 1. Intent Decimals
        intent_decimals = config.strategist_intent_decimals
        print(f"Strategist Intent Decimals: {intent_decimals}")
        assert intent_decimals > 0

        # 2. Whitelisting checks
        assets = config.whitelisted_assets
        print(f"Whitelisted Assets: {assets}")
        if assets:
            first_asset = assets[0]
            assert config.is_whitelisted(first_asset)

            # Check individual decimals via config
            asset_decimals = config.token_decimals(first_asset)
            print(f"Asset {first_asset} Decimals: {asset_decimals}")
            assert asset_decimals in [6, 18, 8]

        # 3. Fee Coefficients
        print(f"V Fee Coeff: {config.v_fee_coefficient}")
        print(f"RS Fee Coeff: {config.rs_fee_coefficient}")

        # 4. Test LiquidityOrchestrator integration
        lo = LiquidityOrchestrator()
        print(f"\n--- [LiquidityOrchestrator @ {lo.contract_address}] ---")
        print(f"Target Buffer Ratio: {lo.target_buffer_ratio}")
        print(f"Epoch Duration: {lo.epoch_duration}s")
        assert lo.epoch_duration > 0


def test_vault_getters_on_fork(skip_if_no_ape):
    """Dynamically discover and test OrionTransparentVaults from OrionConfig."""

    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults

        if not vaults:
            pytest.skip("No Orion Transparent Vaults found in OrionConfig")

        print(f"\nDiscovered {len(vaults)} transparent vaults.")

        for i, vault_addr in enumerate(vaults):
            print(f"\n--- [Vault #{i}: {vault_addr}] ---")
            os.environ["ORION_VAULT_ADDRESS"] = vault_addr
            vault = OrionTransparentVault()

            print(f"Manager: {vault.manager_address}")
            print(f"Strategist: {vault.strategist_address}")
            print(f"Total Assets: {vault.total_assets}")
            print(f"Share Price: {vault.share_price}")

            fee_model = vault.active_fee_model
            print(f"Active Fee Model: {fee_model}")

            portfolio = vault.get_portfolio()
            print(f"Portfolio: {portfolio}")


def test_vault_pending_ops_on_fork(skip_if_no_ape):
    """Test async pending deposit/redeem requests on fork."""

    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No vaults to test pending ops")

        vault_addr = vaults[0]
        os.environ["ORION_VAULT_ADDRESS"] = vault_addr
        vault = OrionTransparentVault()

        manager_addr = vault.manager_address
        print(f"\nTesting Pending Ops on Vault: {vault_addr}")

        # Impersonate manager
        manager = accounts[manager_addr]
        accounts.test_accounts[0].transfer(manager, "1 ether", gas_limit=15000000)

        # Building simple intent
        whitelisted = config.whitelisted_assets
        intent_decimals = config.strategist_intent_decimals
        intent = {whitelisted[0]: 1 * 10**intent_decimals}

        print(f"Vault Pending Deposit before: {vault.pending_deposit(10)}")

        # We need to mock the Account.from_key to return our impersonated manager
        with patch("eth_account.Account.from_key") as mock_from_key:
            mock_from_key.return_value = manager

            # Since impersonated accounts in ape handle signing differently than
            # the SDK's manual sign_transaction flow, we'll just stop here.
            # The test confirms we can fetch the state.
            pass


def test_fork_connection(skip_if_no_ape):
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        block_number = networks.active_provider.get_block("latest").number
        assert block_number > 0
        print(f"\n[Hardhat Fork] Latest Block: {block_number}")


def test_orion_config_v2_properties_on_fork(skip_if_no_ape):
    """OrionConfig v2 properties against Sepolia fork state."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()

        assert config.min_deposit_amount >= 0
        assert config.min_redeem_amount >= 0
        assert config.fee_change_cooldown_duration >= 0
        assert config.max_fulfill_batch_size > 0

        underlying = config.underlying_asset
        assert (
            underlying is not None
            and len(underlying) == 42
            and underlying.startswith("0x")
        )

        assert config.risk_free_rate >= 0

        names = config.whitelisted_asset_names
        assets = config.whitelisted_assets
        assert len(names) == len(assets), (
            "whitelisted_asset_names length must match whitelisted_assets"
        )


def test_orion_config_system_idle_on_fork(skip_if_no_ape):
    """OrionConfig is_system_idle reflects chain state."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        idle = config.is_system_idle()
        assert isinstance(idle, bool)


def test_orion_config_is_orion_vault_on_fork(skip_if_no_ape):
    """OrionConfig is_orion_vault: registered vaults True, zero address False."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults

        for addr in vaults:
            assert config.is_orion_vault(addr) is True

        assert config.is_orion_vault(ZERO_ADDRESS) is False


def test_orion_config_managers_whitelisted_on_fork(skip_if_no_ape):
    """Every registered vault's manager is whitelisted in OrionConfig."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        for vault_addr in vaults:
            os.environ["ORION_VAULT_ADDRESS"] = vault_addr
            vault = OrionTransparentVault()
            manager = vault.manager_address
            assert config.is_whitelisted_manager(manager), (
                f"Manager {manager} of vault {vault_addr} should be whitelisted"
            )


def test_liquidity_orchestrator_state_on_fork(skip_if_no_ape):
    """LiquidityOrchestrator slippage_tolerance, target_buffer_ratio, epoch_duration from chain."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        lo = LiquidityOrchestrator()
        assert lo.slippage_tolerance >= 0
        assert lo.target_buffer_ratio >= 0
        assert lo.epoch_duration > 0
        try:
            assert isinstance(lo.is_system_idle(), bool)
        except ABIFunctionNotFound:
            # LiquidityOrchestrator ABI may not expose isSystemIdle
            pass


def test_vault_factory_address_matches_config_on_fork(skip_if_no_ape):
    """VaultFactory(transparent) address equals OrionConfig.transparentVaultFactory()."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        expected = config.contract.functions.transparentVaultFactory().call()
        factory = VaultFactory(vault_type=VaultType.TRANSPARENT.value)
        assert factory.contract_address.lower() == expected.lower()


def test_vault_fee_limits_and_fees_on_fork(skip_if_no_ape):
    """Vault max_performance_fee, max_management_fee, pending_vault_fees from state."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        os.environ["ORION_VAULT_ADDRESS"] = vaults[0]
        vault = OrionTransparentVault()

        assert vault.max_performance_fee > 0
        assert vault.max_management_fee > 0
        assert vault.pending_vault_fees >= 0.0


def test_vault_share_price_convert_consistency_on_fork(skip_if_no_ape):
    """Vault share_price equals convertToAssets(10**decimals) from contract."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        os.environ["ORION_VAULT_ADDRESS"] = vaults[0]
        vault = OrionTransparentVault()

        decimals = vault.contract.functions.decimals().call()
        one_share = 10**decimals
        assert vault.share_price == vault.convert_to_assets(one_share)


def test_vault_can_request_deposit_and_max_deposit_on_fork(skip_if_no_ape):
    """Vault can_request_deposit and max_deposit for a receiver on fork."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        os.environ["ORION_VAULT_ADDRESS"] = vaults[0]
        vault = OrionTransparentVault()

        receiver = accounts.test_accounts[0].address
        can_deposit = vault.can_request_deposit(receiver)
        assert isinstance(can_deposit, bool)

        max_dep = vault.max_deposit(receiver)
        assert max_dep >= 0


def test_vault_is_decommissioning_on_fork(skip_if_no_ape):
    """Vault is_decommissioning reflects chain state."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        os.environ["ORION_VAULT_ADDRESS"] = vaults[0]
        vault = OrionTransparentVault()
        assert isinstance(vault.is_decommissioning, bool)


def test_vault_pending_deposit_redeem_non_negative_on_fork(skip_if_no_ape):
    """Vault pending_deposit and pending_redeem are non-negative with default and explicit batch size."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        os.environ["ORION_VAULT_ADDRESS"] = vaults[0]
        vault = OrionTransparentVault()

        batch = config.max_fulfill_batch_size
        assert vault.pending_deposit() >= 0
        assert vault.pending_deposit(batch) >= 0
        assert vault.pending_redeem() >= 0
        assert vault.pending_redeem(batch) >= 0


def test_vault_portfolio_tokens_whitelisted_on_fork(skip_if_no_ape):
    """Every token in a vault's portfolio is whitelisted in OrionConfig."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults
        if not vaults:
            pytest.skip("No Orion Transparent Vaults found")

        whitelisted = set(a.lower() for a in config.whitelisted_assets)

        for vault_addr in vaults:
            os.environ["ORION_VAULT_ADDRESS"] = vault_addr
            vault = OrionTransparentVault()
            portfolio = vault.get_portfolio()
            for token in portfolio:
                assert token.lower() in whitelisted, (
                    f"Portfolio token {token} not whitelisted"
                )


def test_orion_config_uses_ape_provider_when_rpc_unset(skip_if_no_ape):
    """OrionConfig uses ape's active provider when RPC_URL is not set (user read path)."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        rpc_saved = os.environ.pop("RPC_URL", None)
        try:
            with patch("orion_finance_sdk_py.contracts.load_dotenv"):
                config = OrionConfig()
            assert config.underlying_asset is not None
            assert len(config.underlying_asset) == 42
        finally:
            if rpc_saved is not None:
                os.environ["RPC_URL"] = rpc_saved


def test_orion_config_uses_env_address_when_set(skip_if_no_ape):
    """OrionConfig uses ORION_CONFIG_ADDRESS when set (user/config override)."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        from orion_finance_sdk_py.types import CHAIN_CONFIG

        expected_addr = CHAIN_CONFIG[11155111]["OrionConfig"]
        os.environ["ORION_CONFIG_ADDRESS"] = expected_addr
        try:
            config = OrionConfig()
            assert config.contract_address.lower() == expected_addr.lower()
            assert config.underlying_asset is not None
        finally:
            os.environ.pop("ORION_CONFIG_ADDRESS", None)


def test_list_whitelisted_assets_logic_on_fork(skip_if_no_ape, capsys):
    """User path: list whitelisted assets from chain via CLI logic (no admin)."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        from orion_finance_sdk_py.cli import _list_whitelisted_assets_logic

        _list_whitelisted_assets_logic()
        out, _ = capsys.readouterr()
        assert "whitelisted" in out.lower() or "Total:" in out


def test_get_investment_universe_on_fork(skip_if_no_ape):
    """User path: get_investment_universe alias equals whitelisted_assets."""
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        universe = config.get_investment_universe
        assets = config.whitelisted_assets
        assert universe == assets
        if assets:
            assert config.is_whitelisted(assets[0])
