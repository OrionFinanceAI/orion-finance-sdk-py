"""Interactions with the Orion Finance protocol contracts."""

import json
import os
from dataclasses import dataclass
from importlib import resources

from dotenv import load_dotenv
from web3 import Web3
from web3.types import TxReceipt

from .types import CHAIN_CONFIG, ZERO_ADDRESS, VaultType
from .utils import (
    MAX_MANAGEMENT_FEE,
    MAX_PERFORMANCE_FEE,
    validate_var,
)

load_dotenv()


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

        validate_var(
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
            address=self.contract_address, abi=load_contract_abi(self.contract_name)
        )

    def _wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120
    ) -> TxReceipt:
        """Wait for a transaction to be processed and return the receipt."""
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def _decode_logs(self, receipt: TxReceipt) -> list[dict]:
        """Decode logs from a transaction receipt."""
        decoded_logs = []
        for log in receipt.logs:
            # Only process logs from this contract
            if log.address.lower() != self.contract_address.lower():
                continue

            # Try to decode the log with each event in the contract
            for event in self.contract.events:
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
        return self.contract.functions.underlyingAsset().call()

    @property
    def strategist_intent_decimals(self) -> int:
        """Fetch the strategist intent decimals from the OrionConfig contract."""
        return self.contract.functions.strategistIntentDecimals().call()

    @property
    def manager_intent_decimals(self) -> int:
        """Alias for strategist_intent_decimals."""
        return self.strategist_intent_decimals

    def token_decimals(self, token_address: str) -> int:
        """Fetch the decimals of a token address."""
        return self.contract.functions.getTokenDecimals(token_address).call()

    @property
    def risk_free_rate(self) -> int:
        """Fetch the risk free rate from the OrionConfig contract."""
        return self.contract.functions.riskFreeRate().call()

    @property
    def whitelisted_assets(self) -> list[str]:
        """Fetch all whitelisted asset addresses from the OrionConfig contract."""
        return self.contract.functions.getAllWhitelistedAssets().call()

    @property
    def whitelisted_asset_names(self) -> list[str]:
        """Fetch all whitelisted asset names from the OrionConfig contract with manual fallback."""
        return self.contract.functions.getAllWhitelistedAssetNames().call()

    @property
    def get_investment_universe(self) -> list[str]:
        """Alias for whitelisted_assets (Investment Universe)."""
        return self.whitelisted_assets

    def is_whitelisted(self, token_address: str) -> bool:
        """Check if a token address is whitelisted."""
        return self.contract.functions.isWhitelisted(
            Web3.to_checksum_address(token_address)
        ).call()

    def is_whitelisted_manager(self, manager_address: str) -> bool:
        """Check if a manager address is whitelisted."""
        return self.contract.functions.isWhitelistedManager(
            Web3.to_checksum_address(manager_address)
        ).call()

    @property
    def orion_transparent_vaults(self) -> list[str]:
        """Fetch all Orion transparent vault addresses from the OrionConfig contract."""
        return self.contract.functions.getAllOrionVaults(0).call()

    @property
    def min_deposit_amount(self) -> int:
        """Fetch the minimum deposit amount from the OrionConfig contract."""
        return self.contract.functions.minDepositAmount().call()

    @property
    def min_redeem_amount(self) -> int:
        """Fetch the minimum redeem amount from the OrionConfig contract."""
        return self.contract.functions.minRedeemAmount().call()

    @property
    def v_fee_coefficient(self) -> int:
        """Fetch the volume fee coefficient from the OrionConfig contract."""
        return self.contract.functions.vFeeCoefficient().call()

    @property
    def rs_fee_coefficient(self) -> int:
        """Fetch the revenue share fee coefficient from the OrionConfig contract."""
        return self.contract.functions.rsFeeCoefficient().call()

    @property
    def fee_change_cooldown_duration(self) -> int:
        """Fetch the fee change cooldown duration in seconds."""
        return self.contract.functions.feeChangeCooldownDuration().call()

    @property
    def max_fulfill_batch_size(self) -> int:
        """Fetch the maximum fulfill batch size."""
        return self.contract.functions.maxFulfillBatchSize().call()

    def is_system_idle(self) -> bool:
        """Check if the system is in idle state, required for vault deployment."""
        return self.contract.functions.isSystemIdle().call()


class LiquidityOrchestrator(OrionSmartContract):
    """LiquidityOrchestrator contract."""

    def __init__(self):
        """Initialize the LiquidityOrchestrator contract."""
        config = OrionConfig()
        contract_address = config.contract.functions.liquidityOrchestrator().call()
        super().__init__(
            contract_name="LiquidityOrchestrator",
            contract_address=contract_address,
        )

    @property
    def target_buffer_ratio(self) -> int:
        """Fetch the target buffer ratio."""
        return self.contract.functions.targetBufferRatio().call()

    @property
    def slippage_tolerance(self) -> int:
        """Fetch the slippage tolerance."""
        return self.contract.functions.slippageTolerance().call()

    @property
    def epoch_duration(self) -> int:
        """Fetch the epoch duration in seconds."""
        return self.contract.functions.epochDuration().call()


class VaultFactory(OrionSmartContract):
    """VaultFactory contract."""

    def __init__(
        self,
        vault_type: str,
        contract_address: str | None = None,
    ):
        """Initialize the VaultFactory contract."""
        if contract_address is None:
            config = OrionConfig()
            if vault_type == VaultType.TRANSPARENT:
                contract_address = (
                    config.contract.functions.transparentVaultFactory().call()
                )
            else:
                raise ValueError(f"Unsupported vault type: {vault_type}")

        super().__init__(
            contract_name="TransparentVaultFactory",
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

        validate_var(
            strategist_address,
            error_message=(
                "STRATEGIST_ADDRESS is invalid. "
                "Please provide a valid strategist address."
            ),
        )

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
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

    def __init__(self, contract_name: str):
        """Initialize the OrionVault contract."""
        contract_address = os.getenv("ORION_VAULT_ADDRESS")
        validate_var(
            contract_address,
            error_message=(
                "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
                "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
                "Please follow the SDK Installation instructions to get one: https://sdk.orionfinance.ai/"
            ),
        )

        # Validate that the address is a valid Orion Vault
        config = OrionConfig()
        is_transparent = contract_address in config.orion_transparent_vaults

        if not is_transparent:
            raise ValueError(
                f"The address {contract_address} is NOT a valid Orion Transparent Vault registered in the OrionConfig contract. "
                "Please check your ORION_VAULT_ADDRESS."
            )

        super().__init__(contract_name, contract_address)

    @property
    def max_performance_fee(self) -> int:
        """Fetch the maximum performance fee allowed from the vault contract."""
        return self.contract.functions.MAX_PERFORMANCE_FEE().call()

    @property
    def max_management_fee(self) -> int:
        """Fetch the maximum management fee allowed from the vault contract."""
        return self.contract.functions.MAX_MANAGEMENT_FEE().call()

    @property
    def manager_address(self) -> str:
        """Fetch the manager address."""
        return self.contract.functions.manager().call()

    @property
    def strategist_address(self) -> str:
        """Fetch the strategist address."""
        return self.contract.functions.strategist().call()

    @property
    def is_decommissioning(self) -> bool:
        """Check if the vault is in decommissioning mode."""
        return self.contract.functions.isDecommissioning().call()

    @property
    def active_fee_model(self) -> dict:
        """Fetch the currently active fee model (struct FeeModel)."""
        model = self.contract.functions.activeFeeModel().call()
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
        return self.contract.functions.pendingDeposit(fulfill_batch_size).call()

    def pending_redeem(self, fulfill_batch_size: int | None = None) -> int:
        """Get total pending redemption shares across all users."""
        if fulfill_batch_size is None:
            config = OrionConfig()
            fulfill_batch_size = config.max_fulfill_batch_size
        return self.contract.functions.pendingRedeem(fulfill_batch_size).call()

    def _execute_vault_tx(
        self,
        contract_fn_call,
        key_env: str = "MANAGER_PRIVATE_KEY",
        error_msg: str = "Private key missing for transaction.",
    ) -> TransactionResult:
        """Execute a vault transaction with the given contract function call.

        Args:
            contract_fn_call: The contract function call (e.g., self.contract.functions.requestDeposit(assets))
            key_env: Environment variable name for the private key (default: "MANAGER_PRIVATE_KEY")
            error_msg: Error message for validation

        Returns:
            TransactionResult with transaction hash, receipt, and decoded logs
        """
        private_key = os.getenv(key_env)
        validate_var(private_key, error_msg)
        account = self.w3.eth.account.from_key(private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)
        tx = contract_fn_call.build_transaction(
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

    def request_deposit(self, assets: int) -> TransactionResult:
        """Submit an asynchronous deposit request."""
        return self._execute_vault_tx(
            self.contract.functions.requestDeposit(assets),
            error_msg="Private key missing for deposit request.",
        )

    def cancel_deposit_request(self, amount: int) -> TransactionResult:
        """Cancel a previously submitted deposit request."""
        return self._execute_vault_tx(
            self.contract.functions.cancelDepositRequest(amount),
            error_msg="Private key missing for cancellation.",
        )

    def request_redeem(self, shares: int) -> TransactionResult:
        """Submit a redemption request."""
        return self._execute_vault_tx(
            self.contract.functions.requestRedeem(shares),
            error_msg="Private key missing for redeem request.",
        )

    def cancel_redeem_request(self, shares: int) -> TransactionResult:
        """Cancel a previously submitted redemption request."""
        return self._execute_vault_tx(
            self.contract.functions.cancelRedeemRequest(shares),
            error_msg="Private key missing for cancellation.",
        )

    def update_strategist(self, new_strategist_address: str) -> TransactionResult:
        """Update the strategist address for the vault."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot update strategist at this time."
            )

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
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

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
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
        return self.contract.functions.totalAssets().call()

    @property
    def pending_vault_fees(self) -> float:
        """Fetch the pending vault fees in the underlying asset."""
        config = OrionConfig()
        decimals = config.token_decimals(config.underlying_asset)
        return self.contract.functions.pendingVaultFees().call() / 10**decimals

    @property
    def share_price(self) -> int:
        """Fetch the current share price (value of 1 share unit)."""
        decimals = self.contract.functions.decimals().call()
        return self.contract.functions.convertToAssets(10**decimals).call()

    def convert_to_assets(self, shares: int) -> int:
        """Convert shares to assets."""
        return self.contract.functions.convertToAssets(shares).call()

    def get_portfolio(self) -> dict:
        """Get the vault portfolio."""
        # This returns a tuple (tokens, values)
        tokens, values = self.contract.functions.getPortfolio().call()
        return dict(zip(tokens, values, strict=True))

    def set_deposit_access_control(
        self, access_control_address: str
    ) -> TransactionResult:
        """Set the deposit access control contract address."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot set deposit access control at this time."
            )

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
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
        return self.contract.functions.maxDeposit(
            Web3.to_checksum_address(receiver)
        ).call()

    def can_request_deposit(self, user: str) -> bool:
        """Check if a user is allowed to request a deposit.

        This method queries the vault's depositAccessControl contract.
        If no access control is set (zero address), it returns True.
        """
        try:
            access_control_address = (
                self.contract.functions.depositAccessControl().call()
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
        return access_control.functions.canRequestDeposit(
            Web3.to_checksum_address(user)
        ).call()


class OrionTransparentVault(OrionVault):
    """OrionTransparentVault contract."""

    def __init__(self):
        """Initialize the OrionTransparentVault contract."""
        super().__init__("OrionTransparentVault")

    def transfer_manager_fees(self, amount: int) -> TransactionResult:
        """Transfer manager fees (claimVaultFees)."""
        config = OrionConfig()
        if not config.is_system_idle():
            raise SystemNotIdleError(
                "System is not idle. Cannot transfer manager fees at this time."
            )

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
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
                f"Signer {account.address} is not the vault manager {self.manager_address}. Cannot claim fees."
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

        strategist_private_key = os.getenv("STRATEGIST_PRIVATE_KEY")
        validate_var(
            strategist_private_key,
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
