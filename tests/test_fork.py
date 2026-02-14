import pytest
from orion_finance_sdk_py.contracts import OrionConfig

try:
    from ape import networks

    HAS_APE = True
except ImportError:
    HAS_APE = False


@pytest.mark.skipif(not HAS_APE, reason="ape not installed")
def test_orion_config_on_fork():
    """Test interaction with OrionConfig on a Sepolia fork."""
    # The SDK now supports this via ORION_CONFIG_ADDRESS that is set in .env under /tests

    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        config = OrionConfig()

        print(f"\n--- OrionConfig @ {config.contract_address} ---")

        # 1. Check System State
        is_idle = config.is_system_idle()
        print(f"System Idle: {is_idle}")

        # 2. Fetch Whitelisted Assets
        assets = config.whitelisted_assets
        print(f"Whitelisted Assets Count: {len(assets)}")
        assert len(assets) > 0

        # 3. Check Risk Free Rate
        rf_rate = config.risk_free_rate
        print(f"Risk Free Rate: {rf_rate}")

        # 4. Check Underlying Asset
        underlying = config.underlying_asset
        print(f"Underlying Asset: {underlying}")
        assert underlying.startswith("0x")


@pytest.mark.skipif(not HAS_APE, reason="ape not installed")
def test_fork_connection():
    with networks.ethereum.sepolia_fork.use_provider("hardhat"):
        block_number = networks.active_provider.get_block("latest").number
        assert block_number > 0
        print(f"Connected to sepolia fork at block {block_number}")
