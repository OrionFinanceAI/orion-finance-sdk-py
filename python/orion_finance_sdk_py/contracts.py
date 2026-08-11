"""Interactions with the Orion Finance protocol contracts."""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from typing import Any, Iterable, cast

from dotenv import load_dotenv
from web3 import Web3
from web3.types import HexStr, TxReceipt

from .rpc import pick_default_rpc
from .types import CHAIN_CONFIG, ZERO_ADDRESS, VaultType
from .utils import (
    MAX_MANAGEMENT_FEE,
    MAX_PERFORMANCE_FEE,
    validate_var,
)

load_dotenv()

# Gas limit for eth_call (view) when using Hardhat fork (node cap 16M)
_VIEW_CALL_GAS = 15_000_000
_VIEW_CALL_TX = {"gas": _VIEW_CALL_GAS}

_TIMESTAMP_THRESHOLD = 1_000_000_000
_SECONDS_PER_DAY = 86_400


def _get_view_call_tx():
    """Return tx dict for view calls: gas override only when ORION_FORCE_VIEW_GAS is set (e.g. fork tests)."""
    if os.getenv("ORION_FORCE_VIEW_GAS"):
        return _VIEW_CALL_TX
    return {}


def _call_view(contract_fn, block_identifier: int | str | None = None):
    """Execute a view/pure contract call (uses gas override in fork/dev when ORION_FORCE_VIEW_GAS is set).

    Args:
        contract_fn: Bound contract function call (e.g. ``contract.functions.foo()``).
        block_identifier: Optional block number or tag (default: ``"latest"``).
    """
    tx = _get_view_call_tx()
    if block_identifier is None:
        return contract_fn.call(tx)
    return contract_fn.call(tx, block_identifier=block_identifier)


@dataclass
class TransactionResult:
    """Result of a transaction including receipt and extracted logs."""

    tx_hash: str
    receipt: TxReceipt
    decoded_logs: list[dict] | None = None


class SystemNotIdleError(RuntimeError):
    """Raised when the protocol is not idle for the requested operation."""


def load_contract_abi(contract_name: str) -> list[dict]:
    """Load the ABI for a given contract."""
    try:
        # Try to load from package data (when installed from PyPI)
        with (
            resources.files("orion_finance_sdk_py")
            .joinpath("abis", f"{contract_name}.json")
            .open() as f
        ):
            return json.load(f)["abi"]
    except (FileNotFoundError, AttributeError):
        # Fallback to local development path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abi_path = os.path.join(script_dir, "..", "abis", f"{contract_name}.json")
        with open(abi_path) as f:
            return json.load(f)["abi"]


class OrionSmartContract:
    """Base class for Orion smart contracts."""

    def __init__(self, contract_name: str, contract_address: str):
        """Initialize a smart contract."""
        rpc_url = os.getenv("RPC_URL")
        if not rpc_url:
            # Try loading from current directory explicitly
            load_dotenv(os.getcwd() + "/.env")
            rpc_url = os.getenv("RPC_URL")

        # Fork tests: load_dotenv() above can restore RPC_URL from disk; ORION_USE_APE_PROVIDER
        # forces Ape's Hardhat web3 before the HTTP branch (see tests/test_fork.py sepolia_fork).
        use_ape_provider = os.getenv("ORION_USE_APE_PROVIDER", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        if use_ape_provider:
            ape_error = None
            try:
                from ape import networks

                if networks.active_provider:
                    self.w3 = networks.active_provider.web3
                    self.chain_id = self.w3.eth.chain_id
                    self.contract_name = contract_name
                    self.contract_address = contract_address
                    self.contract = self.w3.eth.contract(
                        address=Web3.to_checksum_address(self.contract_address),
                        abi=load_contract_abi(self.contract_name),
                    )
                    return
            except (ImportError, AttributeError):
                pass
            except Exception as e:
                ape_error = e
            msg = (
                "ORION_USE_APE_PROVIDER is set but Ape has no usable active_provider. "
                "Run inside an Ape network context (e.g. sepolia_fork Hardhat)."
            )
            if ape_error is not None:
                msg += f" ({ape_error})"
            raise ValueError(msg)

        if rpc_url:
            rpc_url = validate_var(
                rpc_url,
                error_message=(
                    "RPC_URL environment variable is missing or invalid. "
                    "Please set RPC_URL in your .env file or as an environment variable. "
                ),
            )

            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            self.chain_id = self.w3.eth.chain_id

            env_chain_id = os.getenv("CHAIN_ID")
            if env_chain_id:
                try:
                    env_chain_id_int = int(env_chain_id)
                    if env_chain_id_int != self.chain_id:
                        print(
                            f"⚠️ Warning: CHAIN_ID in env ({env_chain_id}) does not match RPC chain ID ({self.chain_id})"
                        )
                except ValueError:
                    print(f"⚠️ Warning: Invalid CHAIN_ID in env: {env_chain_id}")

            self.contract_name = contract_name
            self.contract_address = contract_address
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=load_contract_abi(self.contract_name),
            )
            return

        ape_error = None
        try:
            from ape import networks

            if networks.active_provider:
                self.w3 = networks.active_provider.web3
                self.chain_id = self.w3.eth.chain_id
                self.contract_name = contract_name
                self.contract_address = contract_address
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(self.contract_address),
                    abi=load_contract_abi(self.contract_name),
                )
                return
        except (ImportError, AttributeError):
            pass
        except Exception as e:
            ape_error = e

        default_rpc = pick_default_rpc()
        if default_rpc:
            self.w3 = Web3(Web3.HTTPProvider(default_rpc))
            self.chain_id = self.w3.eth.chain_id
            self.contract_name = contract_name
            self.contract_address = contract_address
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=load_contract_abi(self.contract_name),
            )
            return

        msg = (
            "RPC_URL environment variable is missing or invalid, and no default "
            "public RPC responded. Please set RPC_URL in your .env file or as an "
            "environment variable."
        )
        if ape_error is not None:
            msg += f" (Ape provider failed: {ape_error})"
            raise ValueError(msg) from ape_error
        raise ValueError(msg)

    def block_at_timestamp(self, timestamp: int) -> int:
        """Return the latest block number whose timestamp is <= ``timestamp``.

        Uses binary search over ``eth_getBlockByNumber``. For long historical
        series prefer a dedicated ``RPC_URL`` (public endpoints are rate-limited).
        """
        if timestamp < 0:
            raise ValueError("timestamp must be non-negative")

        latest = self.w3.eth.block_number
        latest_block = self.w3.eth.get_block(latest)
        if timestamp >= latest_block["timestamp"]:
            return latest

        earliest = 0
        earliest_block = self.w3.eth.get_block(earliest)
        if timestamp < earliest_block["timestamp"]:
            raise ValueError(
                f"timestamp {timestamp} is before the earliest block "
                f"({earliest_block['timestamp']})"
            )

        lo, hi = earliest, latest
        while lo < hi:
            mid = (lo + hi + 1) // 2
            mid_ts = self.w3.eth.get_block(mid)["timestamp"]
            if mid_ts <= timestamp:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _resolve_block(self, value: datetime | int) -> int:
        """Resolve a datetime, unix timestamp, or block number to a block number."""
        if isinstance(value, datetime):
            ts = (
                value
                if value.tzinfo is not None
                else value.replace(tzinfo=timezone.utc)
            )
            return self.block_at_timestamp(int(ts.timestamp()))
        if isinstance(value, int):
            if value >= _TIMESTAMP_THRESHOLD:
                return self.block_at_timestamp(value)
            return value

    def _daily_sample_points(
        self,
        start: datetime | int,
        end: datetime | int | None = None,
    ) -> list[tuple[int, int]]:
        """Sample ``(timestamp, block)`` pairs at daily cadence over a range.

        Ensures the end block is included when the last daily step did not land
        on it. Public RPCs are rate-limited - use a dedicated ``RPC_URL`` for
        long series.
        """
        start_block = self._resolve_block(start)
        end_block = (
            self.w3.eth.block_number if end is None else self._resolve_block(end)
        )
        if end_block < start_block:
            raise ValueError(
                f"end block ({end_block}) is before start block ({start_block})"
            )

        start_ts = int(self.w3.eth.get_block(start_block)["timestamp"])
        end_ts = int(self.w3.eth.get_block(end_block)["timestamp"])

        points: list[tuple[int, int]] = []
        sample_ts = start_ts
        while sample_ts <= end_ts:
            block = self.block_at_timestamp(sample_ts)
            # Clamp to the requested window (binary search can land slightly outside
            # if the chain has gaps, but keep samples within [start_block, end_block]).
            block = max(start_block, min(block, end_block))
            block_data = self.w3.eth.get_block(block)
            points.append((int(block_data["timestamp"]), block))
            sample_ts += _SECONDS_PER_DAY

        # Ensure the end of the range is represented when the last daily step
        # did not land on end_ts.
        if not points or points[-1][1] != end_block:
            end_data = self.w3.eth.get_block(end_block)
            points.append((int(end_data["timestamp"]), end_block))

        return points

    def _wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120
    ) -> TxReceipt:
        """Wait for a transaction to be processed and return the receipt."""
        return self.w3.eth.wait_for_transaction_receipt(
            cast(HexStr, tx_hash), timeout=timeout
        )

    def _decode_logs(self, receipt: TxReceipt) -> list[dict]:
        """Decode logs from a transaction receipt."""
        decoded_logs = []
        for log in receipt["logs"]:
            # Only process logs from this contract
            if log["address"].lower() != self.contract_address.lower():
                continue

            # Try to decode the log with each event in the contract
            for event in cast(Iterable[Any], self.contract.events):
                try:
                    decoded_log = event.process_log(log)
                    decoded_logs.append(
                        {
                            "event": decoded_log.event,
                            "args": dict(decoded_log.args),
                            "address": decoded_log.address,
                            "blockHash": decoded_log.blockHash.hex(),
                            "blockNumber": decoded_log.blockNumber,
                            "logIndex": decoded_log.logIndex,
                            "transactionHash": decoded_log.transactionHash.hex(),
                            "transactionIndex": decoded_log.transactionIndex,
                        }
                    )
                    break  # Successfully decoded, move to next log
                except Exception:
                    # This event doesn't match this log, try the next event
                    continue
        return decoded_logs


class OrionConfig(OrionSmartContract):
    """OrionConfig contract."""

    def __init__(self):
        """Initialize the OrionConfig contract."""
        # Check for manual address override first
        contract_address = os.getenv("ORION_CONFIG_ADDRESS")

        if not contract_address:
            # Default to Sepolia if not specified, but prefer env var
            chain_id = int(os.getenv("CHAIN_ID", "11155111"))

            if chain_id in CHAIN_CONFIG:
                contract_address = CHAIN_CONFIG[chain_id]["OrionConfig"]
            else:
                raise ValueError(
                    f"Unsupported CHAIN_ID: {chain_id}. Please check CHAIN_CONFIG in types.py or set CHAIN_ID env var correctly."
                )

        super().__init__(
            contract_name="OrionConfig",
            contract_address=contract_address,
        )

    @property
    def underlying_asset(self) -> str:
        """Fetch the underlying asset address."""
        return _call_view(self.contract.functions.underlyingAsset())

    @property
    def hpke_public_key(self) -> bytes:
        """Fetch the Orion HPKE recipient public key (X25519, 32 raw bytes)."""
        raw = _call_view(self.contract.functions.hpkePublicKey())
        if isinstance(raw, bytes):
            pk = raw
        elif isinstance(raw, str):
            hex_str = raw[2:] if raw.startswith(("0x", "0X")) else raw
            pk = bytes.fromhex(hex_str)
        elif isinstance(raw, int):
            pk = raw.to_bytes(32, "big")
        else:
            pk = bytes(raw)

        if len(pk) != 32:
            raise ValueError(f"hpkePublicKey must be 32 bytes, got {len(pk)}")
        if pk == b"\x00" * 32:
            raise ValueError("hpkePublicKey is unset (zero bytes32)")
        return pk

    @property
    def strategist_intent_decimals(self) -> int:
        """Fetch the strategist intent decimals from the OrionConfig contract."""
        return _call_view(self.contract.functions.strategistIntentDecimals())

    @property
    def manager_intent_decimals(self) -> int:
        """Alias for strategist_intent_decimals."""
        return self.strategist_intent_decimals

    def token_decimals(self, token_address: str) -> int:
        """Fetch the decimals of a token address."""
        return _call_view(
            self.contract.functions.tokenDecimals(
                Web3.to_checksum_address(token_address)
            )
        )

    @property
    def all_token_decimals(self) -> list[int]:
        """Fetch decimals for all whitelisted assets (parallel to ``whitelisted_assets``)."""
        return list(_call_view(self.contract.functions.getAllTokenDecimals()))

    @property
    def whitelisted_assets_length(self) -> int:
        """Fetch the number of whitelisted assets."""
        return _call_view(self.contract.functions.whitelistedAssetsLength())

    @property
    def risk_free_rate(self) -> int:
        """Fetch the risk free rate from the OrionConfig contract."""
        return _call_view(self.contract.functions.riskFreeRate())

    @property
    def whitelisted_assets(self) -> list[str]:
        """Fetch all whitelisted asset addresses from the OrionConfig contract."""
        return _call_view(self.contract.functions.getAllWhitelistedAssets())

    @property
    def whitelisted_asset_names(self) -> list[str]:
        """Fetch all whitelisted asset names from the OrionConfig contract."""
        return _call_view(self.contract.functions.getAllWhitelistedAssetNames())

    @property
    def get_investment_universe(self) -> list[str]:
        """Alias for whitelisted_assets (Investment Universe)."""
        return self.whitelisted_assets

    def is_whitelisted(self, token_address: str) -> bool:
        """Check if a token address is whitelisted."""
        return _call_view(
            self.contract.functions.isWhitelisted(
                Web3.to_checksum_address(token_address)
            )
        )

    def is_whitelisted_manager(self, manager_address: str) -> bool:
        """Check if a manager address is whitelisted."""
        return _call_view(
            self.contract.functions.isWhitelistedManager(
                Web3.to_checksum_address(manager_address)
            )
        )

    def is_orion_vault(self, vault_address: str) -> bool:
        """Check if an address is a registered Orion vault."""
        return _call_view(
            self.contract.functions.isOrionVault(
                Web3.to_checksum_address(vault_address)
            )
        )

    def is_encrypted_vault(self, vault_address: str) -> bool:
        """Check if an address is a registered Orion encrypted vault."""
        return _call_view(
            self.contract.functions.isEncryptedVault(
                Web3.to_checksum_address(vault_address)
            )
        )

    @property
    def orion_transparent_vaults(self) -> list[str]:
        """Fetch all Orion transparent vault addresses from the OrionConfig contract."""
        return _call_view(self.contract.functions.getAllOrionVaults(0))

    @property
    def orion_encrypted_vaults(self) -> list[str]:
        """Fetch all Orion encrypted vault addresses from the OrionConfig contract."""
        return _call_view(self.contract.functions.getAllOrionVaults(1))

    @property
    def min_deposit_amount(self) -> int:
        """Fetch the minimum deposit amount from the OrionConfig contract."""
        return _call_view(self.contract.functions.minDepositAmount())

    @property
    def min_redeem_amount(self) -> int:
        """Fetch the minimum redeem amount from the OrionConfig contract."""
        return _call_view(self.contract.functions.minRedeemAmount())

    @property
    def netting_fee_coefficient(self) -> int:
        """Fetch the netting fee coefficient from the OrionConfig contract."""
        return _call_view(self.contract.functions.nettingFeeCoefficient())

    @property
    def rs_fee_coefficient(self) -> int:
        """Fetch the revenue share fee coefficient from the OrionConfig contract."""
        return _call_view(self.contract.functions.rsFeeCoefficient())

    @property
    def fee_change_cooldown_duration(self) -> int:
        """Fetch the fee change cooldown duration in seconds."""
        return _call_view(self.contract.functions.feeChangeCooldownDuration())

    @property
    def max_fulfill_batch_size(self) -> int:
        """Fetch the maximum fulfill batch size."""
        return _call_view(self.contract.functions.maxFulfillBatchSize())

    def is_system_idle(self) -> bool:
        """Check if the system is in idle state, required for vault deployment."""
        return _call_view(self.contract.functions.isSystemIdle())

    @property
    def price_adapter_registry(self) -> str:
        """Fetch the PriceAdapterRegistry contract address."""
        return _call_view(self.contract.functions.priceAdapterRegistry())

    @property
    def price_adapter_decimals(self) -> int:
        """Fetch the price adapter decimals from OrionConfig."""
        return _call_view(self.contract.functions.priceAdapterDecimals())

    @property
    def liquidity_orchestrator(self) -> str:
        """Fetch the LiquidityOrchestrator contract address."""
        return _call_view(self.contract.functions.liquidityOrchestrator())

    @property
    def transparent_vault_factory(self) -> str:
        """Fetch the TransparentVaultFactory address."""
        return _call_view(self.contract.functions.transparentVaultFactory())

    @property
    def encrypted_vault_factory(self) -> str:
        """Fetch the EncryptedVaultFactory address."""
        return _call_view(self.contract.functions.encryptedVaultFactory())

    @property
    def orion_managers(self) -> list[str]:
        """Fetch all whitelisted Orion manager addresses."""
        return _call_view(self.contract.functions.getAllOrionManagers())

    def is_decommissioned_vault(self, vault_address: str) -> bool:
        """Check if a vault is fully decommissioned."""
        return _call_view(
            self.contract.functions.isDecommissionedVault(
                Web3.to_checksum_address(vault_address)
            )
        )

    def is_decommissioning_vault(self, vault_address: str) -> bool:
        """Check if a vault is currently decommissioning."""
        return _call_view(
            self.contract.functions.isDecommissioningVault(
                Web3.to_checksum_address(vault_address)
            )
        )

    @property
    def decommissioned_vaults(self) -> list[str]:
        """Fetch all decommissioned vault addresses."""
        return _call_view(self.contract.functions.getAllDecommissionedVaults())

    def remove_orion_vault(self, vault_address: str) -> TransactionResult:
        """Start vault decommissioning (manager or owner only).

        Signs with ``MANAGER_PRIVATE_KEY`` and verifies the signer is the vault
        manager.
        """
        if not self.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot remove Orion vault at this time."
            )

        vault_address = Web3.to_checksum_address(vault_address)
        if not self.is_orion_vault(vault_address):
            raise ValueError(
                f"Address {vault_address} is not a registered Orion vault."
            )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file."
            ),
        )
        account = self.w3.eth.account.from_key(manager_private_key)

        # Resolve vault manager without constructing a full OrionVault (avoids
        # re-entrant OrionConfig init); use OrionVault ABI view call.
        vault_contract = self.w3.eth.contract(
            address=vault_address,
            abi=load_contract_abi("OrionVault"),
        )
        vault_manager = _call_view(vault_contract.functions.manager())
        if account.address != Web3.to_checksum_address(vault_manager):
            raise ValueError(
                f"Signer {account.address} is not the vault manager "
                f"{vault_manager}. Cannot remove vault."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)
        tx = self.contract.functions.removeOrionVault(vault_address).build_transaction(
            {"from": account.address, "nonce": nonce}
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash.hex())
        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")
        return TransactionResult(
            tx_hash=tx_hash.hex(),
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )


class PriceAdapterRegistry(OrionSmartContract):
    """PriceAdapterRegistry contract for point-in-time asset prices."""

    def __init__(self, contract_address: str | None = None):
        """Initialize the PriceAdapterRegistry contract.

        Args:
            contract_address: Optional registry address. If omitted, resolved from
                ``OrionConfig.price_adapter_registry``.
        """
        if contract_address is None:
            config = OrionConfig()
            contract_address = config.price_adapter_registry
        super().__init__(
            contract_name="PriceAdapterRegistry",
            contract_address=contract_address,
        )

    @property
    def price_adapter_decimals(self) -> int:
        """Fetch the price adapter decimals from the registry."""
        return _call_view(self.contract.functions.priceAdapterDecimals())

    def get_price(self, asset: str, block: int | None = None) -> int:
        """Fetch the point-in-time price for a single asset.

        Args:
            asset: Token contract address.
            block: Optional block number for a historical ``eth_call``.

        Returns:
            Price scaled by ``price_adapter_decimals``.
        """
        return _call_view(
            self.contract.functions.getPrice(Web3.to_checksum_address(asset)),
            block_identifier=block,
        )

    def get_prices(
        self,
        block: int | None = None,
        assets: Iterable[str] | None = None,
    ) -> dict[str, int]:
        """Fetch point-in-time prices for the investment universe (or a subset).

        Args:
            block: Optional block number for historical prices.
            assets: Optional token addresses to price. Defaults to the full
                whitelisted investment universe from ``OrionConfig``.

        Returns:
            Mapping of checksummed asset address to price (scaled by
            ``price_adapter_decimals``).
        """
        if assets is None:
            config = OrionConfig()
            assets = config.whitelisted_assets
        return {
            Web3.to_checksum_address(asset): self.get_price(asset, block=block)
            for asset in assets
        }

    def price_history(
        self,
        start: datetime | int,
        end: datetime | int | None = None,
        interval: str = "1d",
        assets: Iterable[str] | None = None,
    ) -> list[dict]:
        """Sample PIT prices for whitelisted assets over a time range.

        No vault is required - prices come from the price adapter registry for
        the investment universe (or an optional subset). The SDK returns plain
        dicts; wrap in pandas in your notebook for return / distribution
        analysis. Public RPCs are rate-limited - use a dedicated ``RPC_URL``
        for long series.

        Args:
            start: Start as ``datetime``, unix timestamp, or block number
                (ints ``>= 1_000_000_000`` are treated as timestamps).
            end: End bound (same types as ``start``). Defaults to latest block.
            interval: Sampling interval. Only ``"1d"`` (daily) is supported for now.
            assets: Optional token addresses to price. Defaults to the full
                whitelisted investment universe from ``OrionConfig``.

        Returns:
            List of ``{"timestamp", "block", "prices"}`` dicts where ``prices``
            maps checksummed asset address to price (scaled by
            ``price_adapter_decimals``).
        """
        if interval != "1d":
            raise ValueError(
                f"Unsupported interval {interval!r}. Only '1d' is supported."
            )

        if assets is None:
            assets = OrionConfig().whitelisted_assets

        return [
            {
                "timestamp": timestamp,
                "block": block,
                "prices": self.get_prices(block=block, assets=assets),
            }
            for timestamp, block in self._daily_sample_points(start, end)
        ]


class LiquidityOrchestrator(OrionSmartContract):
    """LiquidityOrchestrator contract."""

    def __init__(self):
        """Initialize the LiquidityOrchestrator contract."""
        config = OrionConfig()
        contract_address = _call_view(config.contract.functions.liquidityOrchestrator())
        super().__init__(
            contract_name="LiquidityOrchestrator",
            contract_address=contract_address,
        )

    @property
    def target_buffer_ratio(self) -> int:
        """Fetch the target buffer ratio."""
        return _call_view(self.contract.functions.targetBufferRatio())

    @property
    def slippage_tolerance(self) -> int:
        """Fetch the slippage tolerance."""
        return _call_view(self.contract.functions.slippageTolerance())

    @property
    def epoch_duration(self) -> int:
        """Fetch the epoch duration in seconds."""
        return _call_view(self.contract.functions.epochDuration())

    @property
    def buffer_amount(self) -> int:
        """Fetch the current LO underlying buffer amount."""
        return _call_view(self.contract.functions.bufferAmount())

    @property
    def current_phase(self) -> int:
        """Fetch the current epoch phase enum value."""
        return _call_view(self.contract.functions.currentPhase())

    @property
    def epoch_counter(self) -> int:
        """Fetch the epoch counter."""
        return _call_view(self.contract.functions.epochCounter())

    @property
    def pending_protocol_fees(self) -> int:
        """Fetch pending protocol fees (underlying units)."""
        return _call_view(self.contract.functions.pendingProtocolFees())

    def get_epoch_state(self) -> dict:
        """Fetch the current epoch state struct as a dict."""
        state = _call_view(self.contract.functions.getEpochState())
        return {
            "vaultsEpoch": list(state[0]),
            "activeNettingFeeCoefficient": state[1],
            "activeRsFeeCoefficient": state[2],
            "vaultFeeModels": [
                {
                    "feeType": model[0],
                    "performanceFee": model[1],
                    "managementFee": model[2],
                    "highWaterMark": model[3],
                }
                for model in state[3]
            ],
            "epochStateCommitment": state[4],
        }

    def get_asset_prices(self, assets: Iterable[str]) -> list[int]:
        """Fetch LO-reported prices for the given assets."""
        checksummed = [Web3.to_checksum_address(a) for a in assets]
        return list(_call_view(self.contract.functions.getAssetPrices(checksummed)))


class VaultFactory(OrionSmartContract):
    """VaultFactory contract."""

    def __init__(
        self,
        vault_type: str,
        contract_address: str | None = None,
    ):
        """Initialize the VaultFactory contract."""
        self.vault_type = vault_type

        if vault_type == VaultType.TRANSPARENT:
            contract_name = "TransparentVaultFactory"
            factory_getter = "transparentVaultFactory"
        elif vault_type == VaultType.ENCRYPTED:
            contract_name = "EncryptedVaultFactory"
            factory_getter = "encryptedVaultFactory"
        else:
            raise ValueError(f"Unsupported vault type: {vault_type}")

        if contract_address is None:
            config = OrionConfig()
            contract_address = _call_view(
                getattr(config.contract.functions, factory_getter)()
            )

        super().__init__(
            contract_name=contract_name,
            contract_address=contract_address,
        )

    def create_orion_vault(
        self,
        strategist_address: str,
        name: str,
        symbol: str,
        fee_type: int,
        performance_fee: int,
        management_fee: int,
        deposit_access_control: str = ZERO_ADDRESS,
    ) -> TransactionResult:
        """Create an Orion vault for a given strategist address."""
        config = OrionConfig()

        strategist_address = validate_var(
            strategist_address,
            error_message=(
                "STRATEGIST_ADDRESS is invalid. "
                "Please provide a valid strategist address."
            ),
        )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )
        account = self.w3.eth.account.from_key(manager_private_key)
        validate_var(
            account.address,
            error_message="Invalid MANAGER_PRIVATE_KEY.",
        )

        if not config.is_whitelisted_manager(account.address):
            raise ValueError(
                f"Manager {account.address} is not whitelisted to create vaults. "
                "Please contact the Orion Finance team to get whitelisted."
            )

        if len(name.encode("utf-8")) > 26:
            raise ValueError(f"Vault name '{name}' exceeds maximum length of 26 bytes.")

        if len(symbol.encode("utf-8")) > 4:
            raise ValueError(
                f"Vault symbol '{symbol}' exceeds maximum length of 4 bytes."
            )

        if performance_fee > MAX_PERFORMANCE_FEE:
            raise ValueError(
                f"Performance fee {performance_fee} exceeds maximum {MAX_PERFORMANCE_FEE}"
            )

        if management_fee > MAX_MANAGEMENT_FEE:
            raise ValueError(
                f"Management fee {management_fee} exceeds maximum {MAX_MANAGEMENT_FEE}"
            )

        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot deploy vault at this time."
            )

        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.createVault(
            strategist_address,
            name,
            symbol,
            fee_type,
            performance_fee,
            management_fee,
            Web3.to_checksum_address(deposit_access_control),
        ).estimate_gas({"from": account.address, "nonce": nonce})

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        gas_price = self.w3.eth.gas_price
        estimated_cost = gas_limit * gas_price
        balance = self.w3.eth.get_balance(account.address)

        if balance < estimated_cost:
            required_eth = self.w3.from_wei(estimated_cost, "ether")
            available_eth = self.w3.from_wei(balance, "ether")
            raise ValueError(
                f"Insufficient ETH balance. Required: {required_eth} ETH, Available: {available_eth} ETH"
            )

        tx = self.contract.functions.createVault(
            strategist_address,
            name,
            symbol,
            fee_type,
            performance_fee,
            management_fee,
            Web3.to_checksum_address(deposit_access_control),
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        try:
            receipt = self._wait_for_transaction_receipt(tx_hash_hex)
        except Exception as e:
            error_str = str(e)
            if "0xea8e4eb5" in error_str:
                raise ValueError(
                    f"Transaction reverted: Manager {account.address} is not whitelisted to create vaults."
                )
            raise e

        # Check if transaction was successful
        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        # Decode logs from the transaction receipt
        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )

    def get_vault_address_from_result(self, result: TransactionResult) -> str | None:
        """Extract the vault address from OrionVaultCreated event in the transaction result."""
        if not result.decoded_logs:
            return None

        for log in result.decoded_logs:
            if log.get("event") == "OrionVaultCreated":
                return log["args"].get("vault")

        return None


class OrionVault(OrionSmartContract):
    """OrionVault contract."""

    def __init__(self, contract_name: str, contract_address: str | None = None):
        """Initialize the OrionVault contract.

        Args:
            contract_name: On-chain contract name (ABI key).
            contract_address: Vault address. If omitted, uses ``ORION_VAULT_ADDRESS``.
        """
        if contract_address is None:
            contract_address = validate_var(
                os.getenv("ORION_VAULT_ADDRESS"),
                error_message=(
                    "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
                    "Pass contract_address=... or set ORION_VAULT_ADDRESS in your .env. "
                    "Please follow the SDK Installation instructions: https://sdk.orionfinance.ai/"
                ),
            )
        else:
            contract_address = validate_var(
                contract_address,
                error_message="Vault contract_address is missing or invalid.",
            )

        # Validate that the address is a registered Orion vault (transparent or encrypted)
        config = OrionConfig()
        if not config.is_orion_vault(contract_address):
            raise ValueError(
                f"The address {contract_address} is NOT a valid Orion vault registered "
                "in the OrionConfig contract. Please check your ORION_VAULT_ADDRESS."
            )

        super().__init__(contract_name, contract_address)

    @property
    def name(self) -> str:
        """Fetch the vault ERC-20 name."""
        return _call_view(self.contract.functions.name())

    @property
    def symbol(self) -> str:
        """Fetch the vault ERC-20 symbol."""
        return _call_view(self.contract.functions.symbol())

    @property
    def decimals(self) -> int:
        """Fetch the vault share token decimals."""
        return _call_view(self.contract.functions.decimals())

    @property
    def max_performance_fee(self) -> int:
        """Fetch the maximum performance fee allowed from the vault contract."""
        return _call_view(self.contract.functions.MAX_PERFORMANCE_FEE())

    @property
    def max_management_fee(self) -> int:
        """Fetch the maximum management fee allowed from the vault contract."""
        return _call_view(self.contract.functions.MAX_MANAGEMENT_FEE())

    @property
    def manager_address(self) -> str:
        """Fetch the manager address."""
        return _call_view(self.contract.functions.manager())

    @property
    def strategist_address(self) -> str:
        """Fetch the strategist address."""
        return _call_view(self.contract.functions.strategist())

    @property
    def is_decommissioning(self) -> bool:
        """Check if the vault is in decommissioning mode."""
        return _call_view(self.contract.functions.isDecommissioning())

    @property
    def active_fee_model(self) -> dict:
        """Fetch the currently active fee model (struct FeeModel)."""
        model = _call_view(self.contract.functions.activeFeeModel())
        return {
            "feeType": model[0],
            "performanceFee": model[1],
            "managementFee": model[2],
            "highWaterMark": model[3],
        }

    def pending_deposit(self, fulfill_batch_size: int | None = None) -> int:
        """Get total pending deposit amount across all users."""
        if fulfill_batch_size is None:
            config = OrionConfig()
            fulfill_batch_size = config.max_fulfill_batch_size
        return _call_view(self.contract.functions.pendingDeposit(fulfill_batch_size))

    def pending_redeem(self, fulfill_batch_size: int | None = None) -> int:
        """Get total pending redemption shares across all users."""
        if fulfill_batch_size is None:
            config = OrionConfig()
            fulfill_batch_size = config.max_fulfill_batch_size
        return _call_view(self.contract.functions.pendingRedeem(fulfill_batch_size))

    def pending_deposit_count(self) -> int:
        """Get the number of pending deposit requests."""
        return _call_view(self.contract.functions.pendingDepositCount())

    def pending_redeem_count(self) -> int:
        """Get the number of pending redeem requests."""
        return _call_view(self.contract.functions.pendingRedeemCount())

    def pending_redeem_batch(
        self, fulfill_batch_size: int | None = None
    ) -> tuple[list[str], list[int]]:
        """Fetch a batch of pending redeem owners and share amounts."""
        if fulfill_batch_size is None:
            config = OrionConfig()
            fulfill_batch_size = config.max_fulfill_batch_size
        owners, shares = _call_view(
            self.contract.functions.pendingRedeemBatch(fulfill_batch_size)
        )
        return list(owners), list(shares)

    @property
    def deposit_access_control(self) -> str:
        """Fetch the deposit access control contract address (``address(0)`` if none)."""
        return _call_view(self.contract.functions.depositAccessControl())

    @property
    def asset(self) -> str:
        """Fetch the vault underlying asset address."""
        return _call_view(self.contract.functions.asset())

    def balance_of(self, account: str) -> int:
        """Fetch vault share balance for an account."""
        return _call_view(
            self.contract.functions.balanceOf(Web3.to_checksum_address(account))
        )

    @property
    def total_supply(self) -> int:
        """Fetch vault share total supply."""
        return _call_view(self.contract.functions.totalSupply())

    def allowance(self, owner: str, spender: str) -> int:
        """Fetch vault share allowance."""
        return _call_view(
            self.contract.functions.allowance(
                Web3.to_checksum_address(owner),
                Web3.to_checksum_address(spender),
            )
        )

    def convert_to_shares(self, assets: int, block: int | None = None) -> int:
        """Convert assets to shares."""
        return _call_view(
            self.contract.functions.convertToShares(assets),
            block_identifier=block,
        )

    def preview_redeem(self, shares: int) -> int:
        """Preview assets received for redeeming ``shares``."""
        return _call_view(self.contract.functions.previewRedeem(shares))

    def max_deposit(self, receiver: str) -> int:
        """Fetch max deposit for ``receiver``."""
        return _call_view(
            self.contract.functions.maxDeposit(Web3.to_checksum_address(receiver))
        )

    def max_mint(self, receiver: str) -> int:
        """Fetch max mint for ``receiver``."""
        return _call_view(
            self.contract.functions.maxMint(Web3.to_checksum_address(receiver))
        )

    def max_redeem(self, owner: str) -> int:
        """Fetch max redeem for ``owner``."""
        return _call_view(
            self.contract.functions.maxRedeem(Web3.to_checksum_address(owner))
        )

    def max_withdraw(self, owner: str) -> int:
        """Fetch max withdraw for ``owner``."""
        return _call_view(
            self.contract.functions.maxWithdraw(Web3.to_checksum_address(owner))
        )

    def _execute_vault_tx(
        self,
        contract_fn_call,
        key_env: str = "MANAGER_PRIVATE_KEY",
        error_msg: str = "Private key missing for transaction.",
        gas_limit: int | None = None,
    ) -> TransactionResult:
        """Execute a vault transaction with the given contract function call.

        Args:
            contract_fn_call: The contract function call (e.g., self.contract.functions.requestDeposit(assets))
            key_env: Environment variable name for the private key (default: "MANAGER_PRIVATE_KEY")
            error_msg: Error message for validation
            gas_limit: Optional gas limit for the transaction

        Returns:
            TransactionResult with transaction hash, receipt, and decoded logs
        """
        private_key = validate_var(os.getenv(key_env), error_msg)
        account = self.w3.eth.account.from_key(private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx_params = {
            "from": account.address,
            "nonce": nonce,
        }
        if gas_limit is not None:
            tx_params["gas"] = gas_limit

        tx = contract_fn_call.build_transaction(tx_params)
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash.hex())

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash.hex(),
            receipt=receipt,
            decoded_logs=decoded_logs,
        )

    def request_deposit(
        self, assets: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Submit an asynchronous deposit request (signed with LP key by default)."""
        return self._execute_vault_tx(
            self.contract.functions.requestDeposit(assets),
            key_env=key_env,
            error_msg=f"{key_env} missing for deposit request.",
        )

    def cancel_deposit_request(
        self, amount: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Cancel a previously submitted deposit request."""
        return self._execute_vault_tx(
            self.contract.functions.cancelDepositRequest(amount),
            key_env=key_env,
            error_msg=f"{key_env} missing for cancellation.",
        )

    def request_redeem(
        self, shares: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Submit a redemption request."""
        return self._execute_vault_tx(
            self.contract.functions.requestRedeem(shares),
            key_env=key_env,
            error_msg=f"{key_env} missing for redeem request.",
        )

    def cancel_redeem_request(
        self, shares: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Cancel a previously submitted redemption request."""
        return self._execute_vault_tx(
            self.contract.functions.cancelRedeemRequest(shares),
            key_env=key_env,
            error_msg=f"{key_env} missing for cancellation.",
        )

    def redeem(
        self,
        shares: int,
        receiver: str,
        owner: str,
        *,
        key_env: str = "LP_PRIVATE_KEY",
    ) -> TransactionResult:
        """Sync ERC-4626 redeem — only allowed when the vault is decommissioned."""
        config = OrionConfig()
        if not config.is_decommissioned_vault(self.contract_address):
            raise ValueError(
                "Sync redeem is only available for decommissioned vaults. "
                "Use request_redeem while the vault is active."
            )
        return self._execute_vault_tx(
            self.contract.functions.redeem(
                shares,
                Web3.to_checksum_address(receiver),
                Web3.to_checksum_address(owner),
            ),
            key_env=key_env,
            error_msg=f"{key_env} missing for redeem.",
        )

    def approve_shares(
        self, spender: str, amount: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Approve ``spender`` to transfer vault shares."""
        return self._execute_vault_tx(
            self.contract.functions.approve(
                Web3.to_checksum_address(spender), amount
            ),
            key_env=key_env,
            error_msg=f"{key_env} missing for share approve.",
        )

    def transfer_shares(
        self, to: str, amount: int, *, key_env: str = "LP_PRIVATE_KEY"
    ) -> TransactionResult:
        """Transfer vault shares."""
        return self._execute_vault_tx(
            self.contract.functions.transfer(Web3.to_checksum_address(to), amount),
            key_env=key_env,
            error_msg=f"{key_env} missing for share transfer.",
        )

    def transfer_from_shares(
        self,
        from_address: str,
        to: str,
        amount: int,
        *,
        key_env: str = "LP_PRIVATE_KEY",
    ) -> TransactionResult:
        """Transfer vault shares via allowance."""
        return self._execute_vault_tx(
            self.contract.functions.transferFrom(
                Web3.to_checksum_address(from_address),
                Web3.to_checksum_address(to),
                amount,
            ),
            key_env=key_env,
            error_msg=f"{key_env} missing for share transferFrom.",
        )

    def update_strategist(self, new_strategist_address: str) -> TransactionResult:
        """Update the strategist address for the vault."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot update strategist at this time."
            )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )

        account = self.w3.eth.account.from_key(manager_private_key)
        # Validate that the signer is the manager
        if account.address != self.manager_address:
            raise ValueError(
                f"Signer {account.address} is not the vault manager {self.manager_address}. Cannot update strategist."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateStrategist(
            new_strategist_address
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )

    def update_fee_model(
        self, fee_type: int, performance_fee: int, management_fee: int
    ) -> TransactionResult:
        """Update the fee model for the vault."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot update fee model at this time."
            )

        if performance_fee > self.max_performance_fee:
            raise ValueError(
                f"Performance fee {performance_fee} exceeds maximum {self.max_performance_fee}"
            )

        if management_fee > self.max_management_fee:
            raise ValueError(
                f"Management fee {management_fee} exceeds maximum {self.max_management_fee}"
            )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )

        account = self.w3.eth.account.from_key(manager_private_key)
        # Validate that the signer is the manager
        if account.address != self.manager_address:
            raise ValueError(
                f"Signer {account.address} is not the vault manager {self.manager_address}. Cannot update fee model."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateFeeModel(
            fee_type, performance_fee, management_fee
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )

    @property
    def total_assets(self) -> int:
        """Fetch the total assets of the vault."""
        return _call_view(self.contract.functions.totalAssets())

    def total_assets_at(self, block: int) -> int:
        """Fetch ``totalAssets`` at a historical block."""
        return _call_view(self.contract.functions.totalAssets(), block_identifier=block)

    @property
    def pending_vault_fees(self) -> float:
        """Fetch the pending vault fees in the underlying asset."""
        config = OrionConfig()
        decimals = config.token_decimals(config.underlying_asset)
        return _call_view(self.contract.functions.pendingVaultFees()) / 10**decimals

    def transfer_manager_fees(self, amount: int) -> TransactionResult:
        """Transfer manager fees (claimVaultFees)."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot transfer manager fees at this time."
            )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )
        account = self.w3.eth.account.from_key(manager_private_key)
        if account.address != self.manager_address:
            raise ValueError(
                f"Signer {account.address} is not the vault manager "
                f"{self.manager_address}. Cannot claim fees."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.claimVaultFees(amount).build_transaction(
            {"from": account.address, "nonce": nonce}
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash.hex())
        return TransactionResult(
            tx_hash=tx_hash.hex(),
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )

    @property
    def share_price(self) -> int:
        """Fetch the current share price (value of 1 share unit)."""
        decimals = _call_view(self.contract.functions.decimals())
        return _call_view(self.contract.functions.convertToAssets(10**decimals))

    def share_price_at(self, block: int) -> int:
        """Fetch the share price (value of 1 full share) at a historical block."""
        decimals = _call_view(
            self.contract.functions.decimals(), block_identifier=block
        )
        return _call_view(
            self.contract.functions.convertToAssets(10**decimals),
            block_identifier=block,
        )

    def convert_to_assets(self, shares: int, block: int | None = None) -> int:
        """Convert shares to assets.

        Args:
            shares: Share amount in vault share units.
            block: Optional block number for a historical ``eth_call``.
        """
        return _call_view(
            self.contract.functions.convertToAssets(shares),
            block_identifier=block,
        )

    def get_portfolio(self, block: int | None = None) -> dict | bytes:
        """Get the vault portfolio.

        Args:
            block: Optional block number for a historical ``eth_call``.

        Returns:
            Transparent vaults: mapping of token address to shares.
            Encrypted vaults: opaque OrionCiphertext ``bytes`` (subclass override).
        """
        tokens, values = _call_view(
            self.contract.functions.getPortfolio(), block_identifier=block
        )
        return dict(zip(tokens, values, strict=True))

    def share_price_history(
        self,
        start: datetime | int,
        end: datetime | int | None = None,
        interval: str = "1d",
    ) -> list[dict]:
        """Sample vault share price over a time range (on-chain ``eth_call`` at each point).

        The SDK returns plain dicts; wrap in pandas in your notebook for correlation
        analysis. Public RPCs are rate-limited - use a dedicated ``RPC_URL`` for
        long series.

        Args:
            start: Start as ``datetime``, unix timestamp, or block number
                (ints ``>= 1_000_000_000`` are treated as timestamps).
            end: End bound (same types as ``start``). Defaults to latest block.
            interval: Sampling interval. Only ``"1d"`` (daily) is supported for now.

        Returns:
            List of ``{"timestamp", "block", "share_price"}`` dicts (unix timestamp,
            block number, share price in underlying units).
        """
        if interval != "1d":
            raise ValueError(
                f"Unsupported interval {interval!r}. Only '1d' is supported."
            )

        return [
            {
                "timestamp": timestamp,
                "block": block,
                "share_price": self.share_price_at(block),
            }
            for timestamp, block in self._daily_sample_points(start, end)
        ]

    def _portfolio_position_values(
        self, portfolio: dict[str, int] | None = None
    ) -> dict[str, int]:
        """Value each portfolio position using PIT prices from the registry.

        Position value (underlying units) is ``shares * price / 10**decimals``.
        """
        if portfolio is None:
            raw_portfolio = self.get_portfolio()
            if isinstance(raw_portfolio, bytes):
                raise TypeError(
                    "Encrypted vault portfolios are opaque ciphertext; "
                    "pass an explicit token→shares mapping or use a transparent vault."
                )
            portfolio = cast(dict[str, int], raw_portfolio)
        if not portfolio:
            return {}

        registry = PriceAdapterRegistry()
        prices = registry.get_prices()
        decimals = registry.price_adapter_decimals
        scale = 10**decimals

        # Normalize price keys for lookup (checksum + lowercase)
        price_by_lower = {addr.lower(): price for addr, price in prices.items()}

        values: dict[str, int] = {}
        for token, shares in portfolio.items():
            checksum = Web3.to_checksum_address(token)
            if checksum.lower() not in price_by_lower:
                raise ValueError(
                    f"No PIT price for portfolio token {checksum}. "
                    "Token may not be in the investment universe."
                )
            price = price_by_lower[checksum.lower()]
            values[checksum] = (int(shares) * int(price)) // scale
        return values

    def point_in_time_total_assets(self) -> int:
        """Estimate vault TVL from portfolio shares and PIT oracle prices.

        Returns:
            Sum of position values in underlying units (same scaling as registry
            prices after dividing by ``price_adapter_decimals``).
        """
        return sum(self._portfolio_position_values().values())

    def get_portfolio_pct_tvl(self) -> dict[str, float]:
        """Portfolio weights as fractions of PIT TVL (sum to ~1.0).

        Combines ``get_portfolio()`` with ``PriceAdapterRegistry.get_prices()``.

        Returns:
            Mapping of checksummed token address to weight in [0, 1]. Empty if
            the portfolio is empty or PIT total is zero.
        """
        position_values = self._portfolio_position_values()
        total = sum(position_values.values())
        if total <= 0:
            return {}
        return {token: value / total for token, value in position_values.items()}

    def set_deposit_access_control(
        self, access_control_address: str
    ) -> TransactionResult:
        """Set the deposit access control contract address."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot set deposit access control at this time."
            )

        manager_private_key = validate_var(
            os.getenv("MANAGER_PRIVATE_KEY"),
            error_message="MANAGER_PRIVATE_KEY environment variable is missing or invalid.",
        )
        account = self.w3.eth.account.from_key(manager_private_key)
        # Validate that the signer is the manager
        if account.address != self.manager_address:
            raise ValueError(
                f"Signer {account.address} is not the vault manager {self.manager_address}. Cannot set deposit access control."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.setDepositAccessControl(
            Web3.to_checksum_address(access_control_address)
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        receipt = self._wait_for_transaction_receipt(tx_hash_hex)
        return TransactionResult(
            tx_hash=tx_hash_hex,
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )

    def max_deposit(self, receiver: str) -> int:
        """Fetch the maximum deposit amount for a receiver."""
        return _call_view(
            self.contract.functions.maxDeposit(Web3.to_checksum_address(receiver))
        )

    def can_request_deposit(self, user: str) -> bool:
        """Check if a user is allowed to request a deposit.

        This method queries the vault's depositAccessControl contract.
        If no access control is set (zero address), it returns True.
        """
        try:
            access_control_address = _call_view(
                self.contract.functions.depositAccessControl()
            )
        except (AttributeError, ValueError):
            # If function doesn't exist in ABI or call fails due to missing method
            return True

        if access_control_address == ZERO_ADDRESS:
            return True

        # Minimal ABI for IOrionAccessControl to check permissions
        access_control_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "sender", "type": "address"}
                ],
                "name": "canRequestDeposit",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            }
        ]
        access_control = self.w3.eth.contract(
            address=access_control_address, abi=access_control_abi
        )
        return _call_view(
            access_control.functions.canRequestDeposit(Web3.to_checksum_address(user))
        )


class OrionTransparentVault(OrionVault):
    """OrionTransparentVault contract."""

    def __init__(self, contract_address: str | None = None):
        """Initialize the OrionTransparentVault contract.

        Args:
            contract_address: Vault address. If omitted, uses ``ORION_VAULT_ADDRESS``.
        """
        super().__init__("OrionTransparentVault", contract_address=contract_address)

    def get_intent(self) -> dict[str, float]:
        """Fetch the current strategist intent as fractional weights (sum ≈ 1).

        On-chain weights are scaled by ``OrionConfig.strategist_intent_decimals``.
        Returns an empty dict when no intent is set. Compare with
        ``get_portfolio_pct_tvl()`` to see expected rebalancing.
        """
        tokens, weights = _call_view(self.contract.functions.getIntent())
        if not tokens:
            return {}
        config = OrionConfig()
        scale = 10**config.strategist_intent_decimals
        return {
            Web3.to_checksum_address(token): int(weight) / scale
            for token, weight in zip(tokens, weights, strict=True)
        }

    def submit_order_intent(
        self,
        order_intent: dict[str, int],
    ) -> TransactionResult:
        """Submit a portfolio order intent.

        Args:
            order_intent: Dictionary mapping token addresses to values

        Returns:
            TransactionResult
        """
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot submit order intent at this time."
            )

        strategist_private_key = validate_var(
            os.getenv("STRATEGIST_PRIVATE_KEY"),
            error_message=(
                "STRATEGIST_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set STRATEGIST_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )

        account = self.w3.eth.account.from_key(strategist_private_key)
        # Validate that the signer is the strategist
        if account.address != self.strategist_address:
            raise ValueError(
                f"Signer {account.address} is not the vault strategist {self.strategist_address}. Cannot submit order."
            )

        nonce = self.w3.eth.get_transaction_count(account.address)

        items = [
            {"token": Web3.to_checksum_address(token), "weight": value}
            for token, value in order_intent.items()
        ]

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.submitIntent(items).estimate_gas(
            {"from": account.address, "nonce": nonce}
        )

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        tx = self.contract.functions.submitIntent(items).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )


class OrionEncryptedVault(OrionVault):
    """OrionEncryptedVault contract (confidential HPKE intents/portfolios)."""

    def __init__(self, contract_address: str | None = None):
        """Initialize the OrionEncryptedVault contract.

        Args:
            contract_address: Vault address. If omitted, uses ``ORION_VAULT_ADDRESS``.
        """
        super().__init__("OrionEncryptedVault", contract_address=contract_address)

    def get_portfolio(self, block: int | None = None) -> bytes:
        """Fetch the opaque portfolio OrionCiphertext blob.

        Args:
            block: Optional block number for a historical ``eth_call``.
        """
        return _call_view(
            self.contract.functions.getPortfolio(), block_identifier=block
        )

    def get_intent(self) -> bytes:
        """Fetch the opaque intent OrionCiphertext blob."""
        return _call_view(self.contract.functions.getIntent())

    def submit_order_intent(
        self,
        order_intent: dict[str, int],
    ) -> TransactionResult:
        """Encrypt then submit a portfolio order intent.

        Seals the plaintext weights with Orion HPKE (``Intent.encrypt()``, using
        ``OrionConfig.hpkePublicKey()``) and submits the resulting ciphertext.

        Args:
            order_intent: Dictionary mapping token addresses to scaled weights.

        Returns:
            TransactionResult
        """
        from .intent import Intent

        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot submit order intent at this time."
            )

        strategist_private_key = validate_var(
            os.getenv("STRATEGIST_PRIVATE_KEY"),
            error_message=(
                "STRATEGIST_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set STRATEGIST_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )

        account = self.w3.eth.account.from_key(strategist_private_key)
        if account.address != self.strategist_address:
            raise ValueError(
                f"Signer {account.address} is not the vault strategist "
                f"{self.strategist_address}. Cannot submit order."
            )

        ciphertext = Intent(order_intent).encrypt()

        nonce = self.w3.eth.get_transaction_count(account.address)

        gas_estimate = self.contract.functions.submitIntent(ciphertext).estimate_gas(
            {"from": account.address, "nonce": nonce}
        )
        gas_limit = int(gas_estimate * 1.2)

        tx = self.contract.functions.submitIntent(ciphertext).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )
