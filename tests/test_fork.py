import os

import pytest
from orion_finance_sdk_py.contracts import (
    LiquidityOrchestrator,
    OrionConfig,
    OrionTransparentVault,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS

try:
    from ape import networks

    HAS_APE = True
except ImportError:
    HAS_APE = False


@pytest.mark.skipif(not HAS_APE, reason="ape not installed")
def test_comprehensive_config_on_fork():
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
            print(f"Asset {first_asset} is confirmed whitelisted.")

            # Test non-whitelisted address
            assert not config.is_whitelisted(ZERO_ADDRESS)

            # Check individual decimals via config
            asset_decimals = config.token_decimals(first_asset)
            print(f"Asset Decimals: {asset_decimals}")
            assert asset_decimals in [6, 18, 8]  # Common decimals

        # 3. Manager Whitelisting
        manager_key = os.getenv("MANAGER_PRIVATE_KEY")
        if manager_key:
            from web3 import Web3

            w3 = Web3()
            acc = w3.eth.account.from_key(manager_key)
            is_whitelisted_mgr = config.is_whitelisted_manager(acc.address)
            print(f"Manager {acc.address} whitelisted: {is_whitelisted_mgr}")

        # 4. Fee Coefficients
        print(f"V Fee Coeff: {config.v_fee_coefficient}")
        print(f"RS Fee Coeff: {config.rs_fee_coefficient}")
        print(f"Min Deposit: {config.min_deposit_amount}")

        # 5. Cooldowns and Limits
        print(f"Fee Change Cooldown: {config.fee_change_cooldown_duration}s")
        print(f"Max Fulfill Batch: {config.max_fulfill_batch_size}")

        # 6. Test LiquidityOrchestrator integration
        lo = LiquidityOrchestrator()
        print(f"\n--- [LiquidityOrchestrator @ {lo.contract_address}] ---")
        print(f"Target Buffer Ratio: {lo.target_buffer_ratio}")
        print(f"Slippage Tolerance: {lo.slippage_tolerance}")
        print(f"Epoch Duration: {lo.epoch_duration}s")
        assert lo.epoch_duration > 0


@pytest.mark.skipif(not HAS_APE, reason="ape not installed")
def test_vault_getters_on_fork():
    """Dynamically discover and test OrionTransparentVaults from OrionConfig."""

    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()
        vaults = config.orion_transparent_vaults

        if not vaults:
            pytest.skip("No Orion Transparent Vaults found in OrionConfig")

        print(f"\nDiscovered {len(vaults)} transparent vaults.")

        for i, vault_addr in enumerate(vaults):
            print(f"\n--- [Vault #{i}: {vault_addr}] ---")

            # Manually override environment for SDK instantiation
            os.environ["ORION_VAULT_ADDRESS"] = vault_addr

            vault = OrionTransparentVault()

            # 1. Basic Metadata
            print(f"Manager: {vault.manager_address}")
            print(f"Strategist: {vault.strategist_address}")
            print(f"Total Assets: {vault.total_assets}")
            print(f"Share Price: {vault.share_price}")

            # 2. Fee Model
            fee_model = vault.active_fee_model
            print(f"Active Fee Model: {fee_model}")
            assert "performanceFee" in fee_model

            # 3. Portfolio
            portfolio = vault.get_portfolio()
            print(f"Portfolio: {portfolio}")

            # 4. Pending state
            print(f"Pending Deposit (batch 10): {vault.pending_deposit(10)}")
            print(f"Pending Redeem (batch 10): {vault.pending_redeem(10)}")


@pytest.mark.skipif(not HAS_APE, reason="ape not installed")
def test_fork_connection():
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        block_number = networks.active_provider.get_block("latest").number
        assert block_number > 0
        print(f"\n[Hardhat Fork] Latest Block: {block_number}")
