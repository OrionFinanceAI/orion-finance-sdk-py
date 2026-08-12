import os
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from orion_finance_sdk_py.contracts import (
    _VIEW_CALL_TX,
    LiquidityOrchestrator,
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
    PriceAdapterRegistry,
    VaultFactory,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS, VaultType
from web3 import Web3

# Load .env at import so env vars are set before pytest collects/runs
_root = Path(__file__).resolve().parents[1]
for _env_path in (
    _root / ".env",
    Path.cwd() / ".env",
    Path(__file__).resolve().parent / ".env",
):
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        break

# Snapshot at import: sepolia_fork pops RPC_URL later, so skip logic cannot rely on env then.
_HAS_FORK_UPSTREAM = bool(
    (os.getenv("ALCHEMY_API_KEY") or "").strip()
    or (os.getenv("RPC_URL") or "").strip()
    or (os.getenv("WEB3_ETHEREUM_SEPOLIA_ALCHEMY_API_KEY") or "").strip()
    or (os.getenv("WEB3_ALCHEMY_API_KEY") or "").strip()
)

try:
    from ape import accounts, networks

    HAS_APE = True
except ImportError:
    HAS_APE = False
    accounts = networks = None  # type: ignore[assignment]

try:
    from ape_hardhat.exceptions import HardhatSubprocessError
except ImportError:
    HardhatSubprocessError = None  # type: ignore[misc,assignment]


@pytest.fixture(autouse=True)
def _require_ape_and_fork_config():
    """Skip fork tests when ape is not installed or fork env is not set."""
    if not HAS_APE:
        pytest.skip("ape not installed")
    if not _HAS_FORK_UPSTREAM:
        pytest.skip(
            "Fork not configured: set ALCHEMY_API_KEY or RPC_URL in .env "
            "(or rely on tests/conftest.py mirroring from an Alchemy RPC_URL)"
        )


@pytest.fixture(scope="module")
def sepolia_fork():
    """Shared Hardhat Sepolia fork (module-scoped). Sets ORION_USE_APE_PROVIDER=1 because
    OrionSmartContract.load_dotenv can restore RPC_URL and bypass the fork; pops RPC_URL
    then restores both in finally."""
    _prev_rpc = os.environ.pop("RPC_URL", None)
    _prev_use_ape = os.environ.get("ORION_USE_APE_PROVIDER")
    os.environ["ORION_USE_APE_PROVIDER"] = "1"
    try:
        try:
            with networks.ethereum.sepolia_fork.use_provider("hardhat"):
                prov = networks.active_provider
                w3 = getattr(prov, "web3", None) if prov is not None else None
                if prov is None or w3 is None:
                    pytest.skip(
                        "Ape active provider is not connected (cannot run fork tests)"
                    )
                _is_conn = getattr(w3, "is_connected", None) or getattr(
                    w3, "isConnected", None
                )
                if _is_conn is not None and not _is_conn():
                    pytest.skip(
                        "Ape active provider is not connected (cannot run fork tests)"
                    )
                yield
        except Exception as exc:
            if (
                HardhatSubprocessError is not None
                and isinstance(exc, HardhatSubprocessError)
                and "Unable to find Hardhat binary" in str(exc)
            ):
                pytest.skip(
                    "Hardhat CLI not found. From the repository root run: npm ci "
                    "(same as CI 'Install root Node deps'); fork tests need node_modules/hardhat."
                )
            raise
    finally:
        if _prev_use_ape is None:
            os.environ.pop("ORION_USE_APE_PROVIDER", None)
        else:
            os.environ["ORION_USE_APE_PROVIDER"] = _prev_use_ape
        if _prev_rpc is not None:
            os.environ["RPC_URL"] = _prev_rpc


def test_comprehensive_config_on_fork(sepolia_fork):
    """Extensive testing of OrionConfig and linked components on Sepolia fork."""
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
    print(f"Netting Fee Coeff: {config.netting_fee_coefficient}")
    print(f"RS Fee Coeff: {config.rs_fee_coefficient}")

    # 4. Test LiquidityOrchestrator integration
    lo = LiquidityOrchestrator()
    print(f"\n--- [LiquidityOrchestrator @ {lo.contract_address}] ---")
    print(f"Target Buffer Ratio: {lo.target_buffer_ratio}")
    print(f"Epoch Duration: {lo.epoch_duration}s")
    assert lo.epoch_duration > 0


def test_vault_getters_on_fork(sepolia_fork, monkeypatch):
    """Dynamically discover and test OrionTransparentVaults from OrionConfig."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults

    if not vaults:
        pytest.skip("No Orion Transparent Vaults found in OrionConfig")

    print(f"\nDiscovered {len(vaults)} transparent vaults.")

    for i, vault_addr in enumerate(vaults):
        print(f"\n--- [Vault #{i}: {vault_addr}] ---")
        monkeypatch.setenv("ORION_VAULT_ADDRESS", vault_addr)
        vault = OrionTransparentVault()

        assert vault.manager_address and isinstance(vault.manager_address, str)
        assert vault.strategist_address and isinstance(vault.strategist_address, str)
        assert vault.total_assets >= 0
        assert vault.share_price > 0
        assert vault.active_fee_model is not None
        assert isinstance(vault.active_fee_model, dict)
        portfolio = vault.get_portfolio()
        assert isinstance(portfolio, dict)

        print(f"Manager: {vault.manager_address}")
        print(f"Strategist: {vault.strategist_address}")
        print(f"Total Assets: {vault.total_assets}")
        print(f"Share Price: {vault.share_price}")
        print(f"Active Fee Model: {vault.active_fee_model}")
        print(f"Portfolio: {portfolio}")


def test_vault_pending_state_readable_on_fork(sepolia_fork, monkeypatch):
    """Pending deposit/redeem state is readable on fork; asserts types and non-negative values."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No vaults to test pending ops")

    vault_addr = vaults[0]
    monkeypatch.setenv("ORION_VAULT_ADDRESS", vault_addr)
    vault = OrionTransparentVault()

    pending_dep = vault.pending_deposit(10)
    pending_red = vault.pending_redeem(10)
    assert isinstance(pending_dep, int), "pending_deposit should return int"
    assert isinstance(pending_red, int), "pending_redeem should return int"
    assert pending_dep >= 0, "pending_deposit should be non-negative"
    assert pending_red >= 0, "pending_redeem should be non-negative"


def test_fork_connection(sepolia_fork):
    block_number = networks.active_provider.get_block("latest").number
    assert block_number > 0
    print(f"\n[Hardhat Fork] Latest Block: {block_number}")


def test_orion_config_v2_properties_on_fork(sepolia_fork):
    """OrionConfig v2 properties against Sepolia fork state."""
    config = OrionConfig()

    assert config.min_deposit_amount >= 0
    assert config.min_redeem_amount >= 0
    assert config.fee_change_cooldown_duration >= 0
    assert config.max_fulfill_batch_size > 0

    underlying = config.underlying_asset
    assert (
        underlying is not None and len(underlying) == 42 and underlying.startswith("0x")
    )

    assert config.risk_free_rate >= 0

    names = config.whitelisted_asset_names
    assets = config.whitelisted_assets
    assert len(names) == len(assets), (
        "whitelisted_asset_names length must match whitelisted_assets"
    )


def test_orion_config_system_idle_on_fork(sepolia_fork):
    """OrionConfig is_system_idle reflects chain state."""
    config = OrionConfig()
    idle = config.is_system_idle()
    assert isinstance(idle, bool)


def test_orion_config_is_orion_vault_on_fork(sepolia_fork):
    """OrionConfig is_orion_vault: registered vaults True, zero address False."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults

    for addr in vaults:
        assert config.is_orion_vault(addr) is True

    assert config.is_orion_vault(ZERO_ADDRESS) is False


def test_orion_config_managers_whitelisted_on_fork(sepolia_fork, monkeypatch):
    """Every registered vault's manager is whitelisted in OrionConfig."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    for vault_addr in vaults:
        monkeypatch.setenv("ORION_VAULT_ADDRESS", vault_addr)
        vault = OrionTransparentVault()
        manager = vault.manager_address
        assert config.is_whitelisted_manager(manager), (
            f"Manager {manager} of vault {vault_addr} should be whitelisted"
        )


def test_liquidity_orchestrator_state_on_fork(sepolia_fork):
    """LiquidityOrchestrator slippage_tolerance, target_buffer_ratio, epoch_duration from chain."""
    lo = LiquidityOrchestrator()
    assert lo.slippage_tolerance >= 0
    assert lo.target_buffer_ratio >= 0
    assert lo.epoch_duration > 0


def test_vault_factory_address_matches_config_on_fork(sepolia_fork):
    """VaultFactory(transparent) address equals OrionConfig.transparentVaultFactory()."""
    config = OrionConfig()
    expected = config.contract.functions.transparentVaultFactory().call(_VIEW_CALL_TX)
    factory = VaultFactory(vault_type=VaultType.TRANSPARENT.value)
    assert factory.contract_address.lower() == expected.lower()


def test_vault_share_price_convert_consistency_on_fork(sepolia_fork, monkeypatch):
    """Vault share_price equals convertToAssets(10**decimals) from contract."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vaults[0])
    vault = OrionTransparentVault()

    decimals = vault.contract.functions.decimals().call(_VIEW_CALL_TX)
    one_share = 10**decimals
    assert vault.share_price == vault.convert_to_assets(one_share)


def test_vault_share_price_at_recent_block_on_fork(sepolia_fork):
    """share_price_at(past block) is readable and consistent with convert_to_assets."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    vault = OrionTransparentVault(contract_address=vaults[0])
    latest = vault.w3.eth.block_number
    past = max(0, latest - 10)
    at_past = vault.share_price_at(past)
    at_latest = vault.share_price
    assert at_past > 0
    assert at_latest > 0
    # Same block should match the live property when querying latest
    assert vault.share_price_at(latest) == at_latest


def test_vault_name_symbol_and_intent_on_fork(sepolia_fork):
    """Vault name/symbol are non-empty; get_intent returns a weight dict."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    vault = OrionTransparentVault(contract_address=vaults[0])
    assert isinstance(vault.name, str) and len(vault.name) > 0
    assert isinstance(vault.symbol, str) and len(vault.symbol) > 0
    assert vault.decimals > 0

    intent = vault.get_intent()
    assert isinstance(intent, dict)
    if intent:
        assert abs(sum(intent.values()) - 1.0) < 1e-6


def test_vault_can_request_deposit_and_max_deposit_on_fork(sepolia_fork, monkeypatch):
    """Vault can_request_deposit and max_deposit for a receiver on fork."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vaults[0])
    vault = OrionTransparentVault()

    receiver = accounts.test_accounts[0].address
    can_deposit = vault.can_request_deposit(receiver)
    assert isinstance(can_deposit, bool)

    max_dep = vault.max_deposit(receiver)
    assert max_dep >= 0


def test_vault_is_decommissioning_on_fork(sepolia_fork, monkeypatch):
    """Vault is_decommissioning reflects chain state."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vaults[0])
    vault = OrionTransparentVault()
    assert isinstance(vault.is_decommissioning, bool)


def test_vault_pending_deposit_redeem_non_negative_on_fork(sepolia_fork, monkeypatch):
    """Vault pending_deposit and pending_redeem are non-negative with default and explicit batch size."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vaults[0])
    vault = OrionTransparentVault()

    batch = config.max_fulfill_batch_size
    assert vault.pending_deposit() >= 0
    assert vault.pending_deposit(batch) >= 0
    assert vault.pending_redeem() >= 0
    assert vault.pending_redeem(batch) >= 0


def test_vault_portfolio_tokens_whitelisted_on_fork(sepolia_fork, monkeypatch):
    """Every token in a vault's portfolio is whitelisted in OrionConfig."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    whitelisted = {a.lower() for a in config.whitelisted_assets}

    for vault_addr in vaults:
        monkeypatch.setenv("ORION_VAULT_ADDRESS", vault_addr)
        vault = OrionTransparentVault()
        portfolio = vault.get_portfolio()
        for token in portfolio:
            assert token.lower() in whitelisted, (
                f"Portfolio token {token} not whitelisted"
            )


def test_price_adapter_registry_prices_on_fork(sepolia_fork):
    """PriceAdapterRegistry returns a price for every investment-universe asset."""
    config = OrionConfig()
    universe = config.whitelisted_assets
    if not universe:
        pytest.skip("No whitelisted assets")

    registry = PriceAdapterRegistry()
    assert registry.contract_address
    assert registry.price_adapter_decimals >= 0

    prices = registry.get_prices()
    assert len(prices) == len(universe)
    for asset in universe:
        key = next(k for k in prices if k.lower() == asset.lower())
        assert isinstance(prices[key], int)
        assert prices[key] > 0


def test_vault_portfolio_pct_tvl_on_fork(sepolia_fork, monkeypatch):
    """get_portfolio_pct_tvl weights sum to ~1 when the vault has holdings."""
    config = OrionConfig()
    vaults = config.orion_transparent_vaults
    if not vaults:
        pytest.skip("No Orion Transparent Vaults found")

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vaults[0])
    vault = OrionTransparentVault()
    portfolio = vault.get_portfolio()
    if not portfolio:
        pytest.skip("Vault portfolio is empty")

    pct = vault.get_portfolio_pct_tvl()
    assert set(k.lower() for k in pct) == set(k.lower() for k in portfolio)
    assert abs(sum(pct.values()) - 1.0) < 1e-9
    assert vault.point_in_time_total_assets() > 0


def test_orion_config_uses_ape_provider_when_rpc_unset(sepolia_fork, monkeypatch):
    """OrionConfig uses ape's active provider when RPC_URL is not set (user read path)."""
    monkeypatch.delenv("RPC_URL", raising=False)
    with patch("orion_finance_sdk_py.contracts.load_dotenv"):
        config = OrionConfig()
    assert config.underlying_asset is not None
    assert len(config.underlying_asset) == 42


def test_orion_config_uses_env_address_when_set(sepolia_fork, monkeypatch):
    """OrionConfig uses ORION_CONFIG_ADDRESS when set (user/config override)."""
    from orion_finance_sdk_py.types import CHAIN_CONFIG

    expected_addr = CHAIN_CONFIG[11155111]["OrionConfig"]
    monkeypatch.setenv("ORION_CONFIG_ADDRESS", expected_addr)
    config = OrionConfig()
    assert config.contract_address.lower() == expected_addr.lower()
    assert config.underlying_asset is not None


def test_list_whitelisted_assets_logic_on_fork(sepolia_fork, capsys):
    """User path: list whitelisted assets from chain via CLI logic (no admin)."""
    from orion_finance_sdk_py.cli import _list_whitelisted_assets_logic

    _list_whitelisted_assets_logic()
    out, _ = capsys.readouterr()
    assert "whitelisted" in out.lower() or "Total:" in out


def test_get_investment_universe_on_fork(sepolia_fork):
    """User path: get_investment_universe alias equals whitelisted_assets."""
    config = OrionConfig()
    universe = config.get_investment_universe
    assets = config.whitelisted_assets
    assert universe == assets
    if assets:
        assert config.is_whitelisted(assets[0])


# Hardhat / Anvil default funded account #0 (matches Ape test_accounts[0]).
_HH_ACCOUNT0_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)
# §17.2 test-vector recipient public key (valid X25519 pkR for Orion HPKE).
_HPKE_TEST_PK_R = bytes.fromhex(
    "b1f1b840de7a3241b02748cf9b05b74dc8c5e8451298738817bd76aa8ebe8c2b"
)


def _impersonate_send(w3, *, from_address: str, to: str, data: bytes) -> dict:
    """Send an unlocked Hardhat tx from an impersonated account."""
    from_address = Web3.to_checksum_address(from_address)
    to = Web3.to_checksum_address(to)
    w3.provider.make_request("hardhat_impersonateAccount", [from_address])
    w3.provider.make_request(
        "hardhat_setBalance",
        [from_address, hex(10**18)],
    )
    tx_hash = w3.eth.send_transaction(
        {
            "from": from_address,
            "to": to,
            "data": data,
            "gas": 3_000_000,
        }
    )
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] != 1:
        raise AssertionError(
            f"Impersonated tx from {from_address} to {to} failed "
            f"(status={receipt['status']})"
        )
    return receipt


def _ape_account_private_key(account) -> str:
    """Return a 0x-prefixed private key for an Ape test account."""
    key = getattr(account, "private_key", None)
    if key is None:
        raise AttributeError("Ape test account has no private_key")
    if isinstance(key, bytes):
        return "0x" + key.hex()
    key_str = str(key)
    return key_str if key_str.startswith("0x") else "0x" + key_str


def test_encrypted_vault_deploy_encrypt_submit_on_fork(sepolia_fork, monkeypatch):
    """Whitelist manager → deploy encrypted vault → HPKE-seal intent → submitIntent."""
    config = OrionConfig()
    if not config.is_system_idle():
        pytest.skip("System is not Idle; cannot deploy or submit intent")

    enc_factory = config.encrypted_vault_factory
    if not enc_factory or enc_factory == ZERO_ADDRESS:
        pytest.skip("EncryptedVaultFactory not configured on this fork")

    assets = config.whitelisted_assets
    if not assets:
        pytest.skip("No whitelisted assets for intent")

    manager_acct = accounts.test_accounts[0]
    # Prefer a distinct strategist; fall back to manager if private key unavailable.
    strategist_acct = accounts.test_accounts[1]
    try:
        manager_key = _ape_account_private_key(manager_acct)
    except AttributeError:
        manager_key = _HH_ACCOUNT0_KEY
        # Verify fallback matches Hardhat account #0
        derived = config.w3.eth.account.from_key(manager_key).address
        if derived.lower() != manager_acct.address.lower():
            pytest.skip("Cannot resolve private key for manager test account")

    try:
        strategist_key = _ape_account_private_key(strategist_acct)
        strategist_address = Web3.to_checksum_address(strategist_acct.address)
    except AttributeError:
        strategist_key = manager_key
        strategist_address = Web3.to_checksum_address(manager_acct.address)

    manager_address = Web3.to_checksum_address(manager_acct.address)

    # Owner whitelist (admin path only for fork setup — not an SDK public API).
    owner = config.contract.functions.owner().call(_VIEW_CALL_TX)
    if not config.is_whitelisted_manager(manager_address):
        data = config.contract.functions.addWhitelistedManager(
            manager_address
        )._encode_transaction_data()
        _impersonate_send(
            config.w3,
            from_address=owner,
            to=config.contract_address,
            data=data,
        )
    assert config.is_whitelisted_manager(manager_address)

    # Ensure HPKE recipient key is set so Intent.encrypt() can seal on-chain pkR.
    try:
        pk = config.hpke_public_key
        assert len(pk) == 32
    except ValueError:
        data = config.contract.functions.setHpkePublicKey(
            _HPKE_TEST_PK_R
        )._encode_transaction_data()
        _impersonate_send(
            config.w3,
            from_address=owner,
            to=config.contract_address,
            data=data,
        )
        assert config.hpke_public_key == _HPKE_TEST_PK_R

    monkeypatch.setenv("MANAGER_PRIVATE_KEY", manager_key)
    monkeypatch.setenv("STRATEGIST_PRIVATE_KEY", strategist_key)

    factory = VaultFactory(vault_type=VaultType.ENCRYPTED.value)
    assert factory.contract_address.lower() == enc_factory.lower()

    result = factory.create_orion_vault(
        strategist_address=strategist_address,
        name="Fork Enc Vault",
        symbol="FENC",
        fee_type=0,
        performance_fee=0,
        management_fee=0,
        deposit_access_control=ZERO_ADDRESS,
    )
    assert result.receipt["status"] == 1
    vault_addr = factory.get_vault_address_from_result(result)
    assert vault_addr, "OrionVaultCreated event missing vault address"
    assert config.is_encrypted_vault(vault_addr)
    assert config.is_orion_vault(vault_addr)

    monkeypatch.setenv("ORION_VAULT_ADDRESS", vault_addr)
    vault = OrionEncryptedVault()
    assert vault.manager_address.lower() == manager_address.lower()
    assert vault.strategist_address.lower() == strategist_address.lower()

    scale = 10**config.strategist_intent_decimals
    order_intent = {Web3.to_checksum_address(assets[0]): scale}

    tx_result = vault.submit_order_intent(order_intent)
    assert tx_result.receipt["status"] == 1

    intent_blob = vault.get_intent()
    assert isinstance(intent_blob, (bytes, bytearray))
    assert len(intent_blob) >= 48
